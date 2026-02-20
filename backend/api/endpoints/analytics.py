"""
Analytics endpoints - processing metrics, accuracy trends, usage stats.
"""

import structlog
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from api.dependencies import get_db, get_current_user
from db.models import AnalyticsEvent, DocumentProcessing, UserFeedback, ResultEdit

logger = structlog.get_logger()
router = APIRouter()


@router.get("/analytics/overview")
async def analytics_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics overview for the dashboard."""
    since = datetime.utcnow() - timedelta(days=days)

    # Total documents processed
    doc_count = (await db.execute(
        select(func.count(DocumentProcessing.id)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.status == "complete",
        )
    )).scalar() or 0

    # Processing path breakdown
    pdfjs_count = (await db.execute(
        select(func.count(DocumentProcessing.id)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.processing_path == "pdfjs",
            DocumentProcessing.status == "complete",
        )
    )).scalar() or 0

    aws_count = (await db.execute(
        select(func.count(DocumentProcessing.id)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.processing_path == "aws",
            DocumentProcessing.status == "complete",
        )
    )).scalar() or 0

    # Average confidence
    avg_confidence = (await db.execute(
        select(func.avg(DocumentProcessing.confidence_avg)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.status == "complete",
            DocumentProcessing.confidence_avg.isnot(None),
        )
    )).scalar() or 0

    # Average processing time
    avg_time_pdfjs = (await db.execute(
        select(func.avg(DocumentProcessing.processing_time_ms)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.processing_path == "pdfjs",
            DocumentProcessing.status == "complete",
        )
    )).scalar() or 0

    avg_time_aws = (await db.execute(
        select(func.avg(DocumentProcessing.processing_time_ms)).where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.processing_path == "aws",
            DocumentProcessing.status == "complete",
        )
    )).scalar() or 0

    # Feedback summary
    thumbs_up = (await db.execute(
        select(func.count(UserFeedback.id)).where(
            UserFeedback.created_at >= since,
            UserFeedback.feedback_type == "thumbs_up",
        )
    )).scalar() or 0

    thumbs_down = (await db.execute(
        select(func.count(UserFeedback.id)).where(
            UserFeedback.created_at >= since,
            UserFeedback.feedback_type == "thumbs_down",
        )
    )).scalar() or 0

    return {
        "period_days": days,
        "total_documents": doc_count,
        "pdfjs_count": pdfjs_count,
        "aws_count": aws_count,
        "avg_confidence": round(avg_confidence, 4) if avg_confidence else 0,
        "avg_time_pdfjs_ms": int(avg_time_pdfjs) if avg_time_pdfjs else 0,
        "avg_time_aws_ms": int(avg_time_aws) if avg_time_aws else 0,
        "feedback_thumbs_up": thumbs_up,
        "feedback_thumbs_down": thumbs_down,
        "feedback_accuracy": (
            round(thumbs_up / (thumbs_up + thumbs_down), 4)
            if (thumbs_up + thumbs_down) > 0 else None
        ),
    }


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily processing trends for charts."""
    since = datetime.utcnow() - timedelta(days=days)

    # Daily processing counts
    daily_stmt = (
        select(
            func.date_trunc("day", DocumentProcessing.created_at).label("day"),
            func.count(DocumentProcessing.id).label("count"),
            func.avg(DocumentProcessing.confidence_avg).label("avg_confidence"),
            func.avg(DocumentProcessing.processing_time_ms).label("avg_time_ms"),
        )
        .where(
            DocumentProcessing.created_at >= since,
            DocumentProcessing.status == "complete",
        )
        .group_by(func.date_trunc("day", DocumentProcessing.created_at))
        .order_by(func.date_trunc("day", DocumentProcessing.created_at))
    )

    try:
        result = await db.execute(daily_stmt)
        rows = result.all()

        return {
            "trends": [
                {
                    "date": row.day.isoformat() if row.day else None,
                    "count": row.count,
                    "avg_confidence": round(float(row.avg_confidence), 4) if row.avg_confidence else 0,
                    "avg_time_ms": int(row.avg_time_ms) if row.avg_time_ms else 0,
                }
                for row in rows
            ],
        }
    except Exception as e:
        logger.error("analytics_trends_error", error=str(e))
        return {"trends": []}


@router.get("/analytics/edits")
async def analytics_edits(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get edit analytics - how many edits per category, per user, etc."""
    since = datetime.utcnow() - timedelta(days=days)

    # Total edits
    total_edits = (await db.execute(
        select(func.count(ResultEdit.id)).where(ResultEdit.created_at >= since)
    )).scalar() or 0

    # Edits by category
    category_stmt = (
        select(
            ResultEdit.category,
            func.count(ResultEdit.id).label("count"),
        )
        .where(ResultEdit.created_at >= since)
        .group_by(ResultEdit.category)
        .order_by(func.count(ResultEdit.id).desc())
    )
    category_rows = (await db.execute(category_stmt)).all()

    # Edits by user
    user_stmt = (
        select(
            ResultEdit.edited_by_full_name,
            func.count(ResultEdit.id).label("count"),
        )
        .where(ResultEdit.created_at >= since)
        .group_by(ResultEdit.edited_by_full_name)
        .order_by(func.count(ResultEdit.id).desc())
    )
    user_rows = (await db.execute(user_stmt)).all()

    return {
        "period_days": days,
        "total_edits": total_edits,
        "by_category": [
            {"category": row.category or "Unknown", "count": row.count}
            for row in category_rows
        ],
        "by_user": [
            {"user": row.edited_by_full_name or "Unknown", "count": row.count}
            for row in user_rows
        ],
    }
