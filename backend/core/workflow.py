# core/workflow.py

import sys
import logging
from typing import Dict, Any
from pathlib import Path
from agents.orchestrator import OrchestratorAgent
import yaml
# Credentials are loaded from environment variables via config_loader.
# NEVER hardcode secrets here. See .env.example for required env vars.
sys.path.append('..')

logger = logging.getLogger(__name__)


class Talk2DrawingsWorkflow:

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.use_agentic = self.config.get('agentic', {}).get('enabled', False)
        self.orchestrator = OrchestratorAgent(self.config)
        self._graph = None  # lazy-init LangGraph
        mode = "agentic" if self.use_agentic else "legacy"
        print(f"Talk2Drawings Multi-Agent Workflow initialized (mode={mode})")

    @property
    def graph(self):
        """Lazy-initialize the LangGraph processing graph."""
        if self._graph is None and self.use_agentic:
            try:
                from agents.graph import create_processing_graph
                self._graph = create_processing_graph()
                logger.info("LangGraph processing graph compiled")
            except ImportError as e:
                logger.warning(f"LangGraph not available, falling back to legacy: {e}")
                self.use_agentic = False
        return self._graph

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        # Use config_loader which merges: env vars > Secrets Manager > config.yaml
        from config.config_loader import CONFIG
        if CONFIG:
            return dict(CONFIG)
        # Fallback to raw YAML only if config_loader failed
        config_file = config_path or 'config/config.yaml'
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    async def process_document(self, pdf_path: str, prompt_engineering: bool = True, enable_validation: bool = True, optimization_level: str = "balanced") -> Dict[str, Any]:
        if not Path(pdf_path).exists():
            return {'success': False, 'error': f"PDF file not found: {pdf_path}"}

        if self.use_agentic and self.graph is not None:
            return await self._process_agentic(pdf_path, prompt_engineering,
                                                enable_validation, optimization_level)

        # Legacy path
        input_data = {
            'pdf_path': pdf_path,
            'config': {'prompt_engineering': prompt_engineering,
                'enable_validation': enable_validation,
                'optimization_level': optimization_level,
                **self.config}}

        result = await self.orchestrator.safe_process(input_data)
        return result

    async def _process_agentic(self, pdf_path: str, prompt_engineering: bool = True,
                                enable_validation: bool = True,
                                optimization_level: str = "balanced") -> Dict[str, Any]:
        """Process document using the LangGraph agentic pipeline."""
        from agents.state import ProcessingState

        initial_state: ProcessingState = {
            'pdf_path': pdf_path,
            'processing_mode': optimization_level,
            'config': {
                'prompt_engineering': prompt_engineering,
                'enable_validation': enable_validation,
                'optimization_level': optimization_level,
                **self.config,
            },
            'ocr_retries': 0,
            'qa_retries': 0,
            'decisions_log': [],
            'agent_messages': [],
            'quality_metrics': {},
            'cost_tracker': {'total_usd': 0.0, 'calls': []},
        }

        try:
            result_state = await self.graph.ainvoke(initial_state)
            final = result_state.get('final_results', {})
            return {
                'success': True,
                'agent': 'agentic_pipeline',
                'final_results': final,
                'analysis_results': result_state.get('analysis_results', []),
                'processing_summary': final.get('summary', {}),
                'decisions_log': result_state.get('decisions_log', []),
                'pipeline_health': result_state.get('health', {}),
            }
        except Exception as e:
            logger.error(f"Agentic pipeline failed, falling back to legacy: {e}")
            # Fallback to legacy
            input_data = {
                'pdf_path': pdf_path,
                'config': {'prompt_engineering': prompt_engineering,
                    'enable_validation': enable_validation,
                    'optimization_level': optimization_level,
                    **self.config}}
            return await self.orchestrator.safe_process(input_data)

    def get_agent_stats(self) -> Dict[str, Any]:
        return {'orchestrator': self.orchestrator.get_stats(),
            'ocr_agent': self.orchestrator.ocr_agent.get_stats(),
            'qa_agent': self.orchestrator.qa_agent.get_stats(),
            'agentic_enabled': self.use_agentic}

    async def process_ocr_only(self, pdf_path: str) -> Dict[str, Any]:
        input_data = {'pdf_path': pdf_path, 'config': {'processing_mode': 'ocr_only'}}
        return await self.orchestrator.safe_process(input_data)

    async def process_llm_only(self, ocr_data_path: str) -> Dict[str, Any]:
        input_data = {'pdf_path': '',
            'config': {
                'processing_mode': 'llm_only',
                'ocr_data_path': ocr_data_path}}
        return await self.orchestrator.safe_process(input_data)

    async def process_full_pipeline(self, pdf_path: str, **kwargs) -> Dict[str, Any]:
        return await self.process_document(pdf_path, **kwargs)

async def process_pdf_with_agents(pdf_path: str, prompt_engineering: bool = True, optimization_level: str = "balanced") -> Dict[str, Any]:
    workflow = Talk2DrawingsWorkflow()
    result = await workflow.process_document(pdf_path,
        prompt_engineering,
        optimization_level)
    return result
