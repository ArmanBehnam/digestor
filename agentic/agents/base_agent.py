from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from langchain.schema import BaseMessage
import logging
import asyncio

logger = logging.getLogger(__name__)


class Talk2DrawingsBaseAgent(ABC):

    def __init__(self, name: str):
        self.name = name
        self.is_available = True
        self.processing_count = 0
        self.error_count = 0

    @abstractmethod
    async def process(self, input_data: Any, context: Dict[str, Any] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_input(self, input_data: Any) -> bool:
        pass

    def get_stats(self) -> Dict[str, Any]:
        success_rate = ((self.processing_count - self.error_count) / max(self.processing_count, 1)) * 100
        return {
            'name': self.name,
            'is_available': self.is_available,
            'processing_count': self.processing_count,
            'error_count': self.error_count,
            'success_rate': round(success_rate, 2)
        }

    def _record_processing(self, success: bool = True):
        self.processing_count += 1
        if not success:
            self.error_count += 1

    async def safe_process(self, input_data: Any, context: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for agent {self.name}")

            result = await self.process(input_data, context)
            self._record_processing(success=True)
            return result

        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            self._record_processing(success=False)
            return {
                'success': False,
                'error': str(e),
                'agent': self.name
            }