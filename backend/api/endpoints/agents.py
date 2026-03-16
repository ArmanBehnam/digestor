# backend/api/endpoints/agents.py
"""API endpoints for agentic pipeline monitoring and control."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgenticToggle(BaseModel):
    enabled: bool


@router.get("/stats")
async def get_agent_stats():
    """Per-agent performance statistics."""
    from agents.monitoring import get_monitor
    monitor = get_monitor()
    return monitor.get_all_stats()


@router.get("/health")
async def get_agent_health():
    """Circuit breaker states and system health."""
    from agents.monitoring import get_monitor
    monitor = get_monitor()
    return monitor.get_health_summary()


@router.get("/decisions")
async def get_recent_decisions(limit: int = 50):
    """Recent agent decision log (from last pipeline run)."""
    # Decisions are stored per-run in the state; this endpoint reads
    # from Redis cache if available, otherwise returns empty.
    try:
        import os, json
        from redis import Redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        r = Redis.from_url(redis_url, decode_responses=True)
        raw = r.lrange("digestor:decisions:recent", 0, limit - 1)
        return {"decisions": [json.loads(d) for d in raw]}
    except Exception:
        return {"decisions": [], "note": "Decision log not available"}


@router.get("/costs")
async def get_cost_summary():
    """LLM cost tracking summary."""
    from agents.monitoring import get_cost_tracker
    tracker = get_cost_tracker()
    from datetime import datetime, timedelta
    today = datetime.now()
    costs = {}
    for i in range(7):
        date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        costs[date] = tracker.get_daily_cost(date)
    return {"daily_costs": costs}


@router.post("/toggle")
async def toggle_agentic_mode(body: AgenticToggle):
    """Toggle agentic vs legacy processing mode.

    Note: This only affects new processing jobs. Existing in-flight
    jobs will complete with their current mode.
    """
    try:
        from config.config_loader import CONFIG
        if CONFIG is None:
            raise HTTPException(status_code=500, detail="Config not loaded")
        if 'agentic' not in CONFIG:
            CONFIG['agentic'] = {}
        CONFIG['agentic']['enabled'] = body.enabled
        mode = "agentic" if body.enabled else "legacy"
        return {"message": f"Processing mode set to {mode}", "enabled": body.enabled}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
