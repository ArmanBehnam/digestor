import asyncio
import sys
from typing import Dict, Any
from pathlib import Path
from agents.orchestrator_agent import OrchestratorAgent

# Add parent directory to path
sys.path.append('..')


class Talk2DrawingsWorkflow:
    """Main workflow coordinator for multi-agent processing"""

    def __init__(self, config_path: str = None):
        # Load configuration
        self.config = self._load_config(config_path)

        # Initialize orchestrator (which initializes all other agents)
        self.orchestrator = OrchestratorAgent(self.config)

        print("🚀 Talk2Drawings Multi-Agent Workflow initialized")

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load configuration from existing config"""
        try:
            if config_path:
                # Load from custom path
                import yaml
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
            else:
                # Use existing configuration
                from llm_tools.config_loader import ConfigLoader
                return ConfigLoader.load("../llm_tools/config.yaml")
        except Exception as e:
            print(f"⚠️ Could not load config: {e}, using default config")
            return {
                'prompt_engineering': {'enabled': True},
                'questions': [
                    "What building code is referenced?",
                    "What version or year of the building code is used?",
                    # Add more questions as needed
                ]
            }

    async def process_document(self, pdf_path: str,
                               prompt_engineering: bool = True,
                               optimization_level: str = "balanced") -> Dict[str, Any]:
        """Process a single document through the multi-agent workflow"""

        # Validate PDF path
        if not Path(pdf_path).exists():
            return {
                'success': False,
                'error': f"PDF file not found: {pdf_path}"
            }

        # Prepare input data
        input_data = {
            'pdf_path': pdf_path,
            'config': {
                'prompt_engineering': prompt_engineering,
                'optimization_level': optimization_level,
                **self.config
            }
        }

        # Execute workflow through orchestrator
        result = await self.orchestrator.safe_process(input_data)

        return result

    def get_agent_stats(self) -> Dict[str, Any]:
        """Get statistics for all agents"""
        return {
            'orchestrator': self.orchestrator.get_stats(),
            'ocr_agent': self.orchestrator.ocr_agent.get_stats(),
            'qa_agent': self.orchestrator.qa_agent.get_stats()
        }


# Convenience function for simple usage
async def process_pdf_with_agents(pdf_path: str,
                                  prompt_engineering: bool = True,
                                  optimization_level: str = "balanced") -> Dict[str, Any]:
    """Simple function to process a PDF with multi-agent system"""

    workflow = Talk2DrawingsWorkflow()
    result = await workflow.process_document(
        pdf_path,
        prompt_engineering,
        optimization_level
    )

    return result