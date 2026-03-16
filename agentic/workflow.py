# agentic/workflow.py

import asyncio
import sys
from typing import Dict, Any
from pathlib import Path
from agents.orchestrator_agent import OrchestratorAgent
import os
import yaml
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# NOTE: Set these env vars externally (e.g. .env file, Secrets Manager, or shell)
# AZURE_ENDPOINT, AZURE_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

sys.path.append('..')


class Talk2DrawingsWorkflow:

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.orchestrator = OrchestratorAgent(self.config)
        print("Talk2Drawings Multi-Agent Workflow initialized")

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        config_file = config_path or 'config.yaml'
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    async def process_document(self, pdf_path: str, prompt_engineering: bool = True, enable_validation: bool = True, optimization_level: str = "balanced") -> Dict[str, Any]:
        if not Path(pdf_path).exists():
            return {'success': False, 'error': f"PDF file not found: {pdf_path}"}

        input_data = {
            'pdf_path': pdf_path,
            'config': {
                'prompt_engineering': prompt_engineering,
                'enable_validation': enable_validation,  # NEW
                'optimization_level': optimization_level,
                **self.config
            }
        }

        result = await self.orchestrator.safe_process(input_data)
        return result

    def get_agent_stats(self) -> Dict[str, Any]:
        return {'orchestrator': self.orchestrator.get_stats(),
            'ocr_agent': self.orchestrator.ocr_agent.get_stats(),
            'qa_agent': self.orchestrator.qa_agent.get_stats()
        }

    async def process_ocr_only(self, pdf_path: str) -> Dict[str, Any]:
        input_data = {
            'pdf_path': pdf_path,
            'config': {'processing_mode': 'ocr_only'}
        }
        return await self.orchestrator.safe_process(input_data)

    async def process_llm_only(self, ocr_data_path: str) -> Dict[str, Any]:
        input_data = {
            'pdf_path': '',
            'config': {
                'processing_mode': 'llm_only',
                'ocr_data_path': ocr_data_path
            }
        }
        return await self.orchestrator.safe_process(input_data)

    async def process_full_pipeline(self, pdf_path: str, **kwargs) -> Dict[str, Any]:
        return await self.process_document(pdf_path, **kwargs)

async def process_pdf_with_agents(pdf_path: str, prompt_engineering: bool = True, optimization_level: str = "balanced") -> Dict[str, Any]:

    workflow = Talk2DrawingsWorkflow()
    result = await workflow.process_document(pdf_path,
        prompt_engineering,
        optimization_level)
    return result