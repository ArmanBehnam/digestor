# llm/llm_engines/deepseek.py
"""
DeepSeek R1 Engine for LLM processing.

Fallback LLM engine using DeepSeek's R1 model.
"""

from typing import Dict, List, Any
import re
import logging
import requests
import json

from .base import BaseLLMEngine

logger = logging.getLogger(__name__)


class DeepSeekEngine(BaseLLMEngine):
    def __init__(self):
        super().__init__("deepseek_r1", priority=30)
        self.api_key = None
        self.base_url = "https://api.together.xyz/v1"  # Changed from deepseek.com
        self.model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"  # Together.ai model
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize DeepSeek client."""
        try:
            api_key = config.get('deepseek_api_key')
            if not api_key:
                logger.error("DeepSeek API key not found in config")
                return False
            
            self.api_key = api_key
            
            # Test the connection with a simple request
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                test_payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Test"}],
                    "max_tokens": 10
                }
                
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=test_payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.is_available = True
                    logger.info(f"DeepSeek R1 engine initialized successfully")
                    return True
                else:
                    logger.error(f"DeepSeek API test failed: {response.status_code} - {response.text}")
                    self.last_error = f"API test failed: {response.status_code}"
                    self.is_available = False
                    return False
                    
            except Exception as e:
                logger.error(f"DeepSeek API test failed: {e}")
                self.last_error = e
                self.is_available = False
                return False
            
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek engine: {e}")
            self.last_error = e
            self.is_available = False
            return False
    
    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        """Answer multiple questions for a single page using DeepSeek."""
        if not self.is_available or not self.api_key:
            raise RuntimeError(f"DeepSeek engine not available")
        
        try:
            prompt = self.generate_prompt(page_text, questions, prompt_engineer)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1500
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            answers = self._parse_response(content, questions)
            
            self._record_request(success=True)
            return answers
            
        except Exception as e:
            self._record_request(success=False, error=e)
            raise e
    
    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        """Answer a single question using OCR result data."""
        if not self.is_available or not self.api_key:
            raise RuntimeError(f"DeepSeek engine not available")
        
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
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1500
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            result = response.json()
            content = result['choices'][0]['message']['content']
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
            pattern = rf"{qid}\\.?\\s*(.*?)\\s*\\|\\s*Page:\\s*(.*?)\\s*\\|\\s*Confidence:\\s*(\\d+)%"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            
            if match:
                answer = match.group(1).strip()
                page_info = match.group(2).strip()
                confidence = match.group(3).strip()
                
                # Clean up the answer
                if answer.lower().startswith(question.lower()[:20]):
                    answer = answer[len(question):].strip(" \\n:-*")
                
                answers[qid] = {
                    'answer': answer.strip(),
                    'page': page_info if page_info != 'N/A' else 1,
                    'confidence': int(confidence) if confidence.isdigit() else 0,
                    'source': self.engine_name
                }
            else:
                # Fallback to simple format if structured parsing fails
                simple_pattern = rf"{qid}\\.?\\s*(.*?)\\s*(?=Q\\d+\\.|\\Z)"
                simple_match = re.search(simple_pattern, content, re.DOTALL | re.IGNORECASE)
                if simple_match:
                    answer = simple_match.group(1).strip()
                    answers[qid] = {
                        'answer': answer,
                        'page': 1,
                        'confidence': 50,
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
