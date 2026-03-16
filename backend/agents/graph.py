# backend/agents/graph.py
"""LangGraph StateGraph definition for the agentic processing pipeline.

Graph flow:
  triage → memory_suggest → ocr → [conditional] → qa → [conditional]
  → validate → [conditional] → supervisor → memory_learn → END
"""

import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .state import ProcessingState, AgentBlackboard
from .triage import TriageAgent
from .memory import MemoryAgent
from .ocr import OCRAgent
from .qa import EngineeringQAAgent
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


async def ocr_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the OCR Agent with strategy from triage + memory."""
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
            confidences.append(val.get('confidence', 0))
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


async def validation_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Validation Agent on QA results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = ValidationAgent(config=config, blackboard=bb)

    qa_result = state.get('qa_result', {})
    result = await agent.safe_process(qa_result)

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


async def supervisor_node(state: ProcessingState) -> Dict[str, Any]:
    """Run the Supervisor Agent to compile final results."""
    config = state.get('config', {})
    bb = AgentBlackboard(state)
    agent = SupervisorAgent(config=config, blackboard=bb)

    result = await agent.safe_process(state)

    final = result.get('final_results', {}) if result.get('success') else {}
    analysis = final.get('analysis_results', [])

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
        'answer_patterns': {},
    }

    agent.learn_from_result(doc_info, processing_result)

    return {
        'current_step': 'pipeline_complete',
    }


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------

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
    """Retry OCR with incremented retry counter."""
    return {'ocr_retries': state.get('ocr_retries', 0) + 1}


def route_after_qa(state: ProcessingState) -> str:
    """Decide whether to retry QA or proceed to validation."""
    confidence = state.get('qa_confidence', 100)
    retries = state.get('qa_retries', 0)
    config = state.get('config', {})
    threshold = config.get('agentic', {}).get('qa_confidence_threshold', 0.5)
    max_retries = config.get('agentic', {}).get('max_qa_retries', 2)

    if confidence < threshold and retries < max_retries:
        logger.info(f"QA confidence {confidence:.2f} < {threshold}, retry {retries+1}/{max_retries}")
        return "retry_qa"
    return "validate"


async def qa_retry_node(state: ProcessingState) -> Dict[str, Any]:
    """Retry QA with incremented retry counter."""
    return {'qa_retries': state.get('qa_retries', 0) + 1}


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


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def create_processing_graph() -> Any:
    """Build and compile the agentic processing graph.

    Returns a compiled LangGraph that can be invoked with:
        result = await graph.ainvoke(initial_state)
    """
    workflow = StateGraph(ProcessingState)

    # Add nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("memory_suggest", memory_suggest_node)
    workflow.add_node("ocr", ocr_node)
    workflow.add_node("ocr_retry", ocr_retry_node)
    workflow.add_node("qa", qa_node)
    workflow.add_node("qa_retry", qa_retry_node)
    workflow.add_node("validate", validation_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("memory_learn", memory_learn_node)

    # Entry point
    workflow.set_entry_point("triage")

    # Linear edges
    workflow.add_edge("triage", "memory_suggest")
    workflow.add_edge("memory_suggest", "ocr")

    # OCR → conditional
    workflow.add_conditional_edges("ocr", route_after_ocr, {
        "retry_ocr": "ocr_retry",
        "qa": "qa",
    })
    workflow.add_edge("ocr_retry", "ocr")  # retry loops back

    # QA → conditional
    workflow.add_conditional_edges("qa", route_after_qa, {
        "retry_qa": "qa_retry",
        "validate": "validate",
    })
    workflow.add_edge("qa_retry", "qa")  # retry loops back

    # Validation → conditional
    workflow.add_conditional_edges("validate", route_after_validation, {
        "requery_qa": "qa_retry",
        "supervisor": "supervisor",
    })

    # Supervisor → memory learn → END
    workflow.add_edge("supervisor", "memory_learn")
    workflow.add_edge("memory_learn", END)

    return workflow.compile()
