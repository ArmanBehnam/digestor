"""
Results endpoints - fetch processing results and provide feedback.
"""

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import DocumentProcessing, Project, UserFeedback, User

logger = structlog.get_logger()
router = APIRouter()


class FeedbackRequest(BaseModel):
    document_id: str
    question_key: str
    feedback_type: str  # thumbs_up, thumbs_down
    corrected_value: Optional[str] = None
    remarks: Optional[str] = None


class UpdateResultRequest(BaseModel):
    document_id: str
    question_key: str
    new_value: str
    remarks: Optional[str] = None


@router.get("/results/{document_id}")
async def get_results(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get processing results for a document."""
    stmt = select(DocumentProcessing).where(
        DocumentProcessing.id == uuid.UUID(document_id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get existing feedback for this document
    fb_stmt = select(UserFeedback).where(UserFeedback.document_id == doc.id)
    fb_result = await db.execute(fb_stmt)
    feedbacks = {fb.question_key: fb.feedback_type for fb in fb_result.scalars().all()}

    return {
        "document_id": str(doc.id),
        "file_name": doc.file_name,
        "status": doc.status,
        "processing_path": doc.processing_path,
        "confidence_avg": doc.confidence_avg,
        "processing_time_ms": doc.processing_time_ms,
        "fallback_reason": doc.fallback_reason,
        "results": doc.results or [],
        "feedback": feedbacks,
    }


@router.get("/results/project/{project_id}")
async def get_project_results(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get combined processing results for a project (all documents merged)."""
    project_stmt = select(Project).where(
        Project.id == uuid.UUID(project_id)
    )
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all documents for status tracking
    doc_stmt = (
        select(DocumentProcessing)
        .where(DocumentProcessing.project_id == uuid.UUID(project_id))
        .order_by(DocumentProcessing.created_at.asc())
    )
    docs = (await db.execute(doc_stmt)).scalars().all()

    # Determine overall status from all documents
    # Priority: processing > error > complete (so user sees progress, not premature failure)
    statuses = [d.status for d in docs]
    processing_statuses = ("llm_processing", "queued", "ocr_processing", "vlm_processing")
    has_processing = any(s in processing_statuses for s in statuses)
    has_error = any(s in ("failed", "error") for s in statuses)
    all_complete = all(s == "complete" for s in statuses)

    # Self-healing: if worker completed but only updated the primary document,
    # fix the remaining stuck docs. ONLY triggers when at least one doc is
    # already "complete" (meaning the worker DID finish). This avoids
    # prematurely fixing docs that are legitimately queued for the worker.
    # IMPORTANT: Do NOT overwrite documents that already have results —
    # the agentic pipeline may have saved newer results that the snapshot
    # hasn't been updated with yet.
    if project.pending_snapshot_json and not all_complete:
        any_complete = any(s == "complete" for s in statuses)
        if any_complete and has_processing:
            try:
                for d in docs:
                    if d.status in processing_statuses and d.results is None:
                        old_status = d.status
                        d.status = "complete"
                        d.results = project.pending_snapshot_json
                        logger.info("auto_fixed_stuck_document",
                                    doc_id=str(d.id), old_status=old_status)
                await db.flush()
                statuses = [d.status for d in docs]
                has_processing = any(s in processing_statuses for s in statuses)
                all_complete = all(s == "complete" for s in statuses)
            except Exception as fix_err:
                logger.warning("auto_fix_stuck_failed", error=str(fix_err))

    if all_complete:
        overall_status = "complete"
    elif has_processing:
        # Still working — don't show error even if some docs failed
        overall_status = "processing"
    elif has_error:
        overall_status = "error"
    else:
        overall_status = statuses[0] if statuses else "unknown"

    # Prefer project-level combined results
    results = project.pending_snapshot_json
    if not results and docs:
        # Fallback: use first complete document's results
        for d in docs:
            if d.results:
                results = d.results
                break

    # Calculate aggregate metrics
    avg_confidence = None
    processing_time_ms = None
    if docs:
        confidences = [d.confidence_avg for d in docs if d.confidence_avg]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        times = [d.processing_time_ms for d in docs if d.processing_time_ms]
        processing_time_ms = max(times) if times else None

    return {
        "project_id": project_id,
        "status": overall_status,
        "results": results or [],
        "confidence_avg": avg_confidence,
        "processing_time_ms": processing_time_ms,
        "documents": [
            {
                "document_id": str(d.id),
                "file_name": d.file_name,
                "status": d.status,
                "processing_path": d.processing_path,
                "fallback_reason": d.fallback_reason,
            }
            for d in docs
        ],
    }


@router.post("/results/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit thumbs up/down feedback on an answer."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Upsert feedback
    existing_stmt = select(UserFeedback).where(
        UserFeedback.user_id == user.id,
        UserFeedback.document_id == uuid.UUID(req.document_id),
        UserFeedback.question_key == req.question_key,
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()

    if existing:
        existing.feedback_type = req.feedback_type
        existing.corrected_value = req.corrected_value
        existing.remarks = req.remarks
    else:
        feedback = UserFeedback(
            user_id=user.id,
            document_id=uuid.UUID(req.document_id),
            question_key=req.question_key,
            feedback_type=req.feedback_type,
            corrected_value=req.corrected_value,
            remarks=req.remarks,
        )
        db.add(feedback)

    await db.flush()
    logger.info("feedback_submitted", doc_id=req.document_id, key=req.question_key)
    return {"message": "Feedback recorded"}


@router.put("/results/update")
async def update_result(
    req: UpdateResultRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an individual answer value (inline editing)."""
    stmt = select(DocumentProcessing).where(
        DocumentProcessing.id == uuid.UUID(req.document_id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.results:
        raise HTTPException(status_code=400, detail="No results to update")

    # Find and update the specific answer
    # Results are in AnalysisResult[] format: [{category, question, pairs: [{answer, ...}]}]
    # question_key can be: "Q1" (positional), question text, or "category:question"
    updated = False
    for i, result in enumerate(doc.results):
        # Match by Q-index (Q1, Q2, ...), question text, or category:question
        q_index = f"Q{i + 1}"
        matches = (
            req.question_key == q_index
            or req.question_key == result.get("question", "")
            or req.question_key == f'{result.get("category", "")}:{result.get("question", "")}'
            or req.question_key == result.get("question_key", "")  # legacy
        )
        if matches and result.get("pairs"):
            old_answer = result["pairs"][0].get("answer", "")
            result["pairs"][0]["answer"] = req.new_value
            result["pairs"][0]["is_edited"] = True
            result["pairs"][0]["last_edited_changes"] = {
                "Extracted Answer": {"old": old_answer, "new": req.new_value}
            }
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"Question key not found: {req.question_key}")

    # Mark the JSONB column as modified
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(doc, "results")
    await db.flush()

    logger.info("result_updated", doc_id=req.document_id, key=req.question_key)
    return {"message": "Result updated"}
