# llm/coordinate_mapper.py

import re
from typing import Dict, List, Any, Optional, Tuple
from rapidfuzz import fuzz
import logging
import unicodedata

logger = logging.getLogger(__name__)


class CoordinateMapper:
    def __init__(self, similarity_threshold: float = 80.0):
        self.similarity_threshold = similarity_threshold

    def find_answer_coordinates(self, answer_text: str, page_results: List[Dict],
                                page_number: int = None) -> Optional[Dict[str, Any]]:

        if not answer_text or answer_text.lower().strip() in ['not found', 'n/a', 'nan']:
            return None

        clean_answer = self._clean_text_for_matching(answer_text)
        if not clean_answer:
            return None

        best_match = None
        best_score = 0
        for page_data in page_results:
            if page_number and page_data.get('page_number') != page_number:
                continue

            page_text = page_data.get('extracted_text', '')
            if not page_text:
                continue

            exact_match = self._find_exact_match(clean_answer, page_text, page_data)
            if exact_match:
                exact_match['match_type'] = 'exact'
                exact_match['confidence_score'] = 100.0
                return exact_match

            fuzzy_match = self._find_fuzzy_match(clean_answer, page_text, page_data)
            if fuzzy_match and fuzzy_match['confidence_score'] > best_score:
                best_match = fuzzy_match
                best_score = fuzzy_match['confidence_score']

        return best_match if best_score >= self.similarity_threshold else None

    def _clean_text_for_matching(self, text: str) -> str:
        if not text:
            return ""
        clean_text = text.strip()
        if clean_text.startswith('"') and clean_text.endswith('"'):
            clean_text = clean_text[1:-1]
        clean_text = re.sub(r'^(The\s+|A\s+|An\s+)', '', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s*\(.*?\)\s*$', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if len(clean_text) > 50:
            words = clean_text.split()
            if len(words) > 5:
                clean_text = ' '.join(words[:5])

        return clean_text

    def _find_exact_match(self, answer_text: str, page_text: str, page_data: Dict) -> Optional[Dict[str, Any]]:
        page_text_lower = page_text.lower()
        answer_lower = answer_text.lower()

        start_pos = 0
        matches = []

        while True:
            pos = page_text_lower.find(answer_lower, start_pos)
            if pos == -1:
                break

            matches.append({
                'start_pos': pos,
                'end_pos': pos + len(answer_text),
                'matched_text': page_text[pos:pos + len(answer_text)]
            })
            start_pos = pos + 1

        if not matches:
            return None
        match = matches[0]
        coords = self._estimate_coordinates(match, page_text, page_data)

        if coords:
            return {'page_number': page_data.get('page_number', 1),
                'bounding_box': coords,
                'matched_text': match['matched_text'],
                'match_type': 'exact',
                'confidence_score': 100.0,
                'text_position': {
                    'start': match['start_pos'],
                    'end': match['end_pos']}}

        return None

    def _find_fuzzy_match(self, answer_text: str, page_text: str, page_data: Dict) -> Optional[Dict[str, Any]]:
        best_match = None
        best_ratio = 0

        answer_words = [w for w in answer_text.split() if len(w) > 3]
        if not answer_words:
            answer_words = answer_text.split()

        text_words = page_text.split()

        for window_size in [len(answer_words), len(answer_words) + 1, len(answer_words) - 1]:
            if window_size <= 0 or window_size > len(text_words):
                continue

            for i in range(len(text_words) - window_size + 1):
                window_text = ' '.join(text_words[i:i + window_size])
                ratio = fuzz.ratio(answer_text.lower(), window_text.lower())

                if ratio > best_ratio and ratio >= self.similarity_threshold:
                    best_ratio = ratio

                    start_pos = page_text.find(window_text)
                    if start_pos != -1:
                        best_match = {'start_pos': start_pos,
                            'end_pos': start_pos + len(window_text),
                            'matched_text': window_text,
                            'confidence_score': ratio}
        if not best_match:
            return None
        coords = self._estimate_coordinates(best_match, page_text, page_data)

        if coords:
            return {'page_number': page_data.get('page_number', 1), 'bounding_box': coords,
                'matched_text': best_match['matched_text'], 'match_type': 'fuzzy',
                'confidence_score': best_match['confidence_score'],
                'text_position': {'start': best_match['start_pos'], 'end': best_match['end_pos']}}

        return None

    def _estimate_coordinates(self, match: Dict, page_text: str, page_data: Dict) -> Optional[Dict[str, float]]:
        try:
            page_width = page_data.get('page_width', 1000)
            page_height = page_data.get('page_height', 1000)

            total_chars = len(page_text)
            start_ratio = match['start_pos'] / total_chars if total_chars > 0 else 0
            length_ratio = len(match['matched_text']) / total_chars if total_chars > 0 else 0

            text_before = page_text[:match['start_pos']]
            line_breaks = text_before.count('\n')
            estimated_lines = max(page_text.count('\n'), 20)  # Minimum 20 lines

            y_ratio = line_breaks / estimated_lines if estimated_lines > 0 else 0.5

            last_newline = text_before.rfind('\n')
            chars_in_line = match['start_pos'] - last_newline - 1 if last_newline != -1 else match['start_pos']

            next_newline = page_text.find('\n', match['start_pos'])
            line_end = next_newline if next_newline != -1 else len(page_text)
            line_length = line_end - (last_newline + 1) if last_newline != -1 else line_end

            x_ratio = chars_in_line / max(line_length, 1)

            return {'x': int(x_ratio * page_width), 'y': int(y_ratio * page_height),
                'width': int(length_ratio * page_width * 10), 'height': int(page_height * 0.03)}

        except Exception as e:
            logger.warning(f"Coordinate estimation failed: {e}")
            return None

    def map_multiple_answers(self, qa_results: Dict[str, Dict], page_results: List[Dict]) -> Dict[str, Dict]:
        enhanced_results = {}

        for question_id, answer_data in qa_results.items():
            if not isinstance(answer_data, dict):
                enhanced_results[question_id] = answer_data
                continue

            answer_text = answer_data.get('answer', '')
            page_number = answer_data.get('page')

            coordinates = self.find_answer_coordinates(answer_text, page_results, page_number)
            enhanced_answer = answer_data.copy()

            matching_page = next((p for p in page_results if p.get('page_number') == page_number), None)
            if not matching_page and page_number in ['unknown', 1, '1']:
                clean = re.sub(r'[^\x00-\x7F]+', ' ', answer_text.strip('"\''))
                clean = ' '.join(clean.split()).lower()
                matching_page = next((p for p in page_results if clean[:50] in p.get('extracted_text', '').lower()), None)
            if matching_page:
                enhanced_answer['page'] = matching_page.get('page_number', 1)
                enhanced_answer['ocr_engine'] = matching_page.get('ocr_engine', 'aws_textract')
                enhanced_answer['ocr_confidence'] = matching_page.get('confidence_avg', 0.0)
                enhanced_answer['section'] = matching_page.get('section', 'N/A')
                if coordinates:
                    bbox = coordinates.get('bounding_box', {})
                    enhanced_answer['coordinates_display'] = f"({bbox.get('x', 0)},{bbox.get('y', 0)})"
                else:
                    enhanced_answer['coordinates_display'] = 'N/A'

            if coordinates:
                enhanced_answer['coordinates'] = coordinates
                enhanced_answer['has_coordinates'] = True
            else:
                enhanced_answer['has_coordinates'] = False
            enhanced_results[question_id] = enhanced_answer
        return enhanced_results