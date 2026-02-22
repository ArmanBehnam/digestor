"""
Feedback survey endpoints.
"""

import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import User, FeedbackSurvey

logger = structlog.get_logger()
router = APIRouter()


class SurveyDataRequest(BaseModel):
    data: Optional[dict] = None
    # Accept arbitrary fields
    class Config:
        extra = "allow"


@router.get("/feedback/survey")
async def get_feedback_survey(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's feedback survey (draft or submitted)."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        select(FeedbackSurvey)
        .where(FeedbackSurvey.user_id == user.id)
        .order_by(FeedbackSurvey.created_at.desc())
        .limit(1)
    )
    survey = (await db.execute(stmt)).scalar_one_or_none()

    if not survey:
        return {"id": None, "data": {}, "status": "draft"}

    return {
        "id": str(survey.id),
        "data": survey.data or {},
        "status": survey.status,
        "submitted_at": survey.submitted_at.isoformat() if survey.submitted_at else None,
        "created_at": survey.created_at.isoformat() if survey.created_at else None,
    }


@router.post("/feedback/survey")
async def save_feedback_survey(
    req: SurveyDataRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save/update feedback survey draft."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find existing draft or create new
    stmt = (
        select(FeedbackSurvey)
        .where(FeedbackSurvey.user_id == user.id, FeedbackSurvey.status == "draft")
        .order_by(FeedbackSurvey.created_at.desc())
        .limit(1)
    )
    survey = (await db.execute(stmt)).scalar_one_or_none()

    survey_data = req.data or req.model_dump(exclude={"data"}, exclude_none=True)

    if survey:
        survey.data = survey_data
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(survey, "data")
    else:
        survey = FeedbackSurvey(
            user_id=user.id,
            data=survey_data,
            status="draft",
        )
        db.add(survey)

    await db.flush()
    return {"message": "Survey saved", "id": str(survey.id)}


@router.post("/feedback/survey/submit")
async def submit_feedback_survey(
    req: SurveyDataRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit (finalize) feedback survey."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find existing draft
    stmt = (
        select(FeedbackSurvey)
        .where(FeedbackSurvey.user_id == user.id, FeedbackSurvey.status == "draft")
        .order_by(FeedbackSurvey.created_at.desc())
        .limit(1)
    )
    survey = (await db.execute(stmt)).scalar_one_or_none()

    survey_data = req.data or req.model_dump(exclude={"data"}, exclude_none=True)

    if survey:
        survey.data = survey_data
        survey.status = "submitted"
        survey.submitted_at = datetime.utcnow()
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(survey, "data")
    else:
        survey = FeedbackSurvey(
            user_id=user.id,
            data=survey_data,
            status="submitted",
            submitted_at=datetime.utcnow(),
        )
        db.add(survey)

    await db.flush()
    return {"message": "Survey submitted", "id": str(survey.id)}
