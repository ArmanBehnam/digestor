# agents\qa.py
import sys
from typing import Dict, Any
from .base import Talk2DrawingsBaseAgent
from llm.coordinate_mapper import CoordinateMapper
import re
from llm.llm_engines.llm_registry import LLMRegistry
import yaml
import json

sys.path.append('..')


class EngineeringQAAgent(Talk2DrawingsBaseAgent):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("Engineering_QA_Agent")
        self.config = config or {}
        self.coordinate_mapper = CoordinateMapper(similarity_threshold=75.0)
        try:
            with open('config/config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.llm_registry = LLMRegistry(self.config)
            self.questions = self.config.get('questions', [])
            print(f"{self.name}: LLM interface loaded with {len(self.questions)} questions")

        except ImportError as e:
            print(f"{self.name}: Could not load LLM interface: {e}")
            self.llm_interface = None
            self.questions = []
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        return (isinstance(input_data, dict) and 'filtered_pages' in input_data and
                isinstance(input_data['filtered_pages'], dict) and 'matching_pages' in input_data['filtered_pages'])

    def _extract_section(self, page: Dict) -> str:
        text = page.get('extracted_text', '')
        patterns = [r'\b(S\d+\.\d+)\b',
                    r'\b(S\d+)\b',
                    r'DRAWING NO\.\s*([^\s]+)',
                    r'Sheet\s+(\S+)',
                    r'\b([A-Z]\d+\.\d+)\b']
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result = match.group(1)
                # Removed verbose logging
                return result
        if 'DRAWING' in text.upper():
            lines = text.split('\n')
            for line in lines:
                if 'S0.' in line or 'S1.' in line or 'S2.' in line:
                    parts = line.split()
                    for part in parts:
                        if re.match(r'S\d+\.\d+', part):
                            print(f"Section extraction from drawing area: {part}")
                            return part
        print(f"Section extraction: N/A from text ending: {text[-100:]}")
        return 'N/A'

    def _reconstruct_missing_metadata(self, answers: Dict, structured_payload: Dict) -> Dict[str, Any]:
        enhanced_answers = {}
        for qid, answer_data in answers.items():
            if isinstance(answer_data, dict):
                answer_text = answer_data.get('answer', 'Not Found')

                # Try to find which page this answer likely came from
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
                    'source_pdf': 'unknown',
                    'page': 'unknown',
                    'confidence': 0,
                    'source': 'fallback'
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

            # Simple text matching - look for key phrases
            if answer_lower in page_text:
                score = len(answer_text)
                if score > best_score:
                    best_score = score
                    best_match = page

            # Also check for partial matches of technical terms
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
- All 25 questions required (Q1-Q25)
- If not found: "Not Found", "unknown", 0
- When structured_data has a match, use confidence 90%+

Process these 25 questions:
1. What building code and year is referenced? (look in structured_data.building_codes)
2. Is an ASCE 7 standard mentioned? Which version? (look for ASCE 7-XX)
3. What are the exterior wall deflection limits? (look in structured_data.load_requirements for L/XXX)
4. What is the interior wall deflection limit?
5. What is the floor joist framing deflection limit?
6. What is the roof rafter framing deflection limit?
7. What is the ceiling joist framing deflection limit?
8. What is the maximum primary structure vertical deflection due to live load?
9. What is the basic wind speed (in mph)? (look in structured_data.load_requirements)
10. What is the building risk category (e.g., I, II, III)?
11. What is the exposure category (e.g., B, C)?
12. What is the internal pressure coefficient (GCpi)?
13. What is the roof live load? (look for XX psf)
14. What is the roof dead load?
15. What is the ground snow load (Pg)?
16. What is the snow load importance factor (Is)?
17. What is the snow load exposure factor (Ce)?
18. What is the thermal factor (Ct)?
19. What is the flat roof snow load (Pf)?
20. What is the seismic design category (e.g., A, B, C)?
21. What is the seismic importance factor (Ie)?
22. What is the component importance factor (Ip)?
23. What is the site class (e.g., D, E, F)?
24. What is the value of Sds?
25. What is the value of Sd1?

REMEMBER: ONLY JSON output. Prioritize structured_data matches. Extract page_number and source_pdf."""

    async def process(self, ocr_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.llm_registry:
            raise Exception("LLM Registry not available")
        try:
            print(f"QA Agent processing {len(self.questions)} questions")
            filtered_pages = ocr_data['filtered_pages']['matching_pages']

            if not filtered_pages:
                print("No filtered pages found, cannot proceed")
                return {'success': False, 'agent': self.name,
                        'error': 'No relevant pages found for processing',
                        'qa_results': {}}
            for page in filtered_pages:
                page['section'] = self._extract_section(page)
                if 'ocr_engine' not in page:
                    page['ocr_engine'] = 'aws_textract'
                if 'confidence_avg' not in page:
                    page['confidence_avg'] = page.get('confidence', 0.9)
            structured_payload = {"pages_with_metadata": filtered_pages,
                                  "document_info": ocr_data.get('document_info', {}),
                                  "source_mapping": ocr_data.get('source_mapping', [])}

            print(f"Processing {len(filtered_pages)} pages with structured data")
            answers = await self._process_with_metadata(structured_payload)
            enhanced_answers = await self._map_coordinates_with_metadata(answers, structured_payload)

            coord_found = sum(1 for ans in enhanced_answers.values()
                              if isinstance(ans, dict) and ans.get('coordinates') != 'N/A')
            print(f"Coordinate mapping: {coord_found}/{len(enhanced_answers)} answers have coordinates")

            return {'success': True, 'agent': self.name,
                    'qa_results': enhanced_answers,
                    'questions_processed': len(self.questions),
                    'pages_used': len(filtered_pages),
                    'coordinates_found': coord_found}

        except Exception as e:
            raise Exception(f"QA processing failed: {e}")

    async def _process_with_metadata(self, structured_payload: Dict) -> Dict[str, Any]:
        # Include structured_data (regex pattern matches) and table data in payload
        # These contain pre-extracted engineering values that the LLM should prioritize
        payload_pages = []
        for page in structured_payload['pages_with_metadata']:
            page_entry = {
                'extracted_text': page.get('extracted_text', ''),
                'page_number': page.get('page_number'),
                'source_pdf': page.get('source_pdf'),
                'section': page.get('section', 'N/A'),
            }
            # Include regex-extracted structured data (building codes, loads, etc.)
            structured_data = page.get('structured_data', {})
            if structured_data:
                page_entry['structured_data'] = structured_data
            # Include table elements (gridding results)
            table_elements = page.get('table_elements', [])
            if table_elements:
                page_entry['table_data'] = [
                    {'text': t.get('text', ''), 'confidence': t.get('confidence', 0)}
                    for t in table_elements[:20]  # Limit to avoid token overflow
                ]
            payload_pages.append(page_entry)

        # Log what structured data we found for debugging
        all_structured = {}
        for p in payload_pages:
            for cat, vals in p.get('structured_data', {}).items():
                if cat not in all_structured:
                    all_structured[cat] = []
                all_structured[cat].extend(vals if isinstance(vals, list) else [vals])
        if all_structured:
            print(f"Structured data found across all pages: {json.dumps({k: v[:5] for k, v in all_structured.items()}, default=str)}")
        else:
            print("No structured data found from pattern extraction")

        minimal_payload = {'pages_with_metadata': payload_pages}
        json_payload = json.dumps(minimal_payload, indent=2)
        print(f"LLM payload size: {len(json_payload)} chars (~{len(json_payload)//4} tokens)")

        enhanced_prompt = self.get_enhanced_system_prompt()

        try:
            answers = self.llm_registry.answer_questions_with_enhanced_prompt(
                json_payload, self.questions, enhanced_prompt)

            if all(isinstance(ans, dict) and 'source_pdf' in ans and 'page' in ans
                   for ans in answers.values()):
                return answers
            else:
                print("JSON response missing required fields, reconstructing...")
                return self._reconstruct_missing_metadata(answers, structured_payload)

        except Exception as e:
            print(f"Enhanced prompt failed: {e}, using fallback")
            combined_text = "\n\n".join(
                f"[Source: {page.get('source_pdf', 'unknown')}, Page: {page.get('page_number', 'unknown')}]\n{page.get('extracted_text', '')}"
                for page in payload_pages)
            fallback_answers = self.llm_registry.answer_questions_with_fallback(combined_text, self.questions)
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
                    matching_pages = [page for page in structured_payload['pages_with_metadata']
                                      if page.get('page_number') == page_num_int
                                      and page.get('source_pdf') == source_pdf]
                    if matching_pages:
                        section = matching_pages[0].get('section', 'N/A')
                except (ValueError, KeyError):
                    pass

                coordinates = self._find_coordinates_with_source(answer_text, source_pdf, page_number,
                                                                 structured_payload)
                enhanced_answers[qid] = {'answer': answer_text,
                                         'source_pdf': source_pdf,
                                         'page': page_number,
                                         'confidence': confidence,
                                         'section': section,
                                         'coordinates': coordinates,
                                         'coordinates_display': self._format_coordinates(coordinates),
                                         'has_coordinates': coordinates != 'N/A',
                                         'ocr_engine': 'aws_textract'}
            else:
                enhanced_answers[qid] = {'answer': str(answer_data) if answer_data else 'Not Found',
                                         'source_pdf': 'unknown', 'page': 'unknown', 'confidence': '0%',
                                         'section': 'N/A', 'coordinates': 'N/A', 'coordinates_display': 'N/A',
                                         'has_coordinates': False, 'ocr_engine': 'aws_textract'}
        return enhanced_answers

    def _find_coordinates_with_source(self, answer_text: str, source_pdf: str, page_number: str,
                                      structured_payload: Dict) -> Any:
        if answer_text == "Not Found" or page_number == "unknown":
            return "N/A"
        try:
            page_num_int = int(page_number)
            matching_pages = [page for page in structured_payload['pages_with_metadata']
                              if page.get('page_number') == page_num_int
                              and page.get('source_pdf') == source_pdf]
            if not matching_pages:
                return "N/A"
            page_data = matching_pages[0]
            if hasattr(self, 'coordinate_mapper'):
                result = self.coordinate_mapper.find_answer_coordinates(answer_text, [page_data], page_num_int)
                if result and 'bounding_box' in result:
                    return result['bounding_box']
        except (ValueError, KeyError) as e:
            print(f"Coordinate mapping error: {e}")
        return "N/A"

    def _format_coordinates(self, coordinates: Any) -> str:
        if coordinates == "N/A" or not coordinates:
            return "N/A"
        if isinstance(coordinates, dict):
            return f"({coordinates.get('x', 0)}, {coordinates.get('y', 0)}, {coordinates.get('width', 0)}, {coordinates.get('height', 0)})"
        return str(coordinates)
