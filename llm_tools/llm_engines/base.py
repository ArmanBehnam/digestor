"""
Base LLM Engine class for hierarchical LLM processing.

This provides the foundation for all LLM engines with standardized interfaces
and error handling patterns.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging
import time

logger = logging.getLogger(__name__)


class BaseLLMEngine(ABC):
    """
    Abstract base class for all LLM engines.
    
    Provides standardized interface for question answering with
    confidence scoring and error handling.
    """
    
    def __init__(self, engine_name: str, priority: int = 50):
        """
        Initialize the LLM engine.
        
        Args:
            engine_name: Unique identifier for this engine
            priority: Priority for fallback ordering (lower = higher priority)
        """
        self.engine_name = engine_name
        self.priority = priority
        self.is_available = False
        self.last_error = None
        self.request_count = 0
        self.success_count = 0
        
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the engine with configuration.
        
        Args:
            config: Configuration dictionary with API keys, etc.
            
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    def answer_questions(self, page_text: str, questions: List[str], prompt_engineer=None) -> Dict[str, Dict[str, Any]]:
        """
        Answer multiple questions for a single page of text.
        
        Args:
            page_text: The text content to analyze
            questions: List of questions to answer
            prompt_engineer: Optional prompt engineering instance for optimization
            
        Returns:
            Dictionary mapping question IDs (Q1, Q2, etc.) to answer dictionaries
            Each answer dict should contain: answer, page, confidence, source
        """
        pass
    
    @abstractmethod
    def answer_single_question(self, question: str, ocr_result: Dict, relevant_pages: List[int]) -> Dict[str, Any]:
        """
        Answer a single question using OCR result data.
        
        Args:
            question: The question to answer
            ocr_result: OCR result data structure
            relevant_pages: List of page indices to search
            
        Returns:
            Answer dictionary with: answer, page, confidence, source
        """
        pass
    
    def generate_prompt(self, page_text: str, questions: List[str], prompt_engineer=None) -> str:
        """
        Generate engineering-specific prompt for LLM processing.
        
        This method provides a standardized prompt that works across all LLM engines.
        Can use prompt engineering if provided.
        """
        # Use prompt engineering if available and enabled
        if prompt_engineer and prompt_engineer.enabled:
            try:
                return prompt_engineer.optimize_prompt(page_text, questions)
            except Exception as e:
                logger.warning(f"Prompt engineering failed, using static prompt: {e}")
        
        # Fallback to static prompt
        questions_text = "\\n".join([f"Q{i+1}. {q}" for i, q in enumerate(questions)])
        
        return f'''You are a structural and seismic engineering document analyzer. Analyze the following document text and answer the engineering questions with high precision.

**Document Text:**
{page_text}

**Questions to Answer:**
{questions_text}

**Instructions:**
1. **Answer Format**: For each question, respond with: "Q1. [your answer] | Page: [page number or N/A] | Confidence: [0-100]%"
2. **Engineering Focus**: Look for specific technical values, standards, and criteria
3. **Source Attribution**: Reference page numbers when found
4. **Confidence Scoring**: 
   - 90-100%: Exact value found with clear context
   - 70-89%: Value found with reasonable context
   - 50-69%: Approximate or inferred value
   - 0-49%: Uncertain or not found

**Search Strategies:**
- **Building Codes**: Look for "IBC", "NYSBC", "NYCBC", years (2018, 2021, etc.)
- **Deflection Limits**: Search for "L/", fractions like "1/360", "1/240", deflection criteria
- **Wind Parameters**: Find "mph", "psf", "exposure", "GCpi", "basic wind speed"
- **Snow Loads**: Look for "psf", "Pg", "Pf", "Is", "Ce", "Ct" values
- **Seismic Parameters**: Search for "Sds", "Sd1", "site class" (A/B/C/D/E/F), "seismic design category", "Ie", "Ip"

**Answer each question precisely and concisely:**'''

    def get_stats(self) -> Dict[str, Any]:
        """Get engine performance statistics."""
        success_rate = (self.success_count / self.request_count * 100) if self.request_count > 0 else 0
        return {
            'engine_name': self.engine_name,
            'priority': self.priority,
            'is_available': self.is_available,
            'request_count': self.request_count,
            'success_count': self.success_count,
            'success_rate': round(success_rate, 2),
            'last_error': str(self.last_error) if self.last_error else None
        }
    
    def _record_request(self, success: bool, error: Optional[Exception] = None):
        """Record request statistics."""
        self.request_count += 1
        if success:
            self.success_count += 1
            self.last_error = None
        else:
            self.last_error = error
            logger.warning(f"LLM engine {self.engine_name} request failed: {error}")
    
    def _validate_response(self, response: Dict[str, Any]) -> bool:
        """Validate that the response has the expected structure."""
        if not isinstance(response, dict):
            return False
        
        # Check that we have at least one question answer
        has_answers = any(key.startswith('Q') for key in response.keys())
        return has_answers
    
    def __str__(self) -> str:
        return f"{self.engine_name} (priority: {self.priority}, available: {self.is_available})"
    
    def __lt__(self, other):
        """For sorting by priority (lower priority number = higher priority)."""
        return self.priority < other.priority
