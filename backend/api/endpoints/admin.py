"""
Admin endpoints - user management, settings, feedback.
"""

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import User, UserFeedback, FeedbackSurvey

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
            "roles": [u.role] if u.role else [],
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
    """List all feedback survey entries (admin only)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("admin", "supervisor")):
        raise HTTPException(status_code=403, detail="Admin or supervisor role required")

    stmt = select(FeedbackSurvey).order_by(FeedbackSurvey.created_at.desc()).limit(500)
    if status:
        stmt = stmt.where(FeedbackSurvey.status == status)

    result = await db.execute(stmt)
    surveys = result.scalars().all()

    # Build user lookup for email/name
    user_ids = {s.user_id for s in surveys}
    user_lookup = {}
    if user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in user_result.scalars().all():
            user_lookup[u.id] = u

    # Return data matching frontend FeedbackEntry interface
    # Survey data is stored in JSONB 'data' column
    return [
        {
            "id": str(s.id),
            "user_id": str(s.user_id),
            "user_email": user_lookup[s.user_id].email if s.user_id in user_lookup else "",
            "user_name": user_lookup[s.user_id].full_name if s.user_id in user_lookup else None,
            "status": s.status or "draft",
            "role_position": (s.data or {}).get("role_position"),
            "painful_part": (s.data or {}).get("painful_part"),
            "what_surprised": (s.data or {}).get("what_surprised"),
            "expected_not_do": (s.data or {}).get("expected_not_do"),
            "confusing_part": (s.data or {}).get("confusing_part"),
            "overall_satisfaction": (s.data or {}).get("overall_satisfaction"),
            "specific_project_issue": (s.data or {}).get("specific_project_issue"),
            "other_comments": (s.data or {}).get("other_comments"),
            "contact_for_followup": (s.data or {}).get("contact_for_followup"),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        }
        for s in surveys
    ]
