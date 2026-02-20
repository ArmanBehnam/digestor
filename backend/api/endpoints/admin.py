"""
Admin endpoints - user management, settings, feedback.
"""

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.dependencies import get_db, get_current_user
from db.models import User, UserFeedback, DocumentProcessing

logger = structlog.get_logger()
router = APIRouter()


class UpdateRoleRequest(BaseModel):
    role: str


class UpdateSettingsRequest(BaseModel):
    """Generic settings update."""
    pass  # Accept any JSON body


# ============================================================
# User management
# ============================================================

@router.get("/admin/users")
async def list_users(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin",)):
        raise HTTPException(status_code=403, detail="Admin role required")

    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "organization": u.organization,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.put("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role (admin only)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin",)):
        raise HTTPException(status_code=403, detail="Admin role required")

    if req.role not in ("engineer", "supervisor", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    stmt = select(User).where(User.id == uid)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = req.role
    await db.flush()

    logger.info("user_role_updated", user_id=user_id, new_role=req.role)
    return {"message": "Role updated", "user_id": user_id, "role": req.role}


@router.get("/admin/users/for-assignment")
async def get_users_for_assignment(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get users available for project assignment (supervisors)."""
    stmt = (
        select(User)
        .where(User.role.in_(["supervisor", "admin"]))
        .where(User.is_active == True)
        .order_by(User.full_name)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "user_id": str(u.id),
            "full_name": u.full_name or u.email,
            "email": u.email,
            "role": u.role,
        }
        for u in users
    ]


# ============================================================
# Admin settings (stub)
# ============================================================

@router.get("/admin/settings")
async def get_admin_settings(
    current_user: dict = Depends(get_current_user),
):
    """Get admin settings."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin",)):
        raise HTTPException(status_code=403, detail="Admin role required")

    # Return default settings
    return {
        "processing_mode": "auto",
        "max_file_size_mb": 50,
        "allowed_file_types": ["pdf"],
        "auto_fallback_enabled": True,
        "confidence_threshold": 70,
    }


@router.put("/admin/settings")
async def update_admin_settings(
    current_user: dict = Depends(get_current_user),
):
    """Update admin settings (stub)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin",)):
        raise HTTPException(status_code=403, detail="Admin role required")

    return {"message": "Settings updated"}


# ============================================================
# Admin feedback overview
# ============================================================

@router.get("/admin/feedback")
async def list_all_feedback(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all feedback entries (admin only)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin", "supervisor")):
        raise HTTPException(status_code=403, detail="Admin or supervisor role required")

    stmt = select(UserFeedback).order_by(UserFeedback.created_at.desc()).limit(500)
    if status:
        stmt = stmt.where(UserFeedback.feedback_type == status)

    result = await db.execute(stmt)
    feedbacks = result.scalars().all()

    return [
        {
            "id": str(f.id),
            "user_id": str(f.user_id),
            "document_id": str(f.document_id),
            "question_key": f.question_key,
            "answer_value": f.answer_value,
            "feedback_type": f.feedback_type,
            "corrected_value": f.corrected_value,
            "remarks": f.remarks,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in feedbacks
    ]
