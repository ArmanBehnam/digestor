"""
Project management endpoints.
Replaces Supabase: submit-project, update-approved-project, get-finalized-project.
"""

import uuid
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.dependencies import get_db, get_current_user
from db.models import Project, DocumentProcessing, User

logger = structlog.get_logger()
router = APIRouter()


# --- Request Models ---

class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class SubmitProjectRequest(BaseModel):
    project_id: str


class ApproveProjectRequest(BaseModel):
    project_id: str
    approved: bool
    remarks: Optional[str] = None


# --- Endpoints ---

@router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects for the current user."""
    # Get user's db ID from cognito sub
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    # Build query
    stmt = select(Project).where(Project.owner_id == user.id)
    if status:
        stmt = stmt.where(Project.status == status)
    stmt = stmt.order_by(Project.updated_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Count total
    count_stmt = select(func.count(Project.id)).where(Project.owner_id == user.id)
    if status:
        count_stmt = count_stmt.where(Project.status == status)
    total = (await db.execute(count_stmt)).scalar()

    return {
        "items": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "version": p.version,
                "project_name": p.name,
                "project_hash": str(p.id),
                "project_id": str(p.id),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in projects
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/projects")
async def create_project(
    req: CreateProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    project = Project(
        name=req.name,
        description=req.description,
        owner_id=user.id,
        status="draft",
    )
    db.add(project)
    await db.flush()

    logger.info("project_created", project_id=str(project.id), name=req.name)
    return {
        "id": str(project.id),
        "name": project.name,
        "status": "draft",
    }


@router.get("/projects/pending")
async def list_pending_projects(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects pending supervisor review."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("supervisor", "admin")):
        raise HTTPException(status_code=403, detail="Supervisor or admin role required")

    stmt = select(Project).where(Project.status == "submitted").order_by(Project.submitted_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "version": p.version,
            "project_name": p.name,
            "project_hash": str(p.id),
            "project_id": str(p.id),
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details with document list."""
    stmt = select(Project).where(Project.id == uuid.UUID(project_id))
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch documents
    doc_stmt = select(DocumentProcessing).where(
        DocumentProcessing.project_id == project.id
    ).order_by(DocumentProcessing.created_at.desc())
    doc_result = await db.execute(doc_stmt)
    documents = doc_result.scalars().all()

    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "version": project.version,
        "notes": project.notes,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "submitted_at": project.submitted_at.isoformat() if project.submitted_at else None,
        "approved_at": project.approved_at.isoformat() if project.approved_at else None,
        "documents": [
            {
                "id": str(d.id),
                "file_name": d.file_name,
                "status": d.status,
                "processing_path": d.processing_path,
                "confidence_avg": d.confidence_avg,
                "processing_time_ms": d.processing_time_ms,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ],
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project details."""
    stmt = select(Project).where(Project.id == uuid.UUID(project_id))
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if req.name is not None:
        project.name = req.name
    if req.description is not None:
        project.description = req.description
    if req.notes is not None:
        project.notes = req.notes

    await db.flush()
    return {"message": "Project updated", "id": str(project.id)}


@router.post("/submit-project")
async def submit_project(
    req: SubmitProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit project for supervisor review."""
    stmt = select(Project).where(Project.id == uuid.UUID(req.project_id))
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status not in ("draft", "completed", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit project with status: {project.status}",
        )

    project.status = "submitted"
    project.submitted_at = datetime.utcnow()
    await db.flush()

    # Send notification email to supervisors
    from services.email_service import notify_supervisors_new_submission
    await notify_supervisors_new_submission(project, db)

    logger.info("project_submitted", project_id=str(project.id))
    return {"message": "Project submitted for review", "status": "submitted"}


@router.post("/approve-project")
async def approve_project(
    req: ApproveProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a submitted project (supervisor/admin only)."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("supervisor", "admin")):
        raise HTTPException(status_code=403, detail="Supervisor or admin role required")

    stmt = select(Project).where(Project.id == uuid.UUID(req.project_id))
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != "submitted":
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve/reject submitted projects (current: {project.status})",
        )

    # Get approver's db user
    approver_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    approver = (await db.execute(approver_stmt)).scalar_one_or_none()

    if req.approved:
        project.status = "approved"
        project.approved_at = datetime.utcnow()
        project.approved_by = approver.id if approver else None
    else:
        project.status = "rejected"
        if req.remarks:
            project.notes = (project.notes or "") + f"\n[Rejection] {req.remarks}"

    await db.flush()

    # Send notification to project owner
    from services.email_service import notify_project_decision
    await notify_project_decision(project, req.approved, req.remarks, db)

    action = "approved" if req.approved else "rejected"
    logger.info(f"project_{action}", project_id=str(project.id))
    return {"message": f"Project {action}", "status": project.status}
