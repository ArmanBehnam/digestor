"""
LLM Registry for managing hierarchical LLM processing with fallback support.

This provides the central coordination for multiple LLM engines,
automatically falling back to the next available engine when one fails.
"""

from typing import Dict, List, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor
import time

from .base import BaseLLMEngine
from .openai_engine import OpenAIEngine
from .anthropic_engine import AnthropicEngine
from .deepseek_engine import DeepSeekEngine

logger = logging.getLogger(__name__)


class LLMRegistry:
    """
    Central registry for managing multiple LLM engines with hierarchical fallback.
    
    Similar to OCR engines, this provides automatic fallback when primary engines fail.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the LLM registry with configuration.
        
        Args:
            config: Configuration dictionary containing LLM settings and API keys
        """
        self.config = config
        self.engines: List[BaseLLMEngine] = []
        self.llm_config = config.get('llm_engines', {})
        self.preferred_engine = self.llm_config.get('preferred_engine', 'openai_gpt4o')
        self.fallback_engines = self.llm_config.get('fallback_engines', ['anthropic_sonnet', 'deepseek_r1'])
        self.confidence_threshold = self.llm_config.get('confidence_threshold', 0.5)
        self.timeout_seconds = self.llm_config.get('timeout_seconds', 120)
        self.max_retries = self.llm_config.get('max_retries', 3)
        
        # Initialize prompt engineer for passing to engines
        from ..prompt_engineer import PromptEngineer
        self.prompt_engineer = PromptEngineer(config)
        
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize all available LLM engines."""
        # Create all engine instances
        all_engines = [
            OpenAIEngine(),
            AnthropicEngine(),
            DeepSeekEngine()
        ]
        
        # Initialize each engine
        for engine in all_engines:
            try:
                if engine.initialize(self.config):
                    self.engines.append(engine)
                    logger.info(f"LLM engine {engine.engine_name} initialized successfully")
                else:
                    logger.warning(f"LLM engine {engine.engine_name} failed to initialize")
            except Exception as e:
                logger.error(f"Error initializing LLM engine {engine.engine_name}: {e}")
        
        # Sort engines by priority (lower number = higher priority)
        self.engines.sort()
        
        if not self.engines:
            raise RuntimeError("No LLM engines available")
        
        logger.info(f"LLM Registry initialized with {len(self.engines)} engines: {[e.engine_name for e in self.engines]}")
    
    def get_available_engines(self) -> List[BaseLLMEngine]:
        """Get list of currently available engines."""
        return [engine for engine in self.engines if engine.is_available]
    
    def answer_questions_with_fallback(self, page_text: str, questions: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Answer multiple questions with automatic fallback between engines.
        
        Args:
            page_text: The text content to analyze
            questions: List of questions to answer
            
        Returns:
            Dictionary mapping question IDs to answer dictionaries
        """
        available_engines = self.get_available_engines()
        if not available_engines:
            raise RuntimeError("No LLM engines available")
        
        last_error = None
        
        for engine in available_engines:
            try:
                logger.info(f"Attempting to answer questions using {engine.engine_name}")
                
                # Try to get answers from this engine
                answers = engine.answer_questions(page_text, questions, self.prompt_engineer)
                
                # Validate the response
                if self._validate_answers(answers, questions):
                    logger.info(f"Successfully answered {len(answers)} questions using {engine.engine_name}")
                    return answers
                else:
                    logger.warning(f"Invalid response from {engine.engine_name}, trying next engine")
                    continue
                    
            except Exception as e:
                last_error = e
                logger.warning(f"LLM engine {engine.engine_name} failed: {e}")
                
                # Mark engine as temporarily unavailable if it's a serious error
                if "API" in str(e) or "authentication" in str(e).lower():
                    engine.is_available = False
                    logger.warning(f"Marking {engine.engine_name} as unavailable due to API error")
                
                continue
        
        # If we get here, all engines failed
        error_msg = f"All LLM engines failed. Last error: {last_error}"
        logger.error(error_msg)
        
        # Return default "Not Found" answers for all questions
        return self._create_fallback_answers(questions, error_msg)
    
    def answer_single_question_with_fallback(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        """
        Answer a single question with automatic fallback between engines.
        
        Args:
            question: The question to answer
            ocr_result: OCR result data structure
            relevant_pages: List of page indices to search
            
        Returns:
            Answer dictionary with answer, page, confidence, source
        """
        available_engines = self.get_available_engines()
        if not available_engines:
            raise RuntimeError("No LLM engines available")
        
        last_error = None
        
        for engine in available_engines:
            try:
                logger.info(f"Attempting to answer single question using {engine.engine_name}")
                
                # Try to get answer from this engine
                answer = engine.answer_single_question(question, ocr_result, relevant_pages)
                
                # Validate the response
                if self._validate_single_answer(answer):
                    logger.info(f"Successfully answered question using {engine.engine_name}")
                    return answer
                else:
                    logger.warning(f"Invalid response from {engine.engine_name}, trying next engine")
                    continue
                    
            except Exception as e:
                last_error = e
                logger.warning(f"LLM engine {engine.engine_name} failed: {e}")
                
                # Mark engine as temporarily unavailable if it's a serious error
                if "API" in str(e) or "authentication" in str(e).lower():
                    engine.is_available = False
                    logger.warning(f"Marking {engine.engine_name} as unavailable due to API error")
                
                continue
        
        # If we get here, all engines failed
        error_msg = f"All LLM engines failed. Last error: {last_error}"
        logger.error(error_msg)
        
        return {
            'answer': f"Error: {error_msg}",
            'page': 'N/A',
            'confidence': 0,
            'source': 'fallback'
        }
    
    def _validate_answers(self, answers: Dict[str, Dict[str, Any]], questions: List[str]) -> bool:
        """Validate that the answers are properly formatted."""
        if not isinstance(answers, dict):
            return False
        
        # Check that we have answers for the expected questions
        expected_qids = [f"Q{i+1}" for i in range(len(questions))]
        
        for qid in expected_qids:
            if qid not in answers:
                return False
            
            answer_data = answers[qid]
            if not isinstance(answer_data, dict):
                return False
            
            # Check required fields
            required_fields = ['answer', 'page', 'confidence', 'source']
            if not all(field in answer_data for field in required_fields):
                return False
        
        return True
    
    def _validate_single_answer(self, answer: Dict[str, Any]) -> bool:
        """Validate that a single answer is properly formatted."""
        if not isinstance(answer, dict):
            return False
        
        # Check required fields
        required_fields = ['answer', 'page', 'confidence', 'source']
        return all(field in answer for field in required_fields)
    
    def _create_fallback_answers(self, questions: List[str], error_msg: str) -> Dict[str, Dict[str, Any]]:
        """Create fallback answers when all engines fail."""
        answers = {}
        for i, question in enumerate(questions):
            qid = f"Q{i+1}"
            answers[qid] = {
                'answer': f"Error: {error_msg}",
                'page': 'N/A',
                'confidence': 0,
                'source': 'fallback'
            }
        return answers
    
    def get_engine_stats(self) -> List[Dict[str, Any]]:
        """Get performance statistics for all engines."""
        return [engine.get_stats() for engine in self.engines]
    
    def reset_engine_availability(self):
        """Reset availability status for all engines (useful for recovery)."""
        for engine in self.engines:
            if not engine.is_available:
                logger.info(f"Attempting to re-initialize {engine.engine_name}")
                try:
                    if engine.initialize(self.config):
                        logger.info(f"Successfully re-initialized {engine.engine_name}")
                except Exception as e:
                    logger.error(f"Failed to re-initialize {engine.engine_name}: {e}")
    
    def __str__(self) -> str:
        available_count = len(self.get_available_engines())
        return f"LLMRegistry({available_count}/{len(self.engines)} engines available)"
