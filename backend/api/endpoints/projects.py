"""
Project management endpoints.
Replaces Supabase: submit-project, update-approved-project, get-finalized-project.
Includes by-hash lookups, records management, notes, remarks, edit history.
"""

import uuid
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm.attributes import flag_modified

from api.dependencies import get_db, get_current_user
from db.models import (
    Project, DocumentProcessing, User, ProjectNote,
    ProjectRemark, ResultEdit,
)

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
    project_id: Optional[str] = None
    projectHash: Optional[str] = None
    projectId: Optional[str] = None
    projectName: Optional[str] = None
    results: Optional[list] = None
    feedback: Optional[list] = None
    hasEdits: Optional[bool] = None
    supervisorApproval: Optional[bool] = None
    supervisorId: Optional[str] = None
    supervisorName: Optional[str] = None
    pendingSnapshotJson: Optional[list] = None
    pendingSnapshotHtml: Optional[str] = None


class ApproveProjectRequest(BaseModel):
    project_id: str
    approved: bool
    remarks: Optional[str] = None


class UpdateByHashRequest(BaseModel):
    assigned_supervisor_id: Optional[str] = None
    assigned_supervisor_name: Optional[str] = None
    results: Optional[list] = None
    pending_snapshot_json: Optional[list] = None
    pending_snapshot_html: Optional[str] = None
    approval_status: Optional[str] = None
    review_note: Optional[str] = None
    status: Optional[str] = None


class UpdateRecordRequest(BaseModel):
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    results: Optional[list] = None
    pending_snapshot_json: Optional[list] = None
    is_edited: Optional[bool] = None
    updated_at: Optional[str] = None
    approval_status: Optional[str] = None
    saved_by_user_id: Optional[str] = None
    saved_by_full_name: Optional[str] = None


class CreateNoteRequest(BaseModel):
    text: str


class UpdateNoteRequest(BaseModel):
    text: str


class CreateRemarkRequest(BaseModel):
    project_hash: str
    row_id: str
    remark_text: str
    created_by_user_id: str
    created_by_full_name: str


class UpdateRemarkRequest(BaseModel):
    remark_text: str


class CreateResultEditRequest(BaseModel):
    project_hash: str
    row_id: str
    column_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    edited_by_user_id: str
    edited_by_full_name: str
    question_id: Optional[int] = None
    question_text: Optional[str] = None
    category: Optional[str] = None


class RepairProjectRequest(BaseModel):
    projectHash: str
    version: Optional[int] = None


class UpdateApprovedRequest(BaseModel):
    projectHash: str
    snapshotJson: list
    version: int


# --- Helper to look up user from cognito_sub ---

async def _get_db_user(db: AsyncSession, current_user: dict) -> User:
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")
    return user


def _project_to_dict(p: Project, include_snapshot: bool = False, owner_name: str = None, supervisor_name: str = None) -> dict:
    """Convert project to frontend-expected dict.

    Pass owner_name and supervisor_name explicitly to avoid lazy-loading issues.
    """
    d = {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "approval_status": p.approval_status,
        "version": p.version,
        "notes": p.notes,
        "project_name": p.name,
        "project_hash": str(p.id),
        "project_id": str(p.id),
        "files_metadata": p.files_metadata or [],
        "review_note": p.review_note,
        "assigned_supervisor_id": str(p.assigned_supervisor_id) if p.assigned_supervisor_id else None,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if include_snapshot:
        d["pending_snapshot_json"] = p.pending_snapshot_json
        d["pending_snapshot_html"] = p.pending_snapshot_html
    if owner_name:
        d["submitted_by_full_name"] = owner_name
    if supervisor_name:
        d["assigned_supervisor_name"] = supervisor_name
    return d


async def _project_to_dict_with_relations(p: Project, db: AsyncSession, include_snapshot: bool = False) -> dict:
    """Convert project to dict, eagerly loading owner/supervisor names."""
    owner_name = None
    supervisor_name = None

    if p.owner_id:
        owner = (await db.execute(select(User).where(User.id == p.owner_id))).scalar_one_or_none()
        if owner:
            owner_name = owner.full_name or owner.email
    if p.assigned_supervisor_id:
        sup = (await db.execute(select(User).where(User.id == p.assigned_supervisor_id))).scalar_one_or_none()
        if sup:
            supervisor_name = sup.full_name or sup.email

    return _project_to_dict(p, include_snapshot=include_snapshot, owner_name=owner_name, supervisor_name=supervisor_name)


# ============================================================
# Standard CRUD endpoints
# ============================================================

@router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    approval_status: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects for the current user."""
    user = await _get_db_user(db, current_user)

    # Build query
    stmt = select(Project).where(Project.owner_id == user.id)
    if status:
        stmt = stmt.where(Project.status == status)
    if approval_status:
        statuses = [s.strip() for s in approval_status.split(",")]
        stmt = stmt.where(Project.approval_status.in_(statuses))

    # Sort
    if sort_by == "name":
        order = Project.name.asc() if sort_order == "asc" else Project.name.desc()
    elif sort_by == "created_at":
        order = Project.created_at.asc() if sort_order == "asc" else Project.created_at.desc()
    else:
        order = Project.updated_at.desc()
    stmt = stmt.order_by(order)
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Count total
    count_stmt = select(func.count(Project.id)).where(Project.owner_id == user.id)
    if status:
        count_stmt = count_stmt.where(Project.status == status)
    if approval_status:
        count_stmt = count_stmt.where(Project.approval_status.in_(statuses))
    total = (await db.execute(count_stmt)).scalar()

    items = []
    for p in projects:
        items.append(await _project_to_dict_with_relations(p, db))

    return {
        "items": items,
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
    user = await _get_db_user(db, current_user)

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


# ============================================================
# Pending projects (supervisor queue)
# ============================================================

@router.get("/projects/pending")
async def list_pending_projects(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects pending supervisor review."""
    user_groups = current_user.get("cognito:groups", [])
    if not any(g in user_groups for g in ("supervisor", "admin")):
        raise HTTPException(status_code=403, detail="Supervisor or admin role required")

    stmt = (
        select(Project)
        .where(Project.status == "submitted")
        .order_by(Project.submitted_at.desc())
    )
    result = await db.execute(stmt)
    projects = result.scalars().all()

    result_list = []
    for p in projects:
        result_list.append(await _project_to_dict_with_relations(p, db, include_snapshot=True))
    return result_list


# ============================================================
# Finalized project (replaces Supabase edge function)
# ============================================================

@router.get("/projects/finalized")
async def get_finalized_project(
    project_key: str = Query(...),
    version: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get finalized/approved project data by project_key (hash/id).

    Returns nested structure expected by the frontend:
    { project_key, version, meta, snapshots, artifacts, audit, documents }
    """
    try:
        project_uuid = uuid.UUID(project_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project key")

    stmt = select(Project).where(Project.id == project_uuid)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch documents
    doc_stmt = (
        select(DocumentProcessing)
        .where(DocumentProcessing.project_id == project.id)
        .order_by(DocumentProcessing.created_at.desc())
    )
    docs = (await db.execute(doc_stmt)).scalars().all()

    # Merge all document results into one snapshot
    all_results = []
    for doc in docs:
        if doc.results:
            all_results.extend(doc.results)

    # Resolve owner / supervisor / approver names
    owner_name = None
    supervisor_name = None
    approver_name = None
    if project.owner_id:
        owner = (await db.execute(select(User).where(User.id == project.owner_id))).scalar_one_or_none()
        if owner:
            owner_name = owner.full_name or owner.email
    if project.assigned_supervisor_id:
        sup = (await db.execute(select(User).where(User.id == project.assigned_supervisor_id))).scalar_one_or_none()
        if sup:
            supervisor_name = sup.full_name or sup.email
    if project.approved_by:
        approver = (await db.execute(select(User).where(User.id == project.approved_by))).scalar_one_or_none()
        if approver:
            approver_name = approver.full_name or approver.email

    # Build snapshot JSON — fall back to merged results if empty
    snapshot_json = project.pending_snapshot_json
    if not snapshot_json and all_results:
        snapshot_json = all_results

    # Primary file path from first document
    primary_file_path = docs[0].s3_key if docs else None

    # Fetch edit history for audit log
    audit = []
    try:
        from db.models import ResultEdit
        edit_stmt = (
            select(ResultEdit)
            .where(ResultEdit.project_hash == project_key)
            .order_by(ResultEdit.created_at.desc())
        )
        edits = (await db.execute(edit_stmt)).scalars().all()
        audit = [
            {
                "id": str(e.id),
                "row_id": e.row_id,
                "column_name": e.column_name,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "edited_by_full_name": e.edited_by_full_name,
                "edited_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in edits
        ]
    except Exception:
        audit = []

    # Build files_metadata from documents if not set on project
    files_metadata = project.files_metadata
    if not files_metadata and docs:
        files_metadata = [
            {
                "name": d.file_name,
                "path": d.s3_key,
                "size": d.file_size or 0,
            }
            for d in docs
        ]

    # Build nested response matching frontend expectations
    return {
        "project_key": str(project.id),
        "version": project.version or 1,
        "meta": {
            "id": str(project.id),
            "project_id": str(project.id),
            "project_name": project.name,
            "submitted_by_full_name": owner_name,
            "submitted_at": project.submitted_at.isoformat() if project.submitted_at else None,
            "approved_by_full_name": approver_name,
            "approved_at": project.approved_at.isoformat() if project.approved_at else None,
            "finalized_by_full_name": approver_name,
            "finalized_at": project.approved_at.isoformat() if project.approved_at else None,
            "approval_status": project.approval_status,
            "files_metadata": files_metadata or [],
            "file_path": primary_file_path,
            "notes": project.notes or "",
            "assigned_supervisor_name": supervisor_name,
            "assigned_supervisor_id": str(project.assigned_supervisor_id) if project.assigned_supervisor_id else None,
            "review_note": project.review_note,
            "status": project.status,
        },
        "snapshots": {
            "html": project.pending_snapshot_html,
            "json": snapshot_json,
        },
        "artifacts": [
            # CSV and JSON export artifacts — built from S3 keys if available
            {"type": "CSV", "path": f"exports/{project.id}/results.csv"},
            {"type": "JSON", "path": f"exports/{project.id}/results.json"},
        ],
        "audit": audit,
        "documents": [
            {
                "id": str(d.id),
                "file_name": d.file_name,
                "s3_key": d.s3_key,
                "file_size": d.file_size,
                "status": d.status,
                "processing_path": d.processing_path,
                "confidence_avg": d.confidence_avg,
                "processing_time_ms": d.processing_time_ms,
                "results": d.results or [],
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    }


# ============================================================
# Repair project
# ============================================================

@router.post("/projects/repair")
async def repair_project(
    req: RepairProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Repair/rebuild project data."""
    try:
        project_uuid = uuid.UUID(req.projectHash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    stmt = select(Project).where(Project.id == project_uuid)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Rebuild snapshot from documents
    doc_stmt = select(DocumentProcessing).where(
        DocumentProcessing.project_id == project.id
    )
    docs = (await db.execute(doc_stmt)).scalars().all()

    all_results = []
    for doc in docs:
        if doc.results:
            all_results.extend(doc.results)

    project.pending_snapshot_json = all_results
    flag_modified(project, "pending_snapshot_json")
    await db.flush()

    logger.info("project_repaired", project_id=str(project.id))
    return {"message": "Project repaired", "results_count": len(all_results)}


# ============================================================
# Update approved project
# ============================================================

@router.post("/projects/update-approved")
async def update_approved_project(
    req: UpdateApprovedRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update approved project snapshot."""
    try:
        project_uuid = uuid.UUID(req.projectHash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    stmt = select(Project).where(Project.id == project_uuid)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.pending_snapshot_json = req.snapshotJson
    project.version = req.version
    flag_modified(project, "pending_snapshot_json")
    await db.flush()

    return {"message": "Approved project updated", "version": req.version}


# ============================================================
# By-hash endpoints (for supervisor review workflow)
# ============================================================

@router.get("/projects/by-hash/{project_hash}")
async def get_project_by_hash(
    project_hash: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project by its hash (UUID string)."""
    try:
        project_uuid = uuid.UUID(project_hash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    stmt = select(Project).where(Project.id == project_uuid)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch documents for files_metadata enrichment
    doc_stmt = select(DocumentProcessing).where(
        DocumentProcessing.project_id == project.id
    ).order_by(DocumentProcessing.created_at.desc())
    docs = (await db.execute(doc_stmt)).scalars().all()

    data = await _project_to_dict_with_relations(project, db, include_snapshot=True)

    # If files_metadata is empty, build from documents
    if not data.get("files_metadata") and docs:
        data["files_metadata"] = [
            {
                "name": d.file_name,
                "path": d.s3_key,
                "size": d.file_size or 0,
            }
            for d in docs
        ]

    # If snapshot is empty, build from all doc results
    if not data.get("pending_snapshot_json"):
        all_results = []
        for d in docs:
            if d.results:
                all_results.extend(d.results)
        if all_results:
            data["pending_snapshot_json"] = all_results

    data["documents"] = [
        {
            "id": str(d.id),
            "file_name": d.file_name,
            "s3_key": d.s3_key,
            "file_size": d.file_size,
            "status": d.status,
            "processing_path": d.processing_path,
            "confidence_avg": d.confidence_avg,
            "processing_time_ms": d.processing_time_ms,
            "results": d.results or [],
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]

    return data


@router.get("/projects/by-hash/{project_hash}/records")
async def get_project_records_by_hash(
    project_hash: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get processing records for a project by hash."""
    try:
        project_uuid = uuid.UUID(project_hash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    stmt = (
        select(DocumentProcessing)
        .where(DocumentProcessing.project_id == project_uuid)
        .order_by(DocumentProcessing.created_at.desc())
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "file_name": d.file_name,
            "file_path": d.s3_key,
            "s3_key": d.s3_key,
            "file_size": d.file_size,
            "status": d.status,
            "processing_path": d.processing_path,
            "results": d.results or [],
            "confidence_avg": d.confidence_avg,
            "processing_time_ms": d.processing_time_ms,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.put("/projects/by-hash/{project_hash}")
async def update_project_by_hash(
    project_hash: str,
    req: UpdateByHashRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project by hash (supervisor reassignment, snapshot updates, etc.)."""
    try:
        project_uuid = uuid.UUID(project_hash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    stmt = select(Project).where(Project.id == project_uuid)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if req.assigned_supervisor_id is not None:
        try:
            project.assigned_supervisor_id = uuid.UUID(req.assigned_supervisor_id) if req.assigned_supervisor_id else None
        except ValueError:
            pass
    if req.results is not None:
        # Update first document's results
        doc_stmt = select(DocumentProcessing).where(
            DocumentProcessing.project_id == project.id
        ).order_by(DocumentProcessing.created_at.asc()).limit(1)
        doc = (await db.execute(doc_stmt)).scalar_one_or_none()
        if doc:
            doc.results = req.results
            flag_modified(doc, "results")
    if req.pending_snapshot_json is not None:
        project.pending_snapshot_json = req.pending_snapshot_json
        flag_modified(project, "pending_snapshot_json")
    if req.pending_snapshot_html is not None:
        project.pending_snapshot_html = req.pending_snapshot_html
    if req.approval_status is not None:
        project.approval_status = req.approval_status
    if req.review_note is not None:
        project.review_note = req.review_note
    if req.status is not None:
        project.status = req.status

    await db.flush()
    logger.info("project_updated_by_hash", project_hash=project_hash)
    return {"message": "Project updated", "id": str(project.id)}


@router.get("/projects/by-hash/{project_hash}/edits")
async def get_edit_history(
    project_hash: str,
    row_id: Optional[str] = None,
    notes_only: Optional[str] = None,
    preview: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get edit history for a project by hash."""
    stmt = select(ResultEdit).where(ResultEdit.project_hash == project_hash)
    if row_id:
        stmt = stmt.where(ResultEdit.row_id == row_id)
    if notes_only == "true":
        stmt = stmt.where(ResultEdit.column_name == "Note")
    stmt = stmt.order_by(ResultEdit.created_at.desc())

    result = await db.execute(stmt)
    edits = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "project_hash": e.project_hash,
            "row_id": e.row_id,
            "column_name": e.column_name,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "edited_by_user_id": str(e.edited_by_user_id),
            "edited_by_full_name": e.edited_by_full_name,
            "edited_at": e.created_at.isoformat() if e.created_at else None,
            "question_id": e.question_id,
            "question_text": e.question_text,
            "category": e.category,
        }
        for e in edits
    ]


# ============================================================
# Result edits (audit trail)
# ============================================================

@router.post("/projects/result-edits")
async def create_result_edit(
    req: CreateResultEditRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an audit trail entry for a result edit."""
    # Look up project by hash
    try:
        project_uuid = uuid.UUID(req.project_hash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    edit = ResultEdit(
        project_id=project_uuid,
        project_hash=req.project_hash,
        row_id=req.row_id,
        column_name=req.column_name,
        old_value=req.old_value,
        new_value=req.new_value,
        edited_by_user_id=uuid.UUID(req.edited_by_user_id),
        edited_by_full_name=req.edited_by_full_name,
        question_id=req.question_id,
        question_text=req.question_text,
        category=req.category,
    )
    db.add(edit)
    await db.flush()

    logger.info("result_edit_created", project_hash=req.project_hash, row_id=req.row_id)
    return {
        "id": str(edit.id),
        "project_hash": edit.project_hash,
        "row_id": edit.row_id,
        "column_name": edit.column_name,
        "edited_at": edit.created_at.isoformat() if edit.created_at else None,
    }


# ============================================================
# Processing records endpoints
# ============================================================

@router.put("/projects/records/{record_id}")
async def update_record(
    record_id: str,
    req: UpdateRecordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a processing record by its ID."""
    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid record ID")

    stmt = select(DocumentProcessing).where(DocumentProcessing.id == record_uuid)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Record not found")

    if req.results is not None:
        doc.results = req.results
        flag_modified(doc, "results")
    if req.project_name is not None:
        # Update project name too
        project = await db.get(Project, doc.project_id)
        if project:
            project.name = req.project_name
    if req.pending_snapshot_json is not None:
        project = await db.get(Project, doc.project_id)
        if project:
            project.pending_snapshot_json = req.pending_snapshot_json
            flag_modified(project, "pending_snapshot_json")
    if req.approval_status is not None:
        project = await db.get(Project, doc.project_id)
        if project:
            project.approval_status = req.approval_status

    await db.flush()
    return {"message": "Record updated", "id": str(doc.id)}


@router.delete("/projects/records/{record_id}")
async def delete_record(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a processing record."""
    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid record ID")

    stmt = select(DocumentProcessing).where(DocumentProcessing.id == record_uuid)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Record not found")

    await db.delete(doc)
    await db.flush()
    return {"message": "Record deleted"}


@router.get("/projects/records/{record_id}/text")
async def get_document_text(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted text for a processing record."""
    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid record ID")

    # Check document exists
    stmt = select(DocumentProcessing).where(DocumentProcessing.id == record_uuid)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Record not found")

    # Get text from chunks
    from db.models import DocumentChunk
    chunk_stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == record_uuid)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = (await db.execute(chunk_stmt)).scalars().all()

    text = "\n\n".join(c.content for c in chunks)
    return {"text": text, "chunk_count": len(chunks)}


@router.get("/projects/records/{record_id}/metrics")
async def get_processing_metrics(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get processing metrics for a record."""
    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid record ID")

    stmt = select(DocumentProcessing).where(DocumentProcessing.id == record_uuid)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Record not found")

    return {
        "processing_time_ms": doc.processing_time_ms,
        "confidence_avg": doc.confidence_avg,
        "processing_path": doc.processing_path,
        "processing_mode": doc.processing_mode,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "fallback_reason": doc.fallback_reason,
        "status": doc.status,
    }


# ============================================================
# Remarks endpoints
# ============================================================

@router.get("/projects/remarks/{project_hash}")
async def get_project_remarks(
    project_hash: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all remarks for a project."""
    stmt = (
        select(ProjectRemark)
        .where(ProjectRemark.project_hash == project_hash)
        .order_by(ProjectRemark.created_at.desc())
    )
    result = await db.execute(stmt)
    remarks = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "project_hash": r.project_hash,
            "row_id": r.row_id,
            "remark_text": r.remark_text,
            "created_by_user_id": str(r.created_by_user_id),
            "created_by_full_name": r.created_by_full_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in remarks
    ]


@router.post("/projects/remarks")
async def create_remark(
    req: CreateRemarkRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a remark on a project row."""
    # Look up project
    try:
        project_uuid = uuid.UUID(req.project_hash)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project hash")

    remark = ProjectRemark(
        project_id=project_uuid,
        project_hash=req.project_hash,
        row_id=req.row_id,
        remark_text=req.remark_text,
        created_by_user_id=uuid.UUID(req.created_by_user_id),
        created_by_full_name=req.created_by_full_name,
    )
    db.add(remark)
    await db.flush()

    return {
        "id": str(remark.id),
        "project_hash": remark.project_hash,
        "row_id": remark.row_id,
        "remark_text": remark.remark_text,
        "created_at": remark.created_at.isoformat() if remark.created_at else None,
    }


@router.put("/projects/remarks/{remark_id}")
async def update_remark(
    remark_id: str,
    req: UpdateRemarkRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a remark."""
    try:
        remark_uuid = uuid.UUID(remark_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid remark ID")

    stmt = select(ProjectRemark).where(ProjectRemark.id == remark_uuid)
    remark = (await db.execute(stmt)).scalar_one_or_none()
    if not remark:
        raise HTTPException(status_code=404, detail="Remark not found")

    remark.remark_text = req.remark_text
    await db.flush()
    return {"message": "Remark updated", "id": str(remark.id)}


@router.delete("/projects/remarks/{remark_id}")
async def delete_remark(
    remark_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a remark."""
    try:
        remark_uuid = uuid.UUID(remark_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid remark ID")

    stmt = select(ProjectRemark).where(ProjectRemark.id == remark_uuid)
    remark = (await db.execute(stmt)).scalar_one_or_none()
    if not remark:
        raise HTTPException(status_code=404, detail="Remark not found")

    await db.delete(remark)
    await db.flush()
    return {"message": "Remark deleted"}


# ============================================================
# Standard project CRUD (by ID)
# ============================================================

@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details with document list."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    stmt = select(Project).where(Project.id == pid)
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

    data = await _project_to_dict_with_relations(project, db, include_snapshot=True)
    data["documents"] = [
        {
            "id": str(d.id),
            "file_name": d.file_name,
            "s3_key": d.s3_key,
            "status": d.status,
            "processing_path": d.processing_path,
            "confidence_avg": d.confidence_avg,
            "processing_time_ms": d.processing_time_ms,
            "results": d.results or [],
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in documents
    ]
    return data


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project details."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    stmt = select(Project).where(Project.id == pid)
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


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    stmt = select(Project).where(Project.id == pid)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    await db.flush()
    return {"message": "Project deleted"}


# ============================================================
# Notes endpoints
# ============================================================

@router.get("/projects/{project_id}/notes")
async def get_project_notes(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notes for a project."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    stmt = (
        select(ProjectNote)
        .where(ProjectNote.project_id == pid)
        .order_by(ProjectNote.created_at.desc())
    )
    result = await db.execute(stmt)
    notes = result.scalars().all()

    return [
        {
            "id": str(n.id),
            "project_id": str(n.project_id),
            "user_id": str(n.user_id),
            "text": n.text,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }
        for n in notes
    ]


@router.post("/projects/{project_id}/notes")
async def add_project_note(
    project_id: str,
    req: CreateNoteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a note to a project."""
    user = await _get_db_user(db, current_user)

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    note = ProjectNote(
        project_id=pid,
        user_id=user.id,
        text=req.text,
    )
    db.add(note)
    await db.flush()

    return {
        "id": str(note.id),
        "project_id": str(note.project_id),
        "user_id": str(note.user_id),
        "text": note.text,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


@router.put("/projects/{project_id}/notes/{note_id}")
async def update_project_note(
    project_id: str,
    note_id: str,
    req: UpdateNoteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project note."""
    try:
        note_uuid = uuid.UUID(note_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid note ID")

    stmt = select(ProjectNote).where(ProjectNote.id == note_uuid)
    note = (await db.execute(stmt)).scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    note.text = req.text
    await db.flush()
    return {"message": "Note updated", "id": str(note.id)}


@router.delete("/projects/{project_id}/notes/{note_id}")
async def delete_project_note(
    project_id: str,
    note_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project note."""
    try:
        note_uuid = uuid.UUID(note_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid note ID")

    stmt = select(ProjectNote).where(ProjectNote.id == note_uuid)
    note = (await db.execute(stmt)).scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    await db.delete(note)
    await db.flush()
    return {"message": "Note deleted"}


# ============================================================
# Submit & Approve
# ============================================================

@router.post("/submit-project")
async def submit_project(
    req: SubmitProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit project for supervisor review. Accepts both simple and full payloads."""
    # Determine project ID from various fields
    pid_str = req.project_id or req.projectHash or req.projectId
    if not pid_str:
        raise HTTPException(status_code=400, detail="project_id or projectHash required")

    try:
        project_uuid = uuid.UUID(pid_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    stmt = select(Project).where(Project.id == project_uuid)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status not in ("draft", "completed", "rejected", "complete", "processing", "submitted"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit project with status: {project.status}",
        )

    project.status = "submitted"
    project.submitted_at = datetime.utcnow()

    # Handle extended payload
    if req.pendingSnapshotJson is not None:
        project.pending_snapshot_json = req.pendingSnapshotJson
        flag_modified(project, "pending_snapshot_json")
    if req.pendingSnapshotHtml is not None:
        project.pending_snapshot_html = req.pendingSnapshotHtml
    if req.supervisorId:
        try:
            project.assigned_supervisor_id = uuid.UUID(req.supervisorId)
        except ValueError:
            pass
    if req.projectName:
        project.name = req.projectName
    if req.results is not None:
        # Save results to first document
        doc_stmt = select(DocumentProcessing).where(
            DocumentProcessing.project_id == project.id
        ).order_by(DocumentProcessing.created_at.asc()).limit(1)
        doc = (await db.execute(doc_stmt)).scalar_one_or_none()
        if doc:
            doc.results = req.results
            flag_modified(doc, "results")

    project.approval_status = "pending"

    # Populate files_metadata from documents if not already set
    if not project.files_metadata:
        doc_meta_stmt = select(DocumentProcessing).where(
            DocumentProcessing.project_id == project.id
        ).order_by(DocumentProcessing.created_at.asc())
        doc_rows = (await db.execute(doc_meta_stmt)).scalars().all()
        if doc_rows:
            project.files_metadata = [
                {
                    "name": d.file_name,
                    "path": d.s3_key,
                    "size": d.file_size or 0,
                }
                for d in doc_rows
            ]
            flag_modified(project, "files_metadata")

    await db.flush()

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
        project.approval_status = "approved"
        project.approved_at = datetime.utcnow()
        project.approved_by = approver.id if approver else None
    else:
        project.status = "rejected"
        project.approval_status = "rejected"
        if req.remarks:
            project.review_note = req.remarks

    await db.flush()

    action = "approved" if req.approved else "rejected"
    logger.info(f"project_{action}", project_id=str(project.id))
    return {"message": f"Project {action}", "status": project.status}
