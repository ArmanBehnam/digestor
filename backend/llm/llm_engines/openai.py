# llm/llm_engines/openai.py

from typing import Dict, List, Any
import re
import logging
import openai
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import json

from .base import BaseLLMEngine

logger = logging.getLogger(__name__)


class OpenAIEngine(BaseLLMEngine):
    def __init__(self, config=None):
        super().__init__(engine_name="openai_gpt4o", priority=10)

        self.api_key = None
        self.model = 'gpt-4o'
        self.timeout = 60
        self.client = None

        if config and 'openai_api_key' in config:
            self.initialize(config)

    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            api_key = config.get('openai_api_key')
            if not api_key:
                logger.error("OpenAI API key not found in config")
                return False

            self.api_key = api_key
            self.model = config.get('model', 'gpt-4o')
            self.timeout = config.get('timeout', 60)

            self.client = openai.OpenAI(api_key=api_key, timeout=self.timeout, http_client=httpx.Client(verify=False))

            # Skip test API call — wastes tokens and can fail on rate limit
            # The real call in answer_questions will handle errors gracefully
            self.is_available = True
            logger.info("OpenAI GPT-4o engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenAI engine: {e}")
            self.last_error = e
            self.is_available = False
            return False

    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        if not self.is_available or not self.client:
            raise RuntimeError("OpenAI engine not available")

        try:
            prompt = self._generate_coordinate_aware_prompt(page_text, questions, prompt_engineer)

            messages = [{"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."}, {"role": "user", "content": prompt}]

            response = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0.2, max_tokens=2000)

            content = response.choices[0].message.content
            answers = self._parse_response(content, questions)

            self._record_request(success=True)
            return answers

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def _generate_coordinate_aware_prompt(self, page_text: str, questions: List[str], prompt_engineer=None) -> str:
        if prompt_engineer and prompt_engineer.enabled:
            try:
                base_prompt = prompt_engineer.optimize_prompt(page_text, questions)
                return self._add_coordinate_instructions(base_prompt, questions)
            except Exception as e:
                logger.warning(f"Prompt engineering failed, using coordinate-aware prompt: {e}")

        questions_text = "\n".join([f"Q{i + 1}. {q}" for i, q in enumerate(questions)])

        return f'''You are a structural and seismic engineering document analyzer. Extract information with precise text matching for coordinate tracking.
**CRITICAL INSTRUCTION**: When you find an answer, quote the EXACT text from the document that contains the answer. This is essential for location tracking.

**Document Text:**
{page_text}

**Questions to Answer:**
{questions_text}

**Response Format**: For each question, respond with:
"Q1. [EXACT_TEXT_FROM_DOCUMENT] | Page: [page number or N/A] | Confidence: [0-100]%"

**Key Requirements:**
1. **EXACT TEXT MATCHING**: Quote the exact phrase from the document that contains your answer
2. **NO PARAPHRASING**: Use the document's exact words, even if they seem awkward
3. **COMPLETE PHRASES**: Include enough context so the text can be found in the document
4. **TECHNICAL PRECISION**: Preserve all technical terms, numbers, and units exactly as written

**Examples of Good Responses:**
- Q1. Grade 50 steel per ASTM A992 | Page: 3 | Confidence: 95%
- Q2. Basic wind speed of 90 mph | Page: 1 | Confidence: 90%
- Q3. L/240 for live load deflection | Page: 2 | Confidence: 85%

**Search Strategies:**
- **Building Codes**: Look for "IBC", "NYSBC", "ASCE 7-XX" with years
- **Deflection**: Search for "L/240", "L/360", "deflection criteria"
- **Wind/Snow Loads**: Find values with "mph", "psf", "ground snow load"
- **Materials**: Look for "Grade", "ASTM", gauge measurements
- **Seismic**: Search for "Sds", "Sd1", "site class", "seismic design"

Remember: Quote exactly from the document to enable precise coordinate mapping.'''

    def _add_coordinate_instructions(self, base_prompt: str, questions: List[str]) -> str:
        coordinate_enhancement = """**COORDINATE MAPPING REQUIREMENT**:
For accurate location tracking, always quote the EXACT text from the document that contains your answer. Do not paraphrase or summarize - use the document's precise wording.

**Format**: Q[number]. [EXACT_QUOTED_TEXT] | Page: [page] | Confidence: [%]%"""

        if "**Questions to Answer:**" in base_prompt:
            return base_prompt.replace("**Questions to Answer:**",
                                     coordinate_enhancement + "\n\n**Questions to Answer:**")
        else:
            return base_prompt + coordinate_enhancement

    def _parse_response(self, content: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        answers = {}
        for i, question in enumerate(questions):
            qid = f"Q{i+1}"
            patterns = [
                rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*Confidence:\s*(\d+)%",
                rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*(\d+)%",
                rf"{qid}\.?\s*(.*?)\s*(?=Q\d+\.|\Z)"]

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
                        page_info = "N/A"
                        confidence = "50"

                    answer = self._clean_answer_text(answer, question)

                    answer_lower = answer.lower().strip()
                    is_not_found = (
                        answer_lower in ('n/a', 'na', 'not found', 'none', 'not applicable', '-', '--', '')
                        or any(phrase in answer_lower for phrase in [
                            'not found', 'not specified', 'not mentioned', 'not explicitly',
                            'does not reference', 'no information', 'not provided',
                            'not stated', 'not indicated', 'cannot be determined', 'not given',
                            'not available', 'unable to locate', 'unable to determine',
                            'unable to find', 'no specific mention', 'not included',
                            'does not contain', 'does not specify', 'does not mention',
                            'does not include', 'not referenced', 'not addressed',
                            'no mention', 'no reference', 'not discussed', 'not identified',
                        ])
                    )

                    if is_not_found:
                        final_answer = "Not Found"
                        final_confidence = 0
                    else:
                        final_answer = answer.strip()
                        final_confidence = int(confidence) if confidence.isdigit() else 50

                    answers[qid] = {'answer': final_answer, 'page': page_info if page_info != 'N/A' else 'unknown',
                        'confidence': final_confidence,
                        'source': self.engine_name,
                        'raw_response': answer}
                    match_found = True
                    break

            if not match_found:
                answers[qid] = {'answer': "Not Found",
                                'page': 'unknown',
                                'confidence': 0,
                                'source': self.engine_name, 'raw_response': ""}
        return answers

    def _clean_answer_text(self, answer: str, question: str) -> str:
        if answer.lower().startswith(question.lower()[:20]):
            answer = answer[len(question):].strip(" \n:-*")
        answer = re.sub(r'^(The document states that|According to the document|The text mentions)\s*', '', answer, flags=re.IGNORECASE)
        answer = re.sub(r'\s+', ' ', answer).strip()
        return answer

    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        if not self.is_available or not self.client:
            raise RuntimeError("OpenAI engine not available")
        try:
            pages_data = ocr_result.get('pages') or ocr_result.get('filtered_pages_only', [])
            combined_text = ""
            for page_num in relevant_pages:
                if page_num < len(pages_data):
                    page_data = pages_data[page_num]
                    page_text = page_data.get('content', '') or page_data.get('extracted_text', '')
                    page_number = page_data.get('page_number', page_num + 1)
                    combined_text += f"\\n--- Page {page_number} ---\\n{page_text}\\n"
            prompt = self._generate_coordinate_aware_prompt(combined_text, [question])
            messages = [{"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."}, {"role": "user", "content": prompt}]
            response = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0.2, max_tokens=1500)
            content = response.choices[0].message.content
            answers = self._parse_response(content, [question])
            self._record_request(success=True)
            return answers.get('Q1', {'answer': 'Not Found','page': 'N/A', 'confidence': 0, 'source': self.engine_name, 'raw_response': ""})
        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def answer_questions_with_custom_prompt(self, page_text: str, questions: List[str], custom_prompt: str) -> Dict[
        str, Dict[str, Any]]:
        if not self.is_available or not self.client:
            raise RuntimeError("OpenAI engine not available")
        try:
            full_prompt = f"{custom_prompt}\n\n**JSON DATA:**\n{page_text}"
            estimated_tokens = len(full_prompt) // 3
            # Reject payloads that exceed GPT-4o's 128K context
            if estimated_tokens > 110000:
                raise RuntimeError(f"Payload too large for GPT-4o: ~{estimated_tokens} tokens (max ~110K)")
            model_to_use = self.model
            max_tokens = 2000

            print(f"Using model: {model_to_use} (estimated tokens: {estimated_tokens})")

            messages = [{"role": "system",
                 "content": "You are a helpful assistant for structural and seismic engineering documents. You must respond only in valid JSON format."},
                {"role": "user", "content": full_prompt}]

            response = self.client.chat.completions.create(model=model_to_use,
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"})
            content = response.choices[0].message.content
            answers = self._parse_response_json(content, questions)
            self._record_request(success=True)
            return answers
        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def _parse_response_json(self, content: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        answers = {}
        try:
            json_response = json.loads(content)
            if isinstance(json_response, dict):
                for qid, answer_data in json_response.items():
                    if isinstance(answer_data, dict):
                        confidence_str = str(answer_data.get('confidence', '50%')).replace('%', '')
                        answers[qid] = {'answer': answer_data.get('answer', 'Not Found'),
                            'page': answer_data.get('page_number', 'unknown'),
                            'confidence': int(confidence_str) if confidence_str.isdigit() else 50,
                            'source': self.engine_name,
                            'source_pdf': answer_data.get('source_pdf', 'unknown')}
                return answers
        except (json.JSONDecodeError, KeyError, ValueError):
            print("JSON parsing failed, falling back to text parsing")
            pass
        return self._parse_response(content, questions)
