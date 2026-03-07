"""
Intelligent processing router - decides between PDF.js fast path and AWS pipeline.
This is the main entry point for document processing.
"""

import uuid
import time
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import DocumentProcessing, AnalyticsEvent
from services.fallback_detector import FallbackDetector

logger = structlog.get_logger()
router = APIRouter()
fallback_detector = FallbackDetector()


def _calc_avg_confidence(results: list) -> float:
    """
    Calculate average confidence from AnalysisResult[] format.
    Results are [{category, question, pairs: [{answer, reference, confidence}]}]
    Confidence is on 0.0-1.0 scale.
    """
    confidences = []
    for r in results:
        pairs = r.get("pairs", [])
        for pair in pairs:
            conf = pair.get("confidence", 0)
            if conf and conf > 0:
                confidences.append(conf)
    return sum(confidences) / len(confidences) if confidences else 0


class ProcessRequest(BaseModel):
    document_id: str
    extracted_text: Optional[str] = None  # From PDF.js browser extraction
    text_positions: Optional[list] = None  # Coordinate data from PDF.js
    processing_mode: str = "auto"  # auto, quick, deep
    page_count: Optional[int] = None


@router.post("/process-document")
async def process_document(
    req: ProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Intelligent processing router.

    Modes:
    - auto (default): Try PDF.js first, auto-fallback to AWS if low quality
    - quick: PDF.js only, no fallback
    - deep: AWS pipeline only, skip PDF.js
    """
    start_time = time.time()

    # Fetch document record
    stmt = select(DocumentProcessing).where(
        DocumentProcessing.id == uuid.UUID(req.document_id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update page count if provided
    if req.page_count:
        doc.page_count = req.page_count

    doc.processing_mode = req.processing_mode
    doc.status = "queued"
    # Save extracted text for future combined multi-PDF processing
    if req.extracted_text:
        doc.extracted_text = req.extracted_text
    await db.flush()

    # --- DEEP MODE: Skip PDF.js, go directly to AWS ---
    if req.processing_mode == "deep":
        logger.info("process_deep_mode", doc_id=str(doc.id))
        from api.endpoints.process_aws import enqueue_aws_processing
        job_id = await enqueue_aws_processing(doc, db)
        doc.processing_path = "aws"
        doc.job_id = job_id
        await db.flush()
        return {
            "document_id": str(doc.id),
            "processing_path": "aws",
            "job_id": job_id,
            "message": "Deep analysis queued",
        }

    # --- QUICK or AUTO MODE: Try PDF.js first ---
    if not req.extracted_text:
        # No extracted text from frontend — must use AWS
        logger.info("no_pdfjs_text_fallback_aws", doc_id=str(doc.id))
        from api.endpoints.process_aws import enqueue_aws_processing
        job_id = await enqueue_aws_processing(doc, db)
        doc.processing_path = "aws"
        doc.fallback_reason = "No PDF.js text extracted (scanned/image PDF)"
        doc.job_id = job_id
        await db.flush()
        return {
            "document_id": str(doc.id),
            "processing_path": "aws",
            "job_id": job_id,
            "message": "No text extracted by PDF.js, using deep analysis",
        }

    # --- PDF.js Processing ---
    logger.info("process_pdfjs_path", doc_id=str(doc.id))
    doc.status = "llm_processing"
    doc.processing_path = "pdfjs"
    await db.flush()

    from api.endpoints.process_pdfjs import run_pdfjs_processing
    pdfjs_results, text_quality = await run_pdfjs_processing(
        extracted_text=req.extracted_text,
        text_positions=req.text_positions,
        doc_id=str(doc.id),
    )

    # --- Evaluate Quality (Auto mode only) ---
    if req.processing_mode == "auto":
        should_fallback, reason = fallback_detector.should_fallback_to_aws(
            pdfjs_results, text_quality
        )

        if should_fallback:
            logger.info(
                "pdfjs_fallback_to_aws",
                doc_id=str(doc.id),
                reason=reason,
            )
            # Save PDF.js results as fallback (in case AWS fails)
            # but set status to "queued" so the frontend continues polling
            # until the AWS OCR worker finishes with better results
            processing_time = int((time.time() - start_time) * 1000)
            avg_confidence = _calc_avg_confidence(pdfjs_results)

            doc.results = pdfjs_results
            doc.confidence_avg = avg_confidence
            doc.processing_time_ms = processing_time
            doc.processing_path = "aws"
            doc.fallback_reason = reason
            doc.status = "queued"
            await db.flush()

            # Enqueue AWS OCR processing — worker will update status to "complete"
            try:
                from api.endpoints.process_aws import enqueue_aws_processing
                job_id = await enqueue_aws_processing(doc, db)
                doc.job_id = job_id
                await db.flush()
            except Exception as e:
                logger.warning("aws_enqueue_failed", doc_id=str(doc.id), error=str(e))
                # AWS enqueue failed — revert to "complete" with PDF.js results
                # so the user still sees something rather than being stuck
                doc.status = "complete"
                doc.processing_path = "pdfjs"
                await db.flush()
                job_id = None

            logger.info(
                "pdfjs_results_saved_with_fallback",
                doc_id=str(doc.id),
                answers_found=len(pdfjs_results),
                confidence=f"{avg_confidence:.2%}",
            )

            return {
                "document_id": str(doc.id),
                "processing_path": "aws",
                "job_id": job_id,
                "fallback_reason": reason,
                "message": f"PDF.js quality insufficient ({reason}), deep analysis queued",
            }

    # --- PDF.js results are good enough ---
    processing_time = int((time.time() - start_time) * 1000)
    avg_confidence = _calc_avg_confidence(pdfjs_results)

    doc.results = pdfjs_results
    doc.confidence_avg = avg_confidence
    doc.processing_time_ms = processing_time
    doc.status = "complete"
    await db.flush()

    # Log analytics
    analytics = AnalyticsEvent(
        user_id=None,  # Will be set from current_user
        event_type="process_complete",
        processing_path="pdfjs",
        processing_time_ms=processing_time,
        confidence_score=avg_confidence,
        document_id=doc.id,
        project_id=doc.project_id,
    )
    db.add(analytics)
    await db.flush()

    logger.info(
        "pdfjs_processing_complete",
        doc_id=str(doc.id),
        time_ms=processing_time,
        confidence=f"{avg_confidence:.2%}",
    )

    return {
        "document_id": str(doc.id),
        "processing_path": "pdfjs",
        "results": pdfjs_results,
        "confidence_avg": avg_confidence,
        "processing_time_ms": processing_time,
        "message": "Processing complete",
    }
