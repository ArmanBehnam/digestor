"""
Anthropic Claude Sonnet 4 Engine for LLM processing.

Fallback LLM engine using Anthropic's Claude Sonnet model.
"""

from typing import Dict, List, Any
import re
import logging

from .base import BaseLLMEngine

logger = logging.getLogger(__name__)


class AnthropicEngine(BaseLLMEngine):
    """Anthropic Claude Sonnet engine implementation."""
    
    def __init__(self):
        super().__init__("anthropic_sonnet", priority=20)  # Second priority
        self.client = None
        self.model = "claude-3-5-sonnet-20241022"
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize Anthropic client."""
        try:
            api_key = config.get('anthropic_api_key')
            if not api_key:
                logger.error("Anthropic API key not found in config")
                return False
            
            # Try to import anthropic
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                logger.error("anthropic package not installed. Install with: pip install anthropic")
                return False
            
            # Test the connection with a simple request
            try:
                test_response = self.client.messages.create(
                    model=self.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Test"}]
                )
                
                self.is_available = True
                logger.info(f"Anthropic Claude Sonnet engine initialized successfully")
                return True
            except Exception as e:
                logger.error(f"Anthropic API test failed: {e}")
                self.last_error = e
                self.is_available = False
                return False
            
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic engine: {e}")
            self.last_error = e
            self.is_available = False
            return False
    
    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        """Answer multiple questions for a single page using Anthropic."""
        if not self.is_available or not self.client:
            raise RuntimeError(f"Anthropic engine not available")
        
        try:
            prompt = self.generate_prompt(page_text, questions, prompt_engineer)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text if response.content else ""
            answers = self._parse_response(content, questions)
            
            self._record_request(success=True)
            return answers
            
        except Exception as e:
            self._record_request(success=False, error=e)
            raise e
    
    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        """Answer a single question using OCR result data."""
        if not self.is_available or not self.client:
            raise RuntimeError(f"Anthropic engine not available")
        
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
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text if response.content else ""
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
