"""
File upload endpoint - replaces Supabase upload-document edge function.
Uploads PDFs to S3 and creates document_processing record.
Supports auto-project creation when project_name is provided without project_id.
"""

import os
import uuid
import structlog
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from services.s3_service import upload_file_to_s3
from db.models import DocumentProcessing, Project

logger = structlog.get_logger()
router = APIRouter()

MAX_FILE_SIZE = 400 * 1024 * 1024  # 400MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    project_hash: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    files_metadata: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to S3 and create a processing record.

    Accepts either:
    - project_id: existing project UUID
    - project_name (+ optional project_hash): auto-creates a new project
    """
    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size / 1024 / 1024:.1f}MB. Max: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    user_id = current_user["sub"]

    # Look up DB user by Cognito sub (owner_id FK references users.id, not cognito sub)
    from db.models import User
    user_stmt = select(User).where(User.cognito_sub == user_id)
    user_result = await db.execute(user_stmt)
    db_user = user_result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User profile not found")
    db_user_id = db_user.id

    # Resolve or create the project
    project = None
    resolved_project_id = None

    logger.info(
        "upload_request_params",
        project_id=project_id,
        project_hash=project_hash,
        project_name=project_name,
    )

    # Validate project_id is a real UUID if provided (ignore non-UUID strings)
    valid_project_uuid = None
    if project_id and project_id.strip():
        try:
            valid_project_uuid = uuid.UUID(project_id.strip())
        except ValueError:
            logger.warning("invalid_project_id_ignored", project_id=project_id)
            # Not a UUID — ignore and fall through to project_name path

    if valid_project_uuid:
        # Existing project by UUID
        stmt = select(Project).where(
            Project.id == valid_project_uuid,
            Project.owner_id == db_user_id,
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        resolved_project_id = project.id
    elif project_name:
        # Auto-create a project (or find existing by name + owner)
        stmt = select(Project).where(
            Project.name == project_name,
            Project.owner_id == db_user_id,
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()

        if not project:
            project = Project(
                name=project_name,
                owner_id=db_user_id,
                status="processing",
            )
            db.add(project)
            await db.flush()
            logger.info(
                "project_auto_created",
                project_id=str(project.id),
                name=project_name,
            )
        resolved_project_id = project.id
    else:
        raise HTTPException(
            status_code=400,
            detail="Either project_id or project_name is required",
        )

    # Upload to S3
    s3_key = f"uploads/{user_id}/{resolved_project_id}/{uuid.uuid4().hex}_{file.filename}"

    try:
        await upload_file_to_s3(content, s3_key, content_type=file.content_type)
    except Exception as e:
        logger.error("s3_upload_failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail="File upload failed")

    # Create processing record
    doc = DocumentProcessing(
        project_id=resolved_project_id,
        file_name=file.filename,
        s3_key=s3_key,
        file_size=file_size,
        status="uploading",
    )
    db.add(doc)
    await db.flush()

    logger.info(
        "document_uploaded",
        doc_id=str(doc.id),
        filename=file.filename,
        size=file_size,
        s3_key=s3_key,
        project_id=str(resolved_project_id),
    )

    # Return response matching what the frontend expects
    return {
        "id": str(doc.id),
        "processingId": str(doc.id),
        "filePath": s3_key,
        "file_name": file.filename,
        "s3_key": s3_key,
        "file_size": file_size,
        "status": "uploading",
        "project_id": str(resolved_project_id),
    }
