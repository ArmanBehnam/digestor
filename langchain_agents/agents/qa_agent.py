import asyncio
import sys
from typing import Dict, Any, List
from .base_agent import Talk2DrawingsBaseAgent

# Add parent directory to path
sys.path.append('..')


class EngineeringQAAgent(Talk2DrawingsBaseAgent):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("Engineering_QA_Agent")
        self.config = config or {}

        try:
            from llm_tools.llm_interface import LLMInterface
            from llm_tools.config_loader import ConfigLoader

            self.llm_config = ConfigLoader.load("llm_tools/config.yaml")
            self.llm_interface = LLMInterface(self.llm_config)
            self.questions = self.llm_config['questions']
            print(f"{self.name}: LLM interface loaded with {len(self.questions)} questions")

        except ImportError as e:
            print(f"{self.name}: Could not load LLM interface: {e}")
            self.llm_interface = None
            self.questions = []
            self.is_available = False

    def validate_input(self, input_data: Any) -> bool:
        return (isinstance(input_data, dict) and
                'filtered_pages' in input_data and
                isinstance(input_data['filtered_pages'], dict) and
                'matching_pages' in input_data['filtered_pages'])

    async def process(self, ocr_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.llm_interface:
            raise Exception("LLM interface not available")
        try:
            print(f"QA Agent processing {len(self.questions)} questions")
            filtered_pages = ocr_data['filtered_pages']['matching_pages']
            if not filtered_pages:
                print("No filtered pages found, cannot proceed")
                return {'success': False,
                    'agent': self.name,
                    'error': 'No relevant pages found for processing',
                    'qa_results': {}
                }

            combined_text = ""
            for page in filtered_pages:
                combined_text += f"\n--- Page {page['page_number']} ---\n"
                combined_text += page.get('extracted_text', '') + "\n"
            print(f"Processing {len(filtered_pages)} pages with {len(combined_text)} characters")
            answers = self.llm_interface.answer_page(combined_text, self.questions)

            return {'success': True,
                'agent': self.name,
                'qa_results': answers,
                'questions_processed': len(self.questions),
                'pages_used': len(filtered_pages),
                'text_length': len(combined_text)
            }

        except Exception as e:
            raise Exception(f"QA processing failed: {e}")