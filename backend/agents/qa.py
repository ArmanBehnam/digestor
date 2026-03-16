# agents/qa.py

import sys
import re
import json
import yaml
import logging
from typing import Any, Dict, List, Optional

sys.path.append('..')
from .base import Talk2DrawingsBaseAgent
from llm.coordinate_mapper import CoordinateMapper
from llm.llm_engines.llm_registry import LLMRegistry

logger = logging.getLogger(__name__)

# ── Agentic: Question Categories ────────────────────────────────────
# Maps question categories to 1-based question indices

QUESTION_CATEGORIES = {
    'code_lookup': [1, 2, 10, 11, 20, 23],         # Building code, ASCE, risk, exposure, SDC, site class
    'ratio_extraction': [3, 4, 5, 6, 7, 8],         # Deflection limits L/xxx
    'numeric_extraction': [9, 13, 14, 15, 24, 25],  # Wind speed, loads, Sds, Sd1
    'factor_extraction': [12, 16, 17, 18, 19, 21, 22]  # GCpi, snow factors, seismic factors
}

DEFAULT_LLM_PREFERENCES = {
    'numeric_extraction': 'openai_gpt4o',
    'code_lookup': 'anthropic_sonnet',
    'ratio_extraction': 'openai_gpt4o',
    'factor_extraction': 'deepseek_r1'
}

CATEGORY_PROMPTS = {
    'code_lookup': """Focus on finding building codes, standards, and categorical classifications.
Look for: IBC, ASCE 7, NYSBC, NYCBC, risk category (I/II/III/IV), exposure category (B/C/D),
seismic design category (A-F), site class (A-F). These are typically found in general notes,
title blocks, or design criteria pages. Check structured_data.building_codes first.""",

    'ratio_extraction': """Focus on finding deflection ratios in the format L/XXX.
Look for patterns like: L/240, L/360, L/600, L/180, L/120. These appear in tables
or bulleted lists under headings like "DEFLECTION CRITERIA", "SERVICEABILITY".
Wall deflections, floor joist, roof rafter, ceiling joist each have separate limits.
Check structured_data.load_requirements for pre-extracted deflection values.""",

    'numeric_extraction': """Focus on finding specific numeric values with engineering units.
Look for: wind speed (XXX mph), live load (XX psf), dead load (XX psf),
ground snow load Pg (XX psf), Sds (X.XXg), Sd1 (X.XXg).
Numbers may appear near keywords even if text is disordered from OCR.
Check structured_data.load_requirements for pre-extracted values.""",

    'factor_extraction': """Focus on finding engineering factors and coefficients.
Look for: GCpi (+/-0.18 or +/-0.55), Is (1.0 or 1.2), Ce (0.7-1.2),
Ct (0.85/1.0/1.2), Ie (1.0/1.25/1.5), Ip (1.0/1.5).
These are dimensionless values typically found in design criteria summaries.
Check structured_data for pre-extracted seismic and snow parameters."""
}


class EngineeringQAAgent(Talk2DrawingsBaseAgent):

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("Engineering_QA_Agent", blackboard=blackboard)
        self.config = config or {}
        self.coordinate_mapper = CoordinateMapper(similarity_threshold=75.0)

        agentic_cfg = self.config.get('agentic', {})
        self.confidence_threshold = agentic_cfg.get('qa_confidence_threshold', 0.5)
        self.max_retries = agentic_cfg.get('max_qa_retries', 2)
        self.llm_preferences = agentic_cfg.get(
            'llm_category_preferences', DEFAULT_LLM_PREFERENCES)

        try:
            with open('config/config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.llm_registry = LLMRegistry(self.config)
            self.questions = self.config.get('questions', [])
            print(f"{self.name}: LLM interface loaded with {len(self.questions)} questions")
        except Exception as e:
            print(f"{self.name}: Could not load LLM interface: {e}")
            self.llm_registry = None
            self.questions = []
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        return (isinstance(input_data, dict) and 'filtered_pages' in input_data and
                isinstance(input_data['filtered_pages'], dict) and
                'matching_pages' in input_data['filtered_pages'])

    # ── Agentic: LLM Selection per Category ─────────────────────────

    def select_llm_for_category(self, category: str) -> Optional[str]:
        """Select preferred LLM engine for a question category.

        Returns engine name or None to use default fallback chain.
        """
        preferred = self.llm_preferences.get(category)
        if preferred and hasattr(self.llm_registry, 'engines'):
            # Check if preferred engine is available
            for engine in self.llm_registry.engines:
                if hasattr(engine, 'name') and preferred in engine.name.lower():
                    if engine.is_available:
                        return preferred
            # Preferred not available, fall back to default chain
            self.log_decision(
                f"Preferred LLM '{preferred}' unavailable for {category}",
                "Falling back to default engine chain",
                decision_type="llm_selected"
            )
        return None

    def get_prompt_for_category(self, category: str) -> str:
        """Get a focused system prompt for a specific question category."""
        base = self.get_enhanced_system_prompt()
        category_guidance = CATEGORY_PROMPTS.get(category, '')
        if category_guidance:
            return f"{base}\n\n**CATEGORY FOCUS ({category}):**\n{category_guidance}"
        return base

    # ── Agentic: Category Batch Processing ──────────────────────────

    async def process_category_batch(self, category: str, question_ids: List[int],
                                     ocr_data: Dict, structured_payload: Dict) -> Dict[str, Any]:
        """Process a batch of questions from the same category."""
        # Select questions for this category
        category_questions = []
        for qid in question_ids:
            idx = qid - 1
            if idx < len(self.questions):
                category_questions.append((qid, self.questions[idx]))

        if not category_questions:
            return {}

        preferred_llm = self.select_llm_for_category(category)
        prompt = self.get_prompt_for_category(category)

        self.log_decision(
            f"Processing {len(category_questions)} questions in '{category}' category",
            f"LLM: {preferred_llm or 'default chain'}",
            decision_type="llm_selected"
        )

        # Build focused payload with only relevant questions
        q_list = [q for _, q in category_questions]
        json_payload = self._build_minimal_payload(structured_payload)

        try:
            # Use the enhanced prompt with category-specific guidance
            answers = self.llm_registry.answer_questions_with_enhanced_prompt(
                json_payload, q_list, prompt)

            # Re-map answer keys from sequential Q1,Q2... to actual question IDs
            remapped = {}
            for i, (qid, _) in enumerate(category_questions):
                src_key = f"Q{i + 1}"
                if src_key in answers:
                    remapped[f"Q{qid}"] = answers[src_key]

            return remapped

        except Exception as e:
            logger.warning(f"Category batch '{category}' failed: {e}")
            return {}

    async def retry_low_confidence_answers(self, answers: Dict[str, Any],
                                           structured_payload: Dict,
                                           threshold: float = 0.6) -> Dict[str, Any]:
        """Retry answers with low confidence using a different LLM."""
        low_confidence_qids = []

        for qid, answer_data in answers.items():
            if not isinstance(answer_data, dict):
                continue
            conf = answer_data.get('confidence', 0)
            if isinstance(conf, str):
                conf = float(conf.replace('%', '')) / 100 if '%' in str(conf) else 0
            elif isinstance(conf, (int, float)) and conf > 1:
                conf = conf / 100.0

            answer = answer_data.get('answer', 'Not Found')
            if conf < threshold and answer != 'Not Found':
                try:
                    q_num = int(qid.replace('Q', ''))
                    low_confidence_qids.append(q_num)
                except ValueError:
                    pass

        if not low_confidence_qids:
            return answers

        self.log_decision(
            f"Retrying {len(low_confidence_qids)} low-confidence answers",
            f"Questions: {low_confidence_qids}, threshold: {threshold}",
            decision_type="retry_triggered"
        )

        # Retry with combined text fallback (different LLM will be tried)
        retry_questions = []
        for qid in low_confidence_qids:
            idx = qid - 1
            if idx < len(self.questions):
                retry_questions.append((qid, self.questions[idx]))

        if not retry_questions:
            return answers

        combined_text = "\n\n".join(
            f"[Page {page.get('page_number', '?')}]\n{page.get('extracted_text', '')}"
            for page in structured_payload.get('pages_with_metadata', [])
        )

        try:
            q_list = [q for _, q in retry_questions]
            retry_answers = self.llm_registry.answer_questions_with_fallback(
                combined_text, q_list)

            # Merge retry results if they're better
            for i, (qid, _) in enumerate(retry_questions):
                src_key = f"Q{i + 1}"
                key = f"Q{qid}"
                if src_key in retry_answers:
                    retry_ans = retry_answers[src_key]
                    if isinstance(retry_ans, dict):
                        retry_conf = retry_ans.get('confidence', 0)
                        if isinstance(retry_conf, str):
                            retry_conf = float(retry_conf.replace('%', '')) / 100
                        orig_conf = 0
                        if key in answers and isinstance(answers[key], dict):
                            orig_conf_val = answers[key].get('confidence', 0)
                            if isinstance(orig_conf_val, str):
                                orig_conf = float(orig_conf_val.replace('%', '')) / 100
                            else:
                                orig_conf = float(orig_conf_val)
                                if orig_conf > 1:
                                    orig_conf /= 100

                        if retry_conf > orig_conf:
                            answers[key] = retry_ans
                            answers[key]['source'] = answers[key].get('source', '') + '_retry'

        except Exception as e:
            logger.warning(f"Retry failed: {e}")

        return answers

    # ── Main Process (Agentic) ──────────────────────────────────────

    async def process(self, ocr_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.llm_registry:
            raise Exception("LLM Registry not available")

        try:
            print(f"QA Agent processing {len(self.questions)} questions")
            filtered_pages = ocr_data['filtered_pages']['matching_pages']

            if not filtered_pages:
                return {'success': False, 'agent': self.name,
                        'error': 'No relevant pages found for processing',
                        'qa_results': {}}

            # Enrich page metadata
            for page in filtered_pages:
                page['section'] = self._extract_section(page)
                if 'ocr_engine' not in page:
                    page['ocr_engine'] = 'aws_textract'
                if 'confidence_avg' not in page:
                    page['confidence_avg'] = page.get('confidence', 0.9)

            structured_payload = {
                "pages_with_metadata": filtered_pages,
                "document_info": ocr_data.get('document_info', {}),
                "source_mapping": ocr_data.get('source_mapping', [])
            }

            # ── Agentic: Category-based processing ──────────────────
            all_answers = {}
            category_success = 0

            for category, question_ids in QUESTION_CATEGORIES.items():
                try:
                    batch_answers = await self.process_category_batch(
                        category, question_ids, ocr_data, structured_payload)
                    if batch_answers:
                        all_answers.update(batch_answers)
                        category_success += 1
                except Exception as e:
                    logger.warning(f"Category '{category}' failed: {e}")

            # Fall back to monolithic processing if category-based mostly failed
            if category_success < 2 or len(all_answers) < 10:
                self.log_decision(
                    "Falling back to monolithic QA processing",
                    f"Only {category_success} categories succeeded, {len(all_answers)} answers",
                    decision_type="retry_triggered"
                )
                all_answers = await self._process_with_metadata(structured_payload)

            # ── Agentic: Retry low-confidence answers ───────────────
            all_answers = await self.retry_low_confidence_answers(
                all_answers, structured_payload, threshold=self.confidence_threshold)

            # Map coordinates
            enhanced_answers = await self._map_coordinates_with_metadata(
                all_answers, structured_payload)

            coord_found = sum(1 for ans in enhanced_answers.values()
                              if isinstance(ans, dict) and ans.get('coordinates') != 'N/A')

            # Calculate overall confidence
            confidences = []
            for ans in enhanced_answers.values():
                if isinstance(ans, dict):
                    conf = ans.get('confidence', 0)
                    if isinstance(conf, str):
                        conf = float(conf.replace('%', '')) / 100 if '%' in str(conf) else 0
                    elif isinstance(conf, (int, float)) and conf > 1:
                        conf = conf / 100.0
                    confidences.append(conf)
            avg_confidence = sum(confidences) / max(len(confidences), 1)

            print(f"QA complete: {len(enhanced_answers)} answers, "
                  f"avg confidence: {avg_confidence:.2f}, "
                  f"coordinates: {coord_found}")

            return {
                'success': True,
                'agent': self.name,
                'qa_results': enhanced_answers,
                'questions_processed': len(self.questions),
                'pages_used': len(filtered_pages),
                'coordinates_found': coord_found,
                'avg_confidence': avg_confidence
            }

        except Exception as e:
            raise Exception(f"QA processing failed: {e}")

    # ── Existing methods (preserved) ────────────────────────────────

    def _build_minimal_payload(self, structured_payload: Dict) -> str:
        """Build JSON payload for LLM, same as _process_with_metadata but returns string."""
        payload_pages = []
        for page in structured_payload['pages_with_metadata']:
            page_entry = {
                'extracted_text': page.get('extracted_text', ''),
                'page_number': page.get('page_number'),
                'source_pdf': page.get('source_pdf'),
                'section': page.get('section', 'N/A'),
            }
            structured_data = page.get('structured_data', {})
            if structured_data:
                page_entry['structured_data'] = structured_data
            table_elements = page.get('table_elements', [])
            if table_elements:
                page_entry['table_data'] = [
                    {'text': t.get('text', ''), 'confidence': t.get('confidence', 0)}
                    for t in table_elements[:20]
                ]
            payload_pages.append(page_entry)

        minimal_payload = {'pages_with_metadata': payload_pages}
        return json.dumps(minimal_payload, indent=2)

    def _extract_section(self, page: Dict) -> str:
        text = page.get('extracted_text', '')
        patterns = [r'\b(S\d+\.\d+)\b', r'\b(S\d+)\b',
                    r'DRAWING NO\.\s*([^\s]+)', r'Sheet\s+(\S+)',
                    r'\b([A-Z]\d+\.\d+)\b']
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        if 'DRAWING' in text.upper():
            lines = text.split('\n')
            for line in lines:
                if 'S0.' in line or 'S1.' in line or 'S2.' in line:
                    parts = line.split()
                    for part in parts:
                        if re.match(r'S\d+\.\d+', part):
                            return part
        return 'N/A'

    def _reconstruct_missing_metadata(self, answers: Dict, structured_payload: Dict) -> Dict[str, Any]:
        enhanced_answers = {}
        for qid, answer_data in answers.items():
            if isinstance(answer_data, dict):
                answer_text = answer_data.get('answer', 'Not Found')
                source_pdf, page_number = self._find_likely_source(answer_text, structured_payload)
                enhanced_answers[qid] = {
                    'answer': answer_text,
                    'source_pdf': source_pdf,
                    'page': page_number,
                    'confidence': answer_data.get('confidence', 50),
                    'source': answer_data.get('source', 'reconstructed')
                }
            else:
                enhanced_answers[qid] = {
                    'answer': str(answer_data) if answer_data else 'Not Found',
                    'source_pdf': 'unknown', 'page': 'unknown',
                    'confidence': 0, 'source': 'fallback'
                }
        return enhanced_answers

    def _find_likely_source(self, answer_text: str, structured_payload: Dict) -> tuple:
        if answer_text == "Not Found" or len(answer_text) < 3:
            return 'unknown', 'unknown'
        best_match = None
        best_score = 0
        for page in structured_payload['pages_with_metadata']:
            page_text = page.get('extracted_text', '').lower()
            answer_lower = answer_text.lower()
            if answer_lower in page_text:
                score = len(answer_text)
                if score > best_score:
                    best_score = score
                    best_match = page
            answer_words = answer_lower.split()
            for word in answer_words:
                if len(word) > 3 and word in page_text:
                    score = len(word)
                    if score > best_score:
                        best_score = score
                        best_match = page
        if best_match:
            return best_match.get('source_pdf', 'unknown'), best_match.get('page_number', 'unknown')
        return 'unknown', 'unknown'

    def get_enhanced_system_prompt(self):
        return """You are an expert structural engineering document analyst. Extract answers from OCR-processed engineering drawings and specifications.

IMPORTANT: The text comes from OCR on engineering drawings, so words may be jumbled or out of order. Look for INDIVIDUAL values, numbers, and technical terms rather than complete sentences. Each page includes:
- extracted_text: Raw OCR text (may be spatially disordered)
- structured_data: Pre-extracted values from regex pattern matching (PRIORITIZE these - they are high-confidence extractions)
- table_data: Data from detected tables

PRIORITIZE structured_data matches over raw text. If structured_data contains a value for a category (e.g., building_codes, load_requirements), use that value.

Return ONLY valid JSON: {"Q1": {"answer": "value", "source_pdf": "file.pdf", "page_number": 2, "confidence": "90%"}, ...}

**Extraction Strategy:**
1. First check structured_data for pre-extracted values (building codes, loads, deflection criteria, seismic params)
2. Then scan extracted_text for keywords: IBC, ASCE, L/240, L/360, psf, mph, Sds, Sd1, GCpi, etc.
3. Look for numbers near engineering keywords even if text is disordered
4. For deflection limits, look for patterns like L/XXX or fractions
5. For loads, look for numbers followed by psf, plf, mph, ksi

**Rules:**
- JSON only, no explanations
- Extract exact page_number and source_pdf
- All questions required
- If not found: "Not Found", "unknown", 0
- When structured_data has a match, use confidence 90%+"""

    async def _process_with_metadata(self, structured_payload: Dict) -> Dict[str, Any]:
        """Monolithic processing fallback - sends all questions at once."""
        json_payload = self._build_minimal_payload(structured_payload)
        print(f"LLM payload size: {len(json_payload)} chars (~{len(json_payload)//4} tokens)")
        enhanced_prompt = self.get_enhanced_system_prompt()

        try:
            answers = self.llm_registry.answer_questions_with_enhanced_prompt(
                json_payload, self.questions, enhanced_prompt)
            if all(isinstance(ans, dict) and 'source_pdf' in ans and 'page' in ans
                   for ans in answers.values()):
                return answers
            else:
                return self._reconstruct_missing_metadata(answers, structured_payload)
        except Exception as e:
            print(f"Enhanced prompt failed: {e}, using fallback")
            combined_text = "\n\n".join(
                f"[Page {page.get('page_number', '?')}]\n{page.get('extracted_text', '')}"
                for page in structured_payload.get('pages_with_metadata', []))
            fallback_answers = self.llm_registry.answer_questions_with_fallback(
                combined_text, self.questions)
            return self._reconstruct_missing_metadata(fallback_answers, structured_payload)

    async def _map_coordinates_with_metadata(self, answers: Dict, structured_payload: Dict) -> Dict[str, Any]:
        enhanced_answers = {}
        for qid, answer_data in answers.items():
            if isinstance(answer_data, dict):
                answer_text = answer_data.get('answer', 'Not Found')
                source_pdf = answer_data.get('source_pdf', 'unknown')
                page_number = answer_data.get('page', 'unknown')
                confidence = answer_data.get('confidence', '0%')
                section = 'N/A'
                try:
                    page_num_int = int(page_number)
                    matching_pages = [p for p in structured_payload['pages_with_metadata']
                                      if p.get('page_number') == page_num_int
                                      and p.get('source_pdf') == source_pdf]
                    if matching_pages:
                        section = matching_pages[0].get('section', 'N/A')
                except (ValueError, KeyError):
                    pass
                coordinates = self._find_coordinates_with_source(
                    answer_text, source_pdf, page_number, structured_payload)
                enhanced_answers[qid] = {
                    'answer': answer_text, 'source_pdf': source_pdf,
                    'page': page_number, 'confidence': confidence,
                    'section': section, 'coordinates': coordinates,
                    'coordinates_display': self._format_coordinates(coordinates),
                    'has_coordinates': coordinates != 'N/A',
                    'ocr_engine': 'aws_textract'
                }
            else:
                enhanced_answers[qid] = {
                    'answer': str(answer_data) if answer_data else 'Not Found',
                    'source_pdf': 'unknown', 'page': 'unknown', 'confidence': '0%',
                    'section': 'N/A', 'coordinates': 'N/A',
                    'coordinates_display': 'N/A', 'has_coordinates': False,
                    'ocr_engine': 'aws_textract'
                }
        return enhanced_answers

    def _find_coordinates_with_source(self, answer_text, source_pdf, page_number, structured_payload):
        if answer_text == "Not Found" or page_number == "unknown":
            return "N/A"
        try:
            page_num_int = int(page_number)
            matching_pages = [p for p in structured_payload['pages_with_metadata']
                              if p.get('page_number') == page_num_int
                              and p.get('source_pdf') == source_pdf]
            if not matching_pages:
                return "N/A"
            page_data = matching_pages[0]
            if hasattr(self, 'coordinate_mapper'):
                result = self.coordinate_mapper.find_answer_coordinates(
                    answer_text, [page_data], page_num_int)
                if result and 'bounding_box' in result:
                    return result['bounding_box']
        except (ValueError, KeyError) as e:
            logger.debug(f"Coordinate mapping error: {e}")
        return "N/A"

    def _format_coordinates(self, coordinates):
        if coordinates == "N/A" or not coordinates:
            return "N/A"
        if isinstance(coordinates, dict):
            return (f"({coordinates.get('x', 0)}, {coordinates.get('y', 0)}, "
                    f"{coordinates.get('width', 0)}, {coordinates.get('height', 0)})")
        return str(coordinates)
