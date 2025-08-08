"""
LLM Engines package for hierarchical LLM processing with fallback support.

This package provides a similar structure to OCR engines, allowing for
multiple LLM providers with automatic fallback when one fails.

Supported engines:
- OpenAI GPT-4o (primary)
- Anthropic Claude Sonnet 4 (fallback)
- DeepSeek R1 (fallback)
"""

from .base import BaseLLMEngine
from .openai_engine import OpenAIEngine
from .anthropic_engine import AnthropicEngine
from .deepseek_engine import DeepSeekEngine
from .llm_registry import LLMRegistry

__all__ = [
    'BaseLLMEngine',
    'OpenAIEngine', 
    'AnthropicEngine',
    'DeepSeekEngine',
    'LLMRegistry'
]
