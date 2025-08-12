"""
OpenAI GPT-4o Engine for LLM processing.

Primary LLM engine using OpenAI's GPT-4o model.
"""

from typing import Dict, List, Any
import re
import logging
import openai
import ssl
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .base import BaseLLMEngine

logger = logging.getLogger(__name__)


class OpenAIEngine(BaseLLMEngine):
    def __init__(self, config=None):
        # Call parent constructor with required parameters
        super().__init__(engine_name="openai_gpt4o", priority=10)

        # Initialize attributes with defaults
        self.api_key = None
        self.model = 'gpt-4o'
        self.timeout = 60
        self.client = None

        # Try to initialize immediately if config has the API key
        if config and 'openai_api_key' in config:
            self.initialize(config)

    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize OpenAI client."""
        try:
            api_key = config.get('openai_api_key')
            if not api_key:
                logger.error("OpenAI API key not found in config")
                return False

            # Set instance variables
            self.api_key = api_key
            self.model = config.get('model', 'gpt-4o')
            self.timeout = config.get('timeout', 60)

            self.client = openai.OpenAI(
                api_key=api_key,  # Fix: Use local api_key variable
                timeout=self.timeout,
                http_client=httpx.Client(verify=False)
            )

            # Test the connection with a simple request
            test_response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )

            self.is_available = True
            logger.info(f"OpenAI GPT-4o engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenAI engine: {e}")
            self.last_error = e
            self.is_available = False
            return False

    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        """Answer multiple questions for a single page using OpenAI."""
        if not self.is_available or not self.client:
            raise RuntimeError(f"OpenAI engine not available")

        try:
            prompt = self.generate_prompt(page_text, questions, prompt_engineer)

            messages = [
                {"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500
            )

            content = response.choices[0].message.content
            answers = self._parse_response(content, questions)

            self._record_request(success=True)
            return answers

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        """Answer a single question using OCR result data."""
        if not self.is_available or not self.client:
            raise RuntimeError(f"OpenAI engine not available")

        try:
            # Get the correct pages data - handle both formats
            pages_data = ocr_result.get('pages') or ocr_result.get('filtered_pages_only', [])

            # Combine text from relevant pages
            combined_text = ""
            for page_num in relevant_pages:
                if page_num < len(pages_data):
                    page_data = pages_data[page_num]
                    # Handle both 'content' and 'extracted_text' keys
                    page_text = page_data.get('content', '') or page_data.get('extracted_text', '')
                    page_number = page_data.get('page_number', page_num + 1)
                    combined_text += f"\\n--- Page {page_number} ---\\n{page_text}\\n"

            prompt = self.generate_prompt(combined_text, [question])

            messages = [
                {"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500
            )

            content = response.choices[0].message.content
            answers = self._parse_response(content, [question])

            self._record_request(success=True)

            # Return the single answer
            return answers.get('Q1', {
                'answer': 'Not Found',
                'page': 'N/A',
                'confidence': 0,
                'source': self.engine_name
            })

        except Exception as e:
            self._record_request(success=False, error=e)
            raise e

    def _parse_response(self, content: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse LLM response into structured answers."""
        answers = {}

        for i, question in enumerate(questions):
            qid = f"Q{i+1}"

            # Look for pattern: Q1. answer | Page: X | Confidence: Y%
            pattern = rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*Confidence:\s*(\d+)%"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if match:
                answer = match.group(1).strip()
                page_info = match.group(2).strip()
                confidence = match.group(3).strip()

                # Clean up the answer
                if answer.lower().startswith(question.lower()[:20]):
                    answer = answer[len(question):].strip(" \\n:-*")

                # Check if the answer indicates information was not found
                is_not_found = any(phrase in answer.lower() for phrase in [
                    'not found', 'not specified', 'not mentioned', 'not explicitly',
                    'does not reference', 'no information', 'not provided',
                    'not stated', 'not indicated', 'not given', 'cannot be determined'
                ])

                if is_not_found:
                    final_answer = "Not Found"
                    final_confidence = 0
                else:
                    final_answer = answer.strip()
                    final_confidence = int(confidence) if confidence.isdigit() else 50

                answers[qid] = {
                    'answer': final_answer,
                    'page': page_info if page_info != 'N/A' else 1,
                    'confidence': final_confidence,
                    'source': self.engine_name
                }
            else:
                # Fallback to simple format if structured parsing fails
                simple_pattern = rf"{qid}\.?\s*(.*?)\s*(?=Q\d+\.|\Z)"
                simple_match = re.search(simple_pattern, content, re.DOTALL | re.IGNORECASE)
                if simple_match:
                    answer = simple_match.group(1).strip()

                    # Check if the answer indicates information was not found
                    is_not_found = any(phrase in answer.lower() for phrase in [
                        'not found', 'not specified', 'not mentioned', 'not explicitly',
                        'does not reference', 'no information', 'not provided'
                    ])

                    answers[qid] = {
                        'answer': "Not Found" if is_not_found else answer,
                        'page': 1,
                        'confidence': 0 if is_not_found else 50,
                        'source': self.engine_name
                    }
                else:
                    answers[qid] = {
                        'answer': "Not Found",
                        'page': 1,
                        'confidence': 0,
                        'source': self.engine_name
                    }

        return answers