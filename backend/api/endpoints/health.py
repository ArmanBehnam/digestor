"""Health check endpoint."""

import os
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.utcnow().isoformat(),
    }
