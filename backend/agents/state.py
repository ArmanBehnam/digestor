# backend/agents/state.py
"""Shared state and communication infrastructure for the agentic pipeline."""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AgentEvent(Enum):
    """Events that agents can emit/react to."""
    DOCUMENT_UPLOADED = "document_uploaded"
    TRIAGE_COMPLETE = "triage_complete"
    OCR_COMPLETE = "ocr_complete"
    QA_COMPLETE = "qa_complete"
    VALIDATION_COMPLETE = "validation_complete"
    PIPELINE_COMPLETE = "pipeline_complete"
    ESCALATION_TRIGGERED = "escalation_triggered"


class DecisionType(Enum):
    """Types of decisions agents can make."""
    OCR_ENGINE_SELECTED = "ocr_engine_selected"
    LLM_SELECTED = "llm_selected"
    RETRY_TRIGGERED = "retry_triggered"
    QUALITY_THRESHOLD_MET = "quality_threshold_met"
    ESCALATION_TRIGGERED = "escalation_triggered"
    STRATEGY_OVERRIDE = "strategy_override"
    REQUERY_REQUESTED = "requery_requested"


class ProcessingState(TypedDict, total=False):
    """LangGraph state schema for the agentic pipeline.

    Every field is optional (total=False) so the state can be built up
    incrementally as agents add their results.
    """
    # Input
    document_id: str
    pdf_path: str
    s3_key: str
    bucket: str
    processing_mode: str  # "auto", "deep", "quick"
    config: Dict[str, Any]

    # Triage results
    triage_result: Dict[str, Any]
    document_info: Dict[str, Any]

    # Memory suggestions
    memory_suggestions: Dict[str, Any]

    # PDF.js (Tier 1) results
    pdfjs_result: Dict[str, Any]       # Raw LLM answers from PDF.js text
    pdfjs_analysis: List[Dict[str, Any]]  # AnalysisResult[] format
    pdfjs_text_quality: Dict[str, Any]  # Text quality metrics
    pdfjs_sufficient: bool              # Whether Tier 1 was enough
    extracted_text: str                 # Browser-extracted text (if available)

    # OCR (Tier 2) results
    ocr_strategy: Dict[str, Any]
    ocr_result: Dict[str, Any]
    ocr_quality: float
    ocr_retries: int

    # QA results
    qa_result: Dict[str, Any]
    qa_confidence: float
    qa_retries: int
    requery_question_ids: List[int]

    # VLM (Tier 3) results
    vlm_result: Dict[str, Any]
    vlm_answers: List[Dict[str, Any]]
    missing_questions: List[Dict[str, Any]]

    # Validation results
    validation_result: Dict[str, Any]

    # Final output
    final_results: Dict[str, Any]
    analysis_results: List[Dict[str, Any]]
    processing_tier: int                # 1=pdfjs, 2=ocr+llm, 3=vlm

    # Pipeline metadata
    decisions_log: List[Dict[str, Any]]
    agent_messages: List[Dict[str, Any]]
    quality_metrics: Dict[str, Any]
    cost_tracker: Dict[str, Any]
    error: Optional[str]
    current_step: str


class AgentBlackboard:
    """Shared communication layer for agents.

    Wraps ProcessingState so all data is serializable by LangGraph.
    Agents use this to post messages, log decisions, and share metrics.
    """

    def __init__(self, state: Optional[ProcessingState] = None):
        self.state: ProcessingState = state or {}
        if 'decisions_log' not in self.state:
            self.state['decisions_log'] = []
        if 'agent_messages' not in self.state:
            self.state['agent_messages'] = []
        if 'quality_metrics' not in self.state:
            self.state['quality_metrics'] = {}
        if 'cost_tracker' not in self.state:
            self.state['cost_tracker'] = {'total_usd': 0.0, 'calls': []}

    def post_message(self, from_agent: str, to_agent: str,
                     msg_type: str, content: Any) -> None:
        """Post a message from one agent to another via the blackboard."""
        self.state['agent_messages'].append({
            'from': from_agent,
            'to': to_agent,
            'type': msg_type,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })

    def log_decision(self, agent_name: str, decision_type: str,
                     decision: str, reasoning: str) -> None:
        """Record an agent decision for audit trail."""
        self.state['decisions_log'].append({
            'agent': agent_name,
            'decision_type': decision_type,
            'decision': decision,
            'reasoning': reasoning,
            'timestamp': datetime.now().isoformat()
        })
        logger.info(f"[{agent_name}] Decision: {decision} | Reason: {reasoning}")

    def get_messages_for(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get all messages addressed to a specific agent."""
        return [
            msg for msg in self.state.get('agent_messages', [])
            if msg['to'] == agent_name or msg['to'] == '*'
        ]

    def update_quality_metric(self, metric_name: str, value: Any) -> None:
        """Update a quality metric on the blackboard."""
        self.state['quality_metrics'][metric_name] = {
            'value': value,
            'timestamp': datetime.now().isoformat()
        }

    def record_cost(self, agent_name: str, amount_usd: float,
                    detail: str) -> None:
        """Track LLM/API costs."""
        tracker = self.state['cost_tracker']
        tracker['total_usd'] = tracker.get('total_usd', 0.0) + amount_usd
        tracker['calls'].append({
            'agent': agent_name,
            'amount_usd': amount_usd,
            'detail': detail,
            'timestamp': datetime.now().isoformat()
        })

    def get_state(self) -> ProcessingState:
        """Return the underlying state dict for LangGraph serialization."""
        return self.state
