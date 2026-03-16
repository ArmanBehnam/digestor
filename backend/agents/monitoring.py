# backend/agents/monitoring.py
"""Agent health monitoring, circuit breakers, and cost tracking."""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Opens after N consecutive failures, auto-resets after cooldown."""

    def __init__(self, name: str, failure_threshold: int = 3,
                 cooldown_seconds: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def record_success(self):
        self.consecutive_failures = 0
        self.is_open = False

    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(
                f"Circuit breaker OPEN for {self.name} "
                f"after {self.consecutive_failures} failures"
            )

    def allow_request(self) -> bool:
        if not self.is_open:
            return True
        # Check cooldown
        if self.last_failure_time and \
           (time.time() - self.last_failure_time) > self.cooldown_seconds:
            logger.info(f"Circuit breaker {self.name} entering half-open state")
            return True  # allow one attempt
        return False

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'is_open': self.is_open,
            'consecutive_failures': self.consecutive_failures,
            'failure_threshold': self.failure_threshold,
            'cooldown_seconds': self.cooldown_seconds,
            'last_failure': datetime.fromtimestamp(self.last_failure_time).isoformat()
                if self.last_failure_time else None,
        }


class AgentHealthMonitor:
    """Tracks agent stats, error rates, and latencies."""

    def __init__(self):
        self.agent_stats: Dict[str, Dict[str, Any]] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create_breaker(self, agent_name: str,
                               failure_threshold: int = 3,
                               cooldown_seconds: float = 60.0) -> CircuitBreaker:
        if agent_name not in self.circuit_breakers:
            self.circuit_breakers[agent_name] = CircuitBreaker(
                agent_name, failure_threshold, cooldown_seconds)
        return self.circuit_breakers[agent_name]

    def record_agent_run(self, agent_name: str, success: bool,
                          duration_ms: float, cost_usd: float = 0.0):
        if agent_name not in self.agent_stats:
            self.agent_stats[agent_name] = {
                'total_runs': 0,
                'successes': 0,
                'failures': 0,
                'total_duration_ms': 0,
                'total_cost_usd': 0.0,
                'last_run': None,
                'avg_duration_ms': 0,
                'error_rate': 0.0,
            }

        stats = self.agent_stats[agent_name]
        stats['total_runs'] += 1
        stats['total_duration_ms'] += duration_ms
        stats['total_cost_usd'] += cost_usd
        stats['last_run'] = datetime.now().isoformat()
        stats['avg_duration_ms'] = stats['total_duration_ms'] / stats['total_runs']

        if success:
            stats['successes'] += 1
            breaker = self.get_or_create_breaker(agent_name)
            breaker.record_success()
        else:
            stats['failures'] += 1
            breaker = self.get_or_create_breaker(agent_name)
            breaker.record_failure()

        stats['error_rate'] = stats['failures'] / stats['total_runs']

    def get_all_stats(self) -> Dict[str, Any]:
        return {
            'agents': self.agent_stats,
            'circuit_breakers': {
                name: cb.get_state()
                for name, cb in self.circuit_breakers.items()
            },
        }

    def get_health_summary(self) -> Dict[str, Any]:
        unhealthy = []
        for name, cb in self.circuit_breakers.items():
            if cb.is_open:
                unhealthy.append(name)

        return {
            'status': 'unhealthy' if unhealthy else 'healthy',
            'unhealthy_agents': unhealthy,
            'total_agents': len(self.agent_stats),
            'circuit_breakers_open': len(unhealthy),
        }


class CostTracker:
    """Redis-backed aggregation of LLM costs."""

    REDIS_PREFIX = "digestor:costs:"

    def __init__(self, redis_url: str = None):
        self._redis = None
        self._redis_url = redis_url or os.environ.get(
            'REDIS_URL', 'redis://localhost:6379/0')

    @property
    def redis(self):
        if self._redis is None:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(
                    self._redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def record_cost(self, agent_name: str, amount_usd: float,
                    detail: str = ""):
        if not self.redis:
            return
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            day_key = f"{self.REDIS_PREFIX}daily:{today}"
            agent_key = f"{self.REDIS_PREFIX}agent:{agent_name}"

            self.redis.incrbyfloat(day_key, amount_usd)
            self.redis.expire(day_key, 90 * 24 * 3600)  # 90 day retention

            self.redis.incrbyfloat(agent_key, amount_usd)
            self.redis.expire(agent_key, 90 * 24 * 3600)
        except Exception as e:
            logger.warning(f"Cost tracking failed: {e}")

    def get_daily_cost(self, date_str: str = None) -> float:
        if not self.redis:
            return 0.0
        date_str = date_str or datetime.now().strftime('%Y-%m-%d')
        try:
            val = self.redis.get(f"{self.REDIS_PREFIX}daily:{date_str}")
            return float(val) if val else 0.0
        except Exception:
            return 0.0

    def get_agent_cost(self, agent_name: str) -> float:
        if not self.redis:
            return 0.0
        try:
            val = self.redis.get(f"{self.REDIS_PREFIX}agent:{agent_name}")
            return float(val) if val else 0.0
        except Exception:
            return 0.0


# Singleton monitor instance
_monitor = AgentHealthMonitor()
_cost_tracker = CostTracker()


def get_monitor() -> AgentHealthMonitor:
    return _monitor


def get_cost_tracker() -> CostTracker:
    return _cost_tracker
