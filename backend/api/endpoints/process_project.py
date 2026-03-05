"""
Project-level combined processing endpoint.
Combines extracted text from all documents in a project,
runs the LLM once on the combined text, and evaluates quality holistically.

This avoids per-document FallbackDetector failures when complementary PDFs
together have enough information (e.g., PDF #1 has wind loads, PDF #2 has seismic).
"""

import uuid
import time
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from api.dependencies import get_db, get_current_user
from db.models import DocumentProcessing, Project, AnalyticsEvent, User
from services.fallback_detector import FallbackDetector

logger = structlog.get_logger()
router = APIRouter()
fallback_detector = FallbackDetector()


class DocumentText(BaseModel):
    document_id: str
    extracted_text: str


class ProcessProjectRequest(BaseModel):
    project_id: str
    documents: List[DocumentText]
    processing_mode: str = "auto"  # auto, quick, deep


def _calc_avg_confidence(results: list) -> float:
    """Calculate average confidence from AnalysisResult[] format."""
    confidences = []
    for r in results:
        pairs = r.get("pairs", [])
        for pair in pairs:
            conf = pair.get("confidence", 0)
            if conf and conf > 0:
                confidences.append(conf)
    return sum(confidences) / len(confidences) if confidences else 0


@router.post("/process-project")
async def process_project(
    req: ProcessProjectRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Combined multi-document processing for a project.

    1. Fetches all DocumentProcessing records for the project
    2. Combines extracted text from request + any stored text from existing docs
    3. Runs LLM ONCE on combined text
    4. Runs FallbackDetector on combined results (fewer missing → less fallback)
    5. Saves combined results to Project.pending_snapshot_json
    6. Saves combined results to each DocumentProcessing.results
    """
    start_time = time.time()

    # Validate project exists
    project_stmt = select(Project).where(
        Project.id == uuid.UUID(req.project_id)
    )
    project = (await db.execute(project_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build text map from request documents
    doc_texts = {}  # document_id (str) -> extracted_text
    for doc_input in req.documents:
        doc_texts[doc_input.document_id] = doc_input.extracted_text

    # Fetch ALL documents in this project (handles "add second PDF later" scenario)
    all_docs_stmt = (
        select(DocumentProcessing)
        .where(DocumentProcessing.project_id == uuid.UUID(req.project_id))
        .order_by(DocumentProcessing.created_at.asc())
    )
    all_docs = (await db.execute(all_docs_stmt)).scalars().all()

    if not all_docs:
        raise HTTPException(
            status_code=400,
            detail="No documents found for this project",
        )

    # For existing docs not in the request, use stored extracted_text from DB
    for doc in all_docs:
        doc_id_str = str(doc.id)
        if doc_id_str not in doc_texts and doc.extracted_text:
            doc_texts[doc_id_str] = doc.extracted_text

    if not doc_texts:
        raise HTTPException(
            status_code=400,
            detail="No extracted text available for any documents. Upload and extract text first.",
        )

    # Save extracted_text to each DocumentProcessing record (for future re-processing)
    for doc in all_docs:
        doc_id_str = str(doc.id)
        if doc_id_str in doc_texts and not doc.extracted_text:
            doc.extracted_text = doc_texts[doc_id_str]
        doc.status = "llm_processing"
        doc.processing_path = "pdfjs"
    # COMMIT now so the 'llm_processing' status is persisted even if the HTTP
    # connection is dropped (ALB timeout). Without this, a disconnect causes
    # session.rollback() → statuses revert → frontend sees stale 'error' status.
    await db.commit()

    # Combine all text with file separators
    combined_parts = []
    for doc in all_docs:
        doc_id_str = str(doc.id)
        text = doc_texts.get(doc_id_str)
        if text:
            combined_parts.append(
                f"\n\n{'=' * 60}\n"
                f"=== FILE: {doc.file_name} ===\n"
                f"{'=' * 60}\n\n"
                f"{text}"
            )

    combined_text = "\n".join(combined_parts)

    logger.info(
        "project_combined_processing_start",
        project_id=req.project_id,
        num_documents=len(doc_texts),
        combined_text_len=len(combined_text),
    )

    # --- DEEP MODE: Skip PDF.js, enqueue AWS for each document ---
    if req.processing_mode == "deep":
        from api.endpoints.process_aws import enqueue_aws_processing

        job_ids = []
        for doc in all_docs:
            job_id = await enqueue_aws_processing(doc, db)
            doc.processing_path = "aws"
            doc.status = "queued"
            job_ids.append(job_id)
        await db.flush()

        return {
            "project_id": req.project_id,
            "processing_path": "aws",
            "job_ids": job_ids,
            "message": "Deep analysis queued for all documents",
        }

    # --- PDF.js Combined Processing ---
    from api.endpoints.process_pdfjs import run_pdfjs_processing

    try:
        pdfjs_results, text_quality = await run_pdfjs_processing(
            extracted_text=combined_text,
            text_positions=None,
            doc_id=f"project:{req.project_id}",
        )
    except Exception as llm_err:
        # LLM processing failed — mark all docs as 'error' so frontend
        # gets a clear signal instead of polling forever.
        logger.error(
            "project_llm_processing_failed",
            project_id=req.project_id,
            error=str(llm_err),
        )
        for doc in all_docs:
            doc.status = "error"
            doc.fallback_reason = f"LLM processing error: {str(llm_err)[:200]}"
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"LLM processing failed: {str(llm_err)[:200]}",
        )

    # --- Evaluate Quality on COMBINED results (Auto mode only) ---
    should_fallback = False
    fallback_reason = ""
    if req.processing_mode == "auto":
        should_fallback, fallback_reason = fallback_detector.should_fallback_to_aws(
            pdfjs_results, text_quality
        )

    processing_time = int((time.time() - start_time) * 1000)
    avg_confidence = _calc_avg_confidence(pdfjs_results)

    # Save combined results to Project.pending_snapshot_json
    project.pending_snapshot_json = pdfjs_results
    flag_modified(project, "pending_snapshot_json")

    # Save combined results to each DocumentProcessing record
    for doc in all_docs:
        doc.results = pdfjs_results
        doc.confidence_avg = avg_confidence
        doc.processing_time_ms = processing_time
        doc.processing_path = "pdfjs"
        doc.status = "complete"
        if should_fallback:
            doc.fallback_reason = fallback_reason
        flag_modified(doc, "results")

    # COMMIT results immediately so 'complete' status is persisted.
    # This prevents ALB timeouts or worker fallback jobs from reverting the status.
    await db.commit()

    # Handle fallback — enqueue AWS in background (only if really needed)
    if should_fallback:
        logger.info(
            "project_combined_fallback_to_aws",
            project_id=req.project_id,
            reason=fallback_reason,
        )
        try:
            from api.endpoints.process_aws import enqueue_aws_processing

            for doc in all_docs:
                await enqueue_aws_processing(doc, db)
        except Exception as e:
            logger.warning(
                "aws_enqueue_failed",
                project_id=req.project_id,
                error=str(e),
            )

    # Log analytics
    try:
        user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
        db_user = (await db.execute(user_stmt)).scalar_one_or_none()

        analytics = AnalyticsEvent(
            user_id=db_user.id if db_user else None,
            event_type="process_project_complete",
            processing_path="pdfjs_combined",
            processing_time_ms=processing_time,
            confidence_score=avg_confidence,
            project_id=project.id,
        )
        db.add(analytics)
        await db.flush()
    except Exception as e:
        logger.warning("analytics_write_failed", error=str(e))

    logger.info(
        "project_combined_processing_complete",
        project_id=req.project_id,
        num_documents=len(doc_texts),
        time_ms=processing_time,
        confidence=f"{avg_confidence:.2%}",
        fallback=should_fallback,
    )

    return {
        "project_id": req.project_id,
        "processing_path": "pdfjs_combined",
        "results": pdfjs_results,
        "confidence_avg": avg_confidence,
        "processing_time_ms": processing_time,
        "fallback_reason": fallback_reason if should_fallback else None,
        "num_documents_combined": len(doc_texts),
        "message": (
            f"Combined processing complete ({len(doc_texts)} documents)"
            + (f" (note: {fallback_reason})" if should_fallback else "")
        ),
    }
