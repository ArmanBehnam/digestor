"""Health check endpoint with DB and Redis connectivity verification."""

import os
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check that verifies DB and Redis are reachable."""
    checks = {}

    # Check database connectivity
    try:
        from db.session import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)[:100]}"

    # Check Redis connectivity
    try:
        import redis as redis_lib
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        r.ping()
        r.close()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)[:100]}"

    all_healthy = all(v == "healthy" for v in checks.values())

    response = {
        "status": "healthy" if all_healthy else "degraded",
        "version": "2.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    if not all_healthy:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response, status_code=503)

    return response
