# backend/agents/__init__.py
"""Agentic pipeline agents for Digestor v2.0."""

from .base import Talk2DrawingsBaseAgent
from .state import ProcessingState, AgentBlackboard, AgentEvent, DecisionType
from .ocr import OCRAgent
from .qa import EngineeringQAAgent
from .validation import ValidationAgent
from .orchestrator import OrchestratorAgent
from .triage import TriageAgent
from .memory import MemoryAgent
from .supervisor import SupervisorAgent

__all__ = [
    'Talk2DrawingsBaseAgent',
    'ProcessingState',
    'AgentBlackboard',
    'AgentEvent',
    'DecisionType',
    'OCRAgent',
    'EngineeringQAAgent',
    'ValidationAgent',
    'OrchestratorAgent',
    'TriageAgent',
    'MemoryAgent',
    'SupervisorAgent',
]


# Lazy import for graph (requires langgraph)
def create_processing_graph():
    from .graph import create_processing_graph as _create
    return _create()
