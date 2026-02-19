"""
AWS pipeline processing path.
Enqueues heavy OCR+LLM jobs to Redis Queue for ECS Fargate workers.
"""

import os
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from redis import Redis
from rq import Queue

from api.dependencies import get_db, get_current_user
from db.models import DocumentProcessing

logger = structlog.get_logger()
router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
S3_BUCKET = os.getenv("S3_BUCKET", "digestor-unified-storage")


def _get_rq_queue() -> Queue:
    """Get Redis Queue connection."""
    redis_conn = Redis.from_url(REDIS_URL)
    return Queue("default", connection=redis_conn)


class AWSProcessRequest(BaseModel):
    document_id: str


@router.post("/process-aws")
async def process_aws_endpoint(
    req: AWSProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicitly trigger AWS pipeline processing for a document."""
    from sqlalchemy import select

    stmt = select(DocumentProcessing).where(
        DocumentProcessing.id == uuid.UUID(req.document_id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    job_id = await enqueue_aws_processing(doc, db)

    return {
        "document_id": str(doc.id),
        "job_id": job_id,
        "processing_path": "aws",
        "message": "Deep analysis queued",
    }


async def enqueue_aws_processing(
    doc: DocumentProcessing,
    db: AsyncSession,
) -> str:
    """
    Enqueue a document for AWS pipeline processing (Textract + LLM + Validation).
    Returns the RQ job ID.
    """
    queue = _get_rq_queue()

    # Enqueue the job — tasks.process_pdfs is the existing worker function
    job = queue.enqueue(
        "tasks.process_pdfs",
        kwargs={
            "file_keys": [doc.s3_key],
            "bucket": S3_BUCKET,
            "project_id": str(doc.project_id),
            "document_id": str(doc.id),
        },
        job_timeout=900,  # 15 minutes max
        result_ttl=86400,  # Keep result for 24 hours
    )

    doc.job_id = job.id
    # Only change status to "queued" if not already complete with results
    # (when called from fallback path, results are already saved)
    if doc.status != "complete":
        doc.status = "queued"
        doc.processing_path = "aws"
    await db.flush()

    logger.info(
        "aws_job_enqueued",
        doc_id=str(doc.id),
        job_id=job.id,
        s3_key=doc.s3_key,
    )

    return job.id
