from openai import OpenAI
import re
import logging

from .llm_engines import LLMRegistry
from .prompt_engineer import PromptEngineer

logger = logging.getLogger(__name__)

class LLMInterface:
    def __init__(self, config):
        # Initialize the hierarchical LLM registry
        try:
            self.llm_registry = LLMRegistry(config)
            self.use_fallback = True
            logger.info(f"LLM Interface initialized with hierarchical engine support: {self.llm_registry}")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM registry, falling back to OpenAI only: {e}")
            # Fallback to original OpenAI-only implementation
            self.client = OpenAI(api_key=config['openai_api_key'])
            self.llm_registry = None
            self.use_fallback = False
        
        # Initialize prompt engineering
        self.prompt_engineer = PromptEngineer(config)
        logger.info(f"Prompt engineering initialized: enabled={self.prompt_engineer.enabled}")
        
        # Store config for fallback methods
        self.config = config

    def answer_question(self, question, ocr_result, relevant_pages):
        """
        Answer a single question using OCR result data.
        This method uses hierarchical LLM engines with fallback support.
        """
        if self.use_fallback and self.llm_registry:
            # Use the new hierarchical system
            try:
                return self.llm_registry.answer_single_question_with_fallback(
                    question, ocr_result, relevant_pages
                )
            except Exception as e:
                logger.error(f"LLM registry failed, falling back to OpenAI: {e}")
                # Fall back to original implementation
                pass
        
        # Original OpenAI-only implementation (fallback)
        return self._answer_question_openai_only(question, ocr_result, relevant_pages)
    
    def _answer_question_openai_only(self, question, ocr_result, relevant_pages):
        """
        Original OpenAI-only implementation for fallback.
        """
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
                combined_text += f"\n--- Page {page_number} ---\n{page_text}\n"
        
        # Use the detailed engineering prompt (restored from original)
        prompt = self.generate_prompt(combined_text, [question])
        
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."},
                {"role": "user", "content": prompt}
            ]
            
            # Use new OpenAI API style (version 1.x)
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Switched to gpt-4o for higher rate limits (800k vs 450k TPM)
                messages=messages,
                temperature=0.2,
                max_tokens=1500
            )
            content = response.choices[0].message.content
            
            # Parse the structured response format: Q1. [answer] | Page: [page] | Confidence: [conf]%
            qid = "Q1"
            # Look for pattern: Q1. answer | Page: X | Confidence: Y%
            pattern = rf"{qid}\.?\s*(.*?)\s*\|\s*Page:\s*(.*?)\s*\|\s*Confidence:\s*(\d+)%"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            
            if match:
                answer = match.group(1).strip()
                page_info = match.group(2).strip()
                confidence = match.group(3).strip()
                
                # Clean up the answer
                if answer.lower().startswith(question.lower()[:20]):
                    answer = answer[len(question):].strip(" \n:-*")
                
                return {
                    'answer': answer.strip(),
                    'page': page_info if page_info != 'N/A' else pages_data[relevant_pages[0]].get('page_number', relevant_pages[0] + 1) if relevant_pages and relevant_pages[0] < len(pages_data) else 'N/A',
                    'confidence': int(confidence) if confidence.isdigit() else 0,
                    'source': 'openai_gpt4o_fallback'
                }
            else:
                # Fallback to simple format if structured parsing fails
                simple_pattern = rf"{qid}\.?\s*(.*?)\s*(?=Q\d+\.|\Z)"
                simple_match = re.search(simple_pattern, content, re.DOTALL | re.IGNORECASE)
                if simple_match:
                    answer = simple_match.group(1).strip()
                    return {
                        'answer': answer,
                        'page': pages_data[relevant_pages[0]].get('page_number', relevant_pages[0] + 1) if relevant_pages and relevant_pages[0] < len(pages_data) else 'N/A',
                        'confidence': 50,  # Default confidence for simple format
                        'source': 'openai_gpt4o_fallback'
                    }
                else:
                    return {
                        'answer': "Not Found",
                        'page': 'N/A',
                        'confidence': 0,
                        'source': 'openai_gpt4o_fallback'
                    }
            
        except Exception as e:
            return {
                'answer': f"Error: {str(e)}",
                'page': 'N/A', 
                'confidence': 0,
                'source': 'openai_gpt4o_fallback'
            }
    
    def get_engine_stats(self):
        """Get statistics for all LLM engines."""
        if self.use_fallback and self.llm_registry:
            return self.llm_registry.get_engine_stats()
        else:
            return [{
                'engine_name': 'openai_gpt4o_fallback',
                'priority': 1,
                'is_available': True,
                'request_count': 'N/A',
                'success_count': 'N/A',
                'success_rate': 'N/A',
                'last_error': None
            }]
    
    def reset_engine_availability(self):
        """Reset availability status for all engines."""
        if self.use_fallback and self.llm_registry:
            self.llm_registry.reset_engine_availability()

    def answer_page(self, page_text, questions):
        """
        Answer multiple questions for a single page of text.
        This method uses hierarchical LLM engines with fallback support.
        """
        if self.use_fallback and self.llm_registry:
            # Use the new hierarchical system
            try:
                return self.llm_registry.answer_questions_with_fallback(page_text, questions)
            except Exception as e:
                logger.error(f"LLM registry failed, falling back to OpenAI: {e}")
                # Fall back to original implementation
                pass
        
        # Original OpenAI-only implementation (fallback)
        return self._answer_page_openai_only(page_text, questions)
    
    def _answer_page_openai_only(self, page_text, questions):
        """
        Original OpenAI-only implementation for fallback.
        """
        prompt = self.generate_prompt(page_text, questions)
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant for structural and seismic engineering documents."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model="gpt-4o",  # Use gpt-4o for higher rate limits
                messages=messages,
                temperature=0.2,
                max_tokens=1500
            )
            content = response.choices[0].message.content
            
            # Extract answers based on Q1, Q2,... headers
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
                        answer = answer[len(question):].strip(" \n:-*")
                    
                    answers[qid] = {
                        'answer': answer.strip(),
                        'page': page_info if page_info != 'N/A' else 1,
                        'confidence': int(confidence) if confidence.isdigit() else 0,
                        'source': 'openai_gpt4o_fallback'
                    }
                else:
                    # Fallback to simple format if structured parsing fails
                    simple_pattern = rf"{qid}\.?\s*(.*?)\s*(?=Q\d+\.|\Z)"
                    simple_match = re.search(simple_pattern, content, re.DOTALL | re.IGNORECASE)
                    if simple_match:
                        answer = simple_match.group(1).strip()
                        answers[qid] = {
                            'answer': answer,
                            'page': 1,
                            'confidence': 50,
                            'source': 'openai_gpt4o_fallback'
                        }
                    else:
                        answers[qid] = {
                            'answer': "Not Found",
                            'page': 1,
                            'confidence': 0,
                            'source': 'openai_gpt4o_fallback'
                        }
            
            return answers
            
        except Exception as e:
            # Return error format for all questions
            error_answers = {}
            for i, question in enumerate(questions):
                qid = f"Q{i+1}"
                error_answers[qid] = {
                    'answer': f"Error: {str(e)}",
                    'page': 1,
                    'confidence': 0
                }
            return error_answers

    @staticmethod
    def generate_prompt(page_text, questions):
        """Sophisticated engineering document prompt with detailed search strategies"""
        qblock = "\n".join([f"Q{i+1}. {q}" for i, q in enumerate(questions)])
        return f"""You are a highly skilled engineering document interpreter specializing in construction documents.
        You will analyze OCR-extracted text from engineering documents to find answers to specific technical questions.

        **CRITICAL INSTRUCTIONS:**
        - OCR text may contain errors like character substitutions (e.g., 'Sd8' instead of 'Sds', 'windload' instead of 'wind load')
        - Be resilient to spacing issues, misaligned text, and OCR artifacts
        - Only return answers that are clearly supported by the document text
        - If an exact answer is not found, return "Not Found"
        - Do NOT guess or infer values
        - For deflection questions, search for ratios like L/240, L/360, L/600, etc.

        **SEARCH STRATEGIES BY CATEGORY:**

        **Building Codes:** Look for phrases like "building code", "IBC", "OBC", "CBC", "NYCBC" followed by years (2015, 2018, 2021, etc.)
        
        **ASCE Standards:** Search for "ASCE 7" followed by versions like "7-10", "7-16", "7-22"
        
        **Deflection Limits:** Search for:
        - Exterior walls: Look near "deflection criteria", "exterior wall", "curtain wall"
        - Interior walls: Look near "interior wall", "partition wall"  
        - Floor joists: Look near "floor joist", "floor framing"
        - Roof rafters: Look near "roof rafter", "roof framing"
        - Ceiling joists: Look near "ceiling joist", "ceiling framing"
        - Primary structure: Look near "live load", "primary structure", "vertical deflection"

        **Wind Loads:** Search for "Vult", "wind speed", "mph", "exposure category" (A/B/C), "risk category" (I/II/III/IV), "GCpi"
        
        **Snow Loads:** Search for "Pg", "Is", "Ce", "Ct", "Pf" (often with = signs)
        
        **Seismic Parameters:** Search for "Sds", "Sd1", "site class" (A/B/C/D/E/F), "seismic design category", "Ie", "Ip"
        
        **Gravity Loads:** Search for "psf", "live load", "dead load", "roof"

        **COMMON OCR ERROR PATTERNS:**
        - "SdS" or "Sd8" → "Sds"
        - "SDl" or "SD1" → "Sd1" 
        - "Windload" → "Wind load"
        - "L/240" might appear as "L/ 240" or "L /240"
        - Numbers may have extra spaces: "1 5 0" → "150"

        **OUTPUT FORMAT:**
        For each question, provide your answer in this exact format:
        Q[number]. [answer] | Page: [page_number] | Confidence: [percentage]%

        If not found, use:
        Q[number]. Not Found | Page: N/A | Confidence: 0%

        **DOCUMENT TEXT:**
        \"\"\"
        {page_text}
        \"\"\"

        **QUESTIONS TO ANSWER:**
        {qblock}

        **RESPONSE RULES:**
        - One clear, concise answer per question
        - Include page number if available in metadata
        - Provide confidence percentage (0-100%)
        - Use "Not Found" only when genuinely unable to locate the information
        - For deflection ratios, include the exact format found (e.g., "L/240", "L/360")
        - For codes, include year if present (e.g., "IBC 2018")
        - For numeric values, include units if specified (e.g., "150 mph", "20 psf")
        """
