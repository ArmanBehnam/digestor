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
S3_BUCKET = os.getenv("S3_BUCKET", "digestor-unified-uploads-dev")


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
    Enqueue a single document for AWS pipeline processing.
    Returns the RQ job ID.
    """
    queue = _get_rq_queue()

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


async def enqueue_aws_processing_combined(
    all_s3_keys: list,
    primary_doc: DocumentProcessing,
    all_docs: list,
    project,
    db: AsyncSession,
) -> str:
    """
    Enqueue ALL project documents as a SINGLE combined worker job.
    This ensures the worker processes all PDFs together, merging OCR results
    and answering questions from the combined content (same as Tier 1 approach).

    Returns the RQ job ID.
    """
    queue = _get_rq_queue()

    # Enqueue one job with ALL file keys
    job = queue.enqueue(
        "tasks.process_pdfs",
        kwargs={
            "file_keys": all_s3_keys,
            "bucket": S3_BUCKET,
            "project_id": str(primary_doc.project_id),
            "document_id": str(primary_doc.id),
        },
        job_timeout=1800,  # 30 minutes max for multi-document processing
        result_ttl=86400,
    )

    # Mark all documents as queued with the same job ID
    for doc in all_docs:
        doc.job_id = job.id
        doc.status = "queued"
        doc.processing_path = "aws"
    await db.flush()

    logger.info(
        "aws_combined_job_enqueued",
        project_id=str(primary_doc.project_id),
        job_id=job.id,
        num_files=len(all_s3_keys),
        s3_keys=all_s3_keys,
    )

    return job.id
