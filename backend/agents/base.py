# agents/base.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


class Talk2DrawingsBaseAgent(ABC):

    def __init__(self, name: str, blackboard=None):
        self.name = name
        self.is_available = True
        self.processing_count = 0
        self.error_count = 0
        self.blackboard = blackboard  # Optional AgentBlackboard for agentic mode
        self.cost_total = 0.0
        self.decisions_made = 0
        self._cost_details: List[Dict] = []

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
            'success_rate': round(success_rate, 2),
            'cost_total_usd': round(self.cost_total, 4),
            'decisions_made': self.decisions_made
        }

    def _record_processing(self, success: bool = True):
        self.processing_count += 1
        if not success:
            self.error_count += 1

    def log_decision(self, decision: str, reasoning: str,
                     decision_type: str = "general") -> None:
        """Log a decision made by this agent."""
        self.decisions_made += 1
        if self.blackboard:
            self.blackboard.log_decision(self.name, decision_type, decision, reasoning)
        else:
            logger.info(f"[{self.name}] Decision: {decision} | Reason: {reasoning}")

    def _record_cost(self, amount_usd: float, detail: str) -> None:
        """Track cost of an LLM/API call."""
        self.cost_total += amount_usd
        self._cost_details.append({
            'amount_usd': amount_usd,
            'detail': detail
        })
        if self.blackboard:
            self.blackboard.record_cost(self.name, amount_usd, detail)

    def post_message(self, to_agent: str, msg_type: str, content: Any) -> None:
        """Send a message to another agent via the blackboard."""
        if self.blackboard:
            self.blackboard.post_message(self.name, to_agent, msg_type, content)

    def get_messages(self) -> List[Dict]:
        """Get messages addressed to this agent."""
        if self.blackboard:
            return self.blackboard.get_messages_for(self.name)
        return []

    async def safe_process(self, input_data: Any, context: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for agent {self.name}")

            start_time = time.time()
            result = await self.process(input_data, context)
            elapsed = time.time() - start_time

            self._record_processing(success=True)

            if self.blackboard:
                self.blackboard.update_quality_metric(
                    f"{self.name}_last_duration_s", round(elapsed, 2))

            return result

        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            self._record_processing(success=False)
            return {
                'success': False,
                'error': str(e),
                'agent': self.name
            }
