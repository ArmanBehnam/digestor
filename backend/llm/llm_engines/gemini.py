# llm/llm_engines/gemini.py
"""
Gemini 2.0 Flash LLM engine — 1M token context window.
Primary engine for large documents that exceed GPT-4o's 128K limit.
"""

import json
import re
import logging
import os
from typing import Dict, List, Any

from .base import BaseLLMEngine

logger = logging.getLogger(__name__)


class GeminiEngine(BaseLLMEngine):
    """Google Gemini 2.0 Flash for text-based QA with massive context."""

    def __init__(self):
        super().__init__("gemini_flash", priority=5)  # Highest priority (lowest number)
        self.client = None
        self.model_name = "gemini-2.0-flash"

    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            api_key = config.get('gemini_api_key') or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("Gemini API key not found in config or environment")
                return False

            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel(self.model_name)
            except ImportError:
                logger.error("google-generativeai package not installed. Run: pip install google-generativeai")
                return False

            # Skip test call — real call will handle errors
            self.is_available = True
            logger.info(f"Gemini Flash engine initialized successfully (model: {self.model_name}, context: 1M tokens)")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Gemini engine: {e}")
            self.last_error = e
            self.is_available = False
            return False

    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        if not self.is_available or not self.client:
            raise RuntimeError("Gemini engine not available")

        try:
            prompt = self._generate_prompt(page_text, questions, prompt_engineer)

            response = self.client.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 4096,
                    # Note: NOT using response_mime_type=application/json because
                    # Gemini still returns malformed JSON with large payloads
                },
            )

            answers = self._parse_response(response.text, questions)
            self._record_request(success=True)
            return answers

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def answer_questions_with_custom_prompt(self, page_text: str, questions: List[str], custom_prompt: str) -> Dict[str, Dict[str, Any]]:
        """Answer questions using a custom enhanced prompt."""
        if not self.is_available or not self.client:
            raise RuntimeError("Gemini engine not available")

        try:
            full_prompt = f"{custom_prompt}\n\n**JSON DATA:**\n{page_text}"
            estimated_tokens = len(full_prompt) // 3
            print(f"Using model: {self.model_name} (estimated tokens: {estimated_tokens})")

            response = self.client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 4096,
                    # Note: NOT using response_mime_type=application/json because
                    # Gemini still returns malformed JSON with large payloads
                },
            )

            answers = self._parse_response_json(response.text, questions)
            self._record_request(success=True)
            return answers

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        if not self.is_available or not self.client:
            raise RuntimeError("Gemini engine not available")

        try:
            pages_data = ocr_result.get('pages') or ocr_result.get('filtered_pages_only', [])
            combined_text = ""
            for page_num in relevant_pages:
                if page_num < len(pages_data):
                    page_data = pages_data[page_num]
                    page_text = page_data.get('content', '') or page_data.get('extracted_text', '')
                    page_number = page_data.get('page_number', page_num + 1)
                    combined_text += f"\n--- Page {page_number} ---\n{page_text}\n"

            prompt = self._generate_prompt(combined_text, [question])

            response = self.client.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 2048,
                },
            )

            answers = self._parse_response(response.text, [question])
            self._record_request(success=True)
            return answers.get('Q1', {
                'answer': 'Not Found',
                'page': 'N/A',
                'confidence': 0,
                'source': self.engine_name
            })

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def _generate_prompt(self, page_text: str, questions: List[str], prompt_engineer=None) -> str:
        if prompt_engineer and prompt_engineer.enabled:
            try:
                return prompt_engineer.optimize_prompt(page_text, questions)
            except Exception:
                pass

        questions_text = "\n".join([f"Q{i + 1}. {q}" for i, q in enumerate(questions)])

        return f'''You are a structural and seismic engineering document analyzer. Extract information with precise text matching.

**CRITICAL INSTRUCTION**: When you find an answer, quote the EXACT text from the document that contains the answer.

**Document Text:**
{page_text}

**Questions to Answer:**
{questions_text}

**Response Format (JSON)**:
Return a JSON object where each key is a question ID (Q1, Q2, etc.) and each value has:
- "answer": the exact extracted value or "Not Found"
- "page_number": the page number where the answer was found, or "unknown"
- "confidence": confidence percentage as a string (e.g., "90%")
- "source_pdf": "unknown"

Example:
{{"Q1": {{"answer": "IBC 2018", "page_number": "3", "confidence": "95%", "source_pdf": "unknown"}}}}

**Search Strategies:**
- **Building Codes**: Look for "IBC", "NYSBC", "ASCE 7-XX" with years
- **Deflection**: Search for "L/240", "L/360", "deflection criteria"
- **Wind/Snow Loads**: Find values with "mph", "psf", "ground snow load"
- **Materials**: Look for "Grade", "ASTM", gauge measurements
- **Seismic**: Search for "Sds", "Sd1", "site class", "seismic design category"

Answer each question precisely. If you cannot find the answer, set answer to "Not Found" with confidence "0%".'''

    def _parse_response(self, content: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse text-based response (Q1. answer | Page: X | Confidence: Y%)."""
        # Try JSON first (Gemini usually returns JSON)
        try:
            result = self._parse_response_json(content, questions)
            if result and len(result) >= len(questions) // 2:
                return result
        except Exception as e:
            logger.debug(f"Gemini JSON parse failed, falling back to text parse: {e}")

        answers = {}
        for i, question in enumerate(questions):
            qid = f"Q{i + 1}"
            patterns = [
                rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*Confidence:\s*(\d+)%",
                rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*(\d+)%",
                rf"{qid}\.?\s*(.*?)\s*(?=Q\d+\.|\Z)",
            ]

            match_found = False
            for pattern in patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    if len(match.groups()) >= 3:
                        answer = match.group(1).strip()
                        page_info = match.group(2).strip()
                        confidence = match.group(3).strip()
                    else:
                        answer = match.group(1).strip()
                        page_info = "unknown"
                        confidence = "50"

                    answer_lower = answer.lower().strip()
                    is_not_found = answer_lower in ('n/a', 'na', 'not found', 'none', 'not applicable', '-', '--', '') or \
                        any(phrase in answer_lower for phrase in ['not found', 'not specified', 'not mentioned', 'not available'])

                    answers[qid] = {
                        'answer': "Not Found" if is_not_found else answer.strip(),
                        'page': page_info if page_info != 'N/A' else 'unknown',
                        'confidence': 0 if is_not_found else (int(confidence) if confidence.isdigit() else 50),
                        'source': self.engine_name,
                        'raw_response': answer,
                    }
                    match_found = True
                    break

            if not match_found:
                answers[qid] = {
                    'answer': "Not Found", 'page': 'unknown',
                    'confidence': 0, 'source': self.engine_name, 'raw_response': "",
                }

        return answers

    def _repair_json(self, raw: str) -> str:
        """Attempt to repair common Gemini JSON issues."""
        # Remove trailing commas before } or ]
        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        # Fix unquoted keys (e.g., Q1: -> "Q1":)
        raw = re.sub(r'(?<!["\w])(\w+)\s*:', r'"\1":', raw)
        # Fix single quotes to double quotes
        raw = raw.replace("'", '"')
        # Truncate at the last valid closing brace if JSON is cut off
        depth = 0
        last_valid = -1
        for i, c in enumerate(raw):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    last_valid = i
                    break
        if last_valid > 0:
            raw = raw[:last_valid + 1]
        return raw

    def _parse_response_json(self, content: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse JSON response from Gemini with robust error recovery."""
        answers = {}

        # Extract JSON from potential markdown code block
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            content = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group()

        # Try parsing, then try repair if it fails
        try:
            json_response = json.loads(content)
        except json.JSONDecodeError:
            repaired = self._repair_json(content)
            json_response = json.loads(repaired)
        if isinstance(json_response, dict):
            for qid, answer_data in json_response.items():
                if isinstance(answer_data, dict):
                    confidence_str = str(answer_data.get('confidence', '50%')).replace('%', '')
                    # Normalize page: ensure 1-indexed, handle "0", "unknown", etc.
                    raw_page = answer_data.get('page_number', answer_data.get('page', 'unknown'))
                    try:
                        page_int = int(raw_page)
                        if page_int <= 0:
                            raw_page = 'unknown'
                        else:
                            raw_page = str(page_int)
                    except (ValueError, TypeError):
                        if raw_page in (None, '', 'N/A', 'n/a', 'null'):
                            raw_page = 'unknown'

                    answer_text = answer_data.get('answer', 'Not Found')
                    # Detect "not found" variants
                    if answer_text and answer_text.lower().strip() in (
                        'not found', 'n/a', 'na', 'none', 'not available',
                        'not specified', 'not mentioned', 'not provided', ''):
                        answer_text = 'Not Found'
                        confidence_str = '0'

                    answers[qid] = {
                        'answer': answer_text,
                        'page': raw_page,
                        'confidence': int(confidence_str) if confidence_str.isdigit() else 50,
                        'source': self.engine_name,
                        'source_pdf': answer_data.get('source_pdf', 'unknown'),
                    }

        # Validate we have all expected answers
        for i in range(len(questions)):
            qid = f"Q{i + 1}"
            if qid not in answers:
                answers[qid] = {
                    'answer': 'Not Found', 'page': 'unknown',
                    'confidence': 0, 'source': self.engine_name,
                }

        return answers
