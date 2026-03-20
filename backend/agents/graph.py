# backend/agents/graph.py
"""LangGraph StateGraph definition for the agentic processing pipeline.

3-Tier Fallback Chain (matching Week32 production behavior):

  triage -> memory_suggest ->
    pdfjs (Tier 1: text extraction + LLM) ->
      [fallback_check: >5 missing or <70% confidence?]
        -> YES -> ocr (Tier 2: AWS Textract + LLM) ->
          [quality_check / retry loop] -> qa ->
            [confidence_check / retry loop] ->
              vlm_check ->
                [>5 still missing?]
                  -> YES -> vlm (Tier 3: Gemini page images)
                  -> NO  -> validate
        -> NO  -> validate ->
  validate -> [contradiction check] -> supervisor -> memory_learn -> END
"""

import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .state import ProcessingState, AgentBlackboard
from .triage import TriageAgent
from .memory import MemoryAgent
from .pdfjs_agent import PDFJSAgent, QUESTION_METADATA
from .ocr import OCRAgent
from .qa import EngineeringQAAgent
from .vlm_agent import VLMAgent
from .validation import ValidationAgent
from .supervisor import SupervisorAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node functions — each takes ProcessingState, returns partial state update
# ---------------------------------------------------------------------------

async def triage_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Triage Agent to classify the document."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = TriageAgent(config=config, blackboard=bb)

    result = await agent.safe_process(state.get('pdf_path', ''))

    return {
        'triage_result': result,
        'document_info': {
            'document_type': result.get('document_type', 'mixed'),
            'relevant_pages': result.get('relevant_pages', []),
            'complexity': result.get('complexity', {}),
        },
        'current_step': 'triage_complete',
        'decisions_log': bb.state.get('decisions_log', []),
        'agent_messages': bb.state.get('agent_messages', []),
    }


async def memory_suggest_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Memory Agent to check for prior strategies."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = MemoryAgent(config=config, blackboard=bb)

    result = await agent.safe_process({
        'document_info': state.get('document_info', {}),
    })

    suggestions = result.get('suggestions', {}) if result.get('success') else {}

    return {
        'memory_suggestions': suggestions,
        'current_step': 'memory_suggest_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


# ── TIER 1: PDF.js Text Extraction + LLM ─────────────────────────────

async def pdfjs_node(state: ProcessingState) -> Dict[str, Any]:
    """Tier 1: Extract text from PDF and run LLM to answer questions."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = PDFJSAgent(config=config, blackboard=bb)

    result = await agent.safe_process(state.get('pdf_path', ''))

    pdfjs_sufficient = not result.get('should_fallback', True) if result.get('success') else False

    return {
        'pdfjs_result': result,
        'pdfjs_analysis': result.get('analysis_results', []) if result.get('success') else [],
        'pdfjs_text_quality': result.get('text_quality', {}),
        'pdfjs_sufficient': pdfjs_sufficient,
        'processing_tier': 1 if pdfjs_sufficient else 0,
        'current_step': 'pdfjs_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


def route_after_pdfjs(state: ProcessingState) -> str:
    """Decide whether Tier 1 is sufficient or we need Tier 2 (OCR)."""
    if state.get('pdfjs_sufficient', False):
        logger.info("Tier 1 (PDF.js) sufficient — skipping OCR, going to validation")
        return "validate_pdfjs"
    reason = state.get('pdfjs_result', {}).get('fallback_reason', 'unknown')
    logger.info(f"Tier 1 insufficient ({reason}) — escalating to Tier 2 (OCR)")
    return "ocr"


# ── TIER 2: OCR + LLM ────────────────────────────────────────────────

async def ocr_node(state: ProcessingState) -> Dict[str, Any]:
    """Tier 2: Run OCR Agent with strategy from triage + memory."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = OCRAgent(config=config, blackboard=bb)

    result = await agent.safe_process(state.get('pdf_path', ''))

    ocr_quality = result.get('quality_score', 0.0) if result.get('success') else 0.0
    retries = state.get('ocr_retries', 0)

    return {
        'ocr_result': result,
        'ocr_quality': ocr_quality,
        'ocr_retries': retries,
        'ocr_strategy': result.get('ocr_strategy', {}),
        'current_step': 'ocr_complete',
        'decisions_log': bb.state.get('decisions_log', []),
        'cost_tracker': bb.state.get('cost_tracker', {}),
    }


def route_after_ocr(state: ProcessingState) -> str:
    """Decide whether to retry OCR or proceed to QA."""
    quality = state.get('ocr_quality', 1.0)
    retries = state.get('ocr_retries', 0)
    config = state.get('config', {})
    threshold = config.get('agentic', {}).get('ocr_quality_threshold', 0.7)
    max_retries = config.get('agentic', {}).get('max_ocr_retries', 2)

    if quality < threshold and retries < max_retries:
        logger.info(f"OCR quality {quality:.2f} < {threshold}, retry {retries+1}/{max_retries}")
        return "retry_ocr"
    return "qa"


async def ocr_retry_node(state: ProcessingState) -> Dict[str, Any]:
    """Increment OCR retry counter."""
    return {'ocr_retries': state.get('ocr_retries', 0) + 1}


async def qa_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the QA Agent on OCR results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = EngineeringQAAgent(config=config, blackboard=bb)

    ocr_result = state.get('ocr_result', {})
    result = await agent.safe_process(ocr_result)

    # Compute average confidence
    qa_results = result.get('qa_results', {}) if result.get('success') else {}
    confidences = []
    for val in qa_results.values():
        if isinstance(val, dict):
            conf = val.get('confidence', 0)
            if isinstance(conf, str):
                try:
                    conf = float(conf.replace('%', '')) / 100 if '%' in str(conf) else float(conf)
                except (ValueError, TypeError):
                    conf = 0
            elif isinstance(conf, (int, float)) and conf > 1:
                conf = conf / 100.0
            confidences.append(conf)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    retries = state.get('qa_retries', 0)

    return {
        'qa_result': result,
        'qa_confidence': avg_confidence,
        'qa_retries': retries,
        'current_step': 'qa_complete',
        'decisions_log': bb.state.get('decisions_log', []),
        'cost_tracker': bb.state.get('cost_tracker', {}),
    }


def route_after_qa(state: ProcessingState) -> str:
    """Decide whether to retry QA or proceed to VLM check."""
    confidence = state.get('qa_confidence', 100)
    retries = state.get('qa_retries', 0)
    config = state.get('config', {})
    threshold = config.get('agentic', {}).get('qa_confidence_threshold', 0.5)
    max_retries = config.get('agentic', {}).get('max_qa_retries', 2)

    if confidence < threshold and retries < max_retries:
        logger.info(f"QA confidence {confidence:.2f} < {threshold}, retry {retries+1}/{max_retries}")
        return "retry_qa"
    return "vlm_check"


async def qa_retry_node(state: ProcessingState) -> Dict[str, Any]:
    """Increment QA retry counter."""
    return {'qa_retries': state.get('qa_retries', 0) + 1}


# ── TIER 3: VLM Check & Processing ───────────────────────────────────

async def vlm_check_node(state: ProcessingState) -> Dict[str, Any]:
    """Check if VLM (Tier 3) processing is needed based on missing answers.

    Converts QA results to AnalysisResult[] format, maps answer coordinates
    using OCR text_elements, checks for missing answers, and determines
    whether to escalate to VLM.
    """
    qa_result = state.get('qa_result', {})
    qa_results = qa_result.get('qa_results', {}) if qa_result.get('success') else {}
    ocr_result = state.get('ocr_result', {})
    page_results = ocr_result.get('page_results', [])

    # ── Coordinate mapping: match answers to OCR bounding boxes ──
    mapped_qa = {}
    if page_results:
        try:
            from llm.coordinate_mapper import CoordinateMapper
            mapper = CoordinateMapper()
            mapped_qa = mapper.map_multiple_answers(qa_results, page_results)
            logger.info(f"Coordinate mapping: {sum(1 for v in mapped_qa.values() if isinstance(v, dict) and v.get('has_coordinates'))} answers with bbox")
        except Exception as e:
            logger.warning(f"Coordinate mapping failed: {e}")

    # Convert QA results to AnalysisResult[] format for consistency
    analysis_results = []
    for i, meta in enumerate(QUESTION_METADATA):
        qid = f"Q{i + 1}"
        # Prefer mapped (coordinate-enriched) answer, fall back to raw
        answer_data = mapped_qa.get(qid) or qa_results.get(qid, {})

        if isinstance(answer_data, dict):
            raw_answer = answer_data.get('answer', 'Not Found')
            raw_conf = answer_data.get('confidence', 0)
            # Normalize confidence
            if isinstance(raw_conf, str):
                try:
                    raw_conf = float(raw_conf.replace('%', '')) / 100 if '%' in str(raw_conf) else float(raw_conf)
                except (ValueError, TypeError):
                    raw_conf = 0
            elif isinstance(raw_conf, (int, float)) and raw_conf > 1:
                raw_conf = raw_conf / 100.0
            raw_page = answer_data.get('page', 'unknown')
        else:
            raw_answer = 'Not Found'
            raw_conf = 0
            raw_page = 'unknown'

        reference = f"Page {raw_page}" if raw_page not in ('unknown', 'N/A', '') else "Not Found"

        pair = {
            "answer": raw_answer,
            "reference": reference,
            "confidence": raw_conf,
            "feedback": "up",
        }

        # Add bbox from coordinate mapping (normalize pixel coords to 0-1)
        if isinstance(answer_data, dict) and isinstance(answer_data.get('coordinates'), dict):
            coords = answer_data['coordinates']
            bbox_raw = coords.get('bounding_box', {})
            if bbox_raw:
                # Find page dimensions for normalization
                page_num = answer_data.get('page')
                pg = next((p for p in page_results if p.get('page_number') == page_num), None)
                pw = pg.get('page_width', 1000) if pg else 1000
                ph = pg.get('page_height', 1000) if pg else 1000
                pair["bbox"] = {
                    "x": round(bbox_raw.get("x", 0) / pw, 4),
                    "y": round(bbox_raw.get("y", 0) / ph, 4),
                    "width": round(bbox_raw.get("width", 0) / pw, 4),
                    "height": round(bbox_raw.get("height", 0) / ph, 4),
                }
                pair["reference"] = f"Page {page_num}" if page_num else reference

        analysis_results.append({
            "category": meta["category"],
            "question": meta["question"],
            "pairs": [pair],
        })

    # Count missing answers
    not_found_answers = [
        "not found", "n/a", "na", "none", "not specified",
        "not available", "not provided", "unknown", ""
    ]
    not_found_phrases = [
        "not found", "not specified", "not mentioned", "not available",
        "not provided", "error:", "all llm engines failed",
        "context_length_exceeded", "unable to", "cannot be determined",
    ]
    missing_questions = []
    for i, r in enumerate(analysis_results):
        pairs = r.get("pairs", [])
        if pairs:
            answer = (pairs[0].get("answer", "") or "").strip().lower()
            conf = pairs[0].get("confidence", 0)
            is_missing = (
                answer in not_found_answers
                or not answer
                or any(phrase in answer for phrase in not_found_phrases)
                or conf == 0
            )
            if is_missing:
                missing_questions.append({
                    "index": i,
                    "category": r.get("category", ""),
                    "question": r.get("question", ""),
                })

    needs_vlm = len(missing_questions) > 5
    processing_tier = 2

    logger.info(f"VLM check: {len(missing_questions)} missing answers, "
                f"needs_vlm={needs_vlm}")

    return {
        'analysis_results': analysis_results,
        'missing_questions': missing_questions,
        'processing_tier': processing_tier,
        'current_step': 'vlm_check_complete',
    }


def route_after_vlm_check(state: ProcessingState) -> str:
    """Decide whether to run VLM or go directly to validation."""
    missing = state.get('missing_questions', [])
    if len(missing) > 5:
        logger.info(f"{len(missing)} missing answers — escalating to Tier 3 (VLM)")
        return "vlm"
    logger.info(f"Only {len(missing)} missing — proceeding to validation")
    return "validate_tier2"


async def vlm_node(state: ProcessingState) -> Dict[str, Any]:
    """Tier 3: Run VLM on missing questions using PDF page images."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = VLMAgent(config=config, blackboard=bb)

    result = await agent.safe_process({
        'pdf_path': state.get('pdf_path', ''),
        'analysis_results': state.get('analysis_results', []),
        'missing_questions': state.get('missing_questions', []),
    })

    updated_analysis = result.get('analysis_results', state.get('analysis_results', []))

    return {
        'vlm_result': result,
        'vlm_answers': result.get('vlm_answers', []),
        'analysis_results': updated_analysis,
        'processing_tier': 3,
        'current_step': 'vlm_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


# ── Validation ────────────────────────────────────────────────────────

async def validate_pdfjs_node(state: ProcessingState) -> Dict[str, Any]:
    """Validate Tier 1 (PDF.js) results — copy pdfjs_analysis to analysis_results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = ValidationAgent(config=config, blackboard=bb)

    # Use PDF.js results as the analysis_results
    analysis_results = state.get('pdfjs_analysis', [])

    # Run validation on the QA-style result
    # Build a mock qa_result for the validator
    qa_result_for_validation = {
        'success': True,
        'qa_results': {},
    }
    for i, ar in enumerate(analysis_results):
        pairs = ar.get('pairs', [])
        if pairs:
            qa_result_for_validation['qa_results'][f'Q{i+1}'] = {
                'answer': pairs[0].get('answer', 'Not Found'),
                'confidence': pairs[0].get('confidence', 0),
                'page': pairs[0].get('reference', 'unknown'),
            }

    result = await agent.safe_process(qa_result_for_validation)

    return {
        'analysis_results': analysis_results,
        'validation_result': result,
        'processing_tier': 1,
        'current_step': 'validation_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


async def validation_node(state: ProcessingState) -> Dict[str, Any]:
    """Validate Tier 2/3 results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = ValidationAgent(config=config, blackboard=bb)

    # Convert analysis_results (AnalysisResult[] format) to what ValidationAgent expects
    analysis_results = state.get('analysis_results', [])
    qa_result = state.get('qa_result', {})

    # Build 'results' list and 'qa_results' dict for the validator
    results_list = []
    qa_results_dict = {}
    for i, ar in enumerate(analysis_results):
        pairs = ar.get('pairs', [])
        answer = pairs[0].get('answer', 'Not Found') if pairs else 'Not Found'
        confidence = pairs[0].get('confidence', 0) if pairs else 0
        reference = pairs[0].get('reference', 'N/A') if pairs else 'N/A'
        results_list.append({
            'Question_Number': i + 1,
            'Question': ar.get('question', ''),
            'Answer': answer,
            'Page': reference,
            'Confidence': confidence,
        })
        qa_results_dict[f'Q{i+1}'] = {
            'answer': answer,
            'confidence': confidence,
            'page': reference,
        }

    validation_input = {
        'results': results_list,
        'qa_results': qa_results_dict,
    }
    result = await agent.safe_process(validation_input)

    requery_ids = []
    if result.get('success'):
        for s in result.get('requery_suggestions', []):
            requery_ids.append(s['question_id'])

    return {
        'validation_result': result,
        'requery_question_ids': requery_ids,
        'current_step': 'validation_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


def route_after_validation(state: ProcessingState) -> str:
    """Decide whether to re-query QA or proceed to supervisor."""
    validation = state.get('validation_result', {})
    contradictions = validation.get('contradictions', [])
    qa_retries = state.get('qa_retries', 0)
    config = state.get('config', {})
    max_retries = config.get('agentic', {}).get('max_qa_retries', 2)

    high_severity = [c for c in contradictions if c.get('severity') == 'high']
    requery_ids = state.get('requery_question_ids', [])

    if high_severity and requery_ids and qa_retries < max_retries:
        logger.info(f"High-severity contradictions found, re-querying {len(requery_ids)} questions")
        return "requery_qa"
    return "supervisor"


# ── Supervisor & Memory Learn ─────────────────────────────────────────

async def supervisor_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Supervisor Agent to compile final results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = SupervisorAgent(config=config, blackboard=bb)

    # analysis_results in state is authoritative — it's built by:
    #   Tier 1: pdfjs_node → validate_pdfjs_node
    #   Tier 2: vlm_check_node (converts QA results to AnalysisResult[] format)
    #   Tier 3: vlm_node (merges VLM answers into analysis_results)
    # The supervisor's compile_final_results builds from qa_result which is the
    # RAW Tier 2 output — it does NOT include VLM fills or Tier 1 results.
    # So we ALWAYS prefer the state's analysis_results.
    existing_analysis = state.get('analysis_results', [])

    result = await agent.safe_process(state)
    final = result.get('final_results', {}) if result.get('success') else {}

    # Always use the pipeline's analysis_results (includes VLM fills)
    analysis = existing_analysis

    processing_tier = state.get('processing_tier', 1)
    final['processing_tier'] = processing_tier

    return {
        'final_results': final,
        'analysis_results': analysis,
        'current_step': 'supervisor_complete',
        'decisions_log': bb.state.get('decisions_log', []),
    }


async def memory_learn_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Memory Agent to store what worked."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = MemoryAgent(config=config, blackboard=bb)

    doc_info = state.get('document_info', {})
    processing_result = {
        'ocr_strategy': state.get('ocr_strategy', {}),
        'ocr_engine_used': state.get('ocr_strategy', {}).get('primary', 'unknown'),
        'qa_confidence': state.get('qa_confidence', 0),
        'processing_tier': state.get('processing_tier', 1),
        'answer_patterns': {},
    }

    agent.learn_from_result(doc_info, processing_result)

    return {
        'current_step': 'pipeline_complete',
    }


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def create_processing_graph() -> Any:
    """Build and compile the agentic processing graph with 3-tier fallback.

    Flow:
      triage -> memory_suggest -> pdfjs (Tier 1)
        -> [sufficient?]
          YES -> validate_pdfjs -> supervisor -> memory_learn -> END
          NO  -> ocr (Tier 2) -> [quality?] -> qa -> [confidence?]
                  -> vlm_check -> [>5 missing?]
                    YES -> vlm (Tier 3) -> validate -> supervisor -> memory_learn -> END
                    NO  -> validate -> [contradictions?] -> supervisor -> memory_learn -> END

    Returns a compiled LangGraph that can be invoked with:
        result = await graph.ainvoke(initial_state)
    """
    workflow = StateGraph(ProcessingState)

    # ── Add nodes ──
    workflow.add_node("triage", triage_node)
    workflow.add_node("memory_suggest", memory_suggest_node)

    # Tier 1
    workflow.add_node("pdfjs", pdfjs_node)

    # Tier 2
    workflow.add_node("ocr", ocr_node)
    workflow.add_node("ocr_retry", ocr_retry_node)
    workflow.add_node("qa", qa_node)
    workflow.add_node("qa_retry", qa_retry_node)

    # Tier 3
    workflow.add_node("vlm_check", vlm_check_node)
    workflow.add_node("vlm", vlm_node)

    # Validation (two entry points: one for Tier 1, one for Tier 2/3)
    workflow.add_node("validate_pdfjs", validate_pdfjs_node)
    workflow.add_node("validate", validation_node)

    # Final
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("memory_learn", memory_learn_node)

    # ── Entry point ──
    workflow.set_entry_point("triage")

    # ── Linear edges ──
    workflow.add_edge("triage", "memory_suggest")
    workflow.add_edge("memory_suggest", "pdfjs")

    # ── Tier 1 -> conditional ──
    workflow.add_conditional_edges("pdfjs", route_after_pdfjs, {
        "validate_pdfjs": "validate_pdfjs",  # Tier 1 sufficient
        "ocr": "ocr",                         # Escalate to Tier 2
    })

    # Tier 1 validation -> supervisor
    workflow.add_edge("validate_pdfjs", "supervisor")

    # ── Tier 2: OCR -> conditional ──
    workflow.add_conditional_edges("ocr", route_after_ocr, {
        "retry_ocr": "ocr_retry",
        "qa": "qa",
    })
    workflow.add_edge("ocr_retry", "ocr")  # retry loops back

    # QA -> conditional
    workflow.add_conditional_edges("qa", route_after_qa, {
        "retry_qa": "qa_retry",
        "vlm_check": "vlm_check",
    })
    workflow.add_edge("qa_retry", "qa")  # retry loops back

    # ── VLM check -> conditional ──
    workflow.add_conditional_edges("vlm_check", route_after_vlm_check, {
        "vlm": "vlm",              # Escalate to Tier 3
        "validate_tier2": "validate",  # Tier 2 sufficient
    })

    # VLM -> validate
    workflow.add_edge("vlm", "validate")

    # ── Validation -> conditional ──
    workflow.add_conditional_edges("validate", route_after_validation, {
        "requery_qa": "qa_retry",
        "supervisor": "supervisor",
    })

    # ── Supervisor -> memory learn -> END ──
    workflow.add_edge("supervisor", "memory_learn")
    workflow.add_edge("memory_learn", END)

    return workflow.compile()
