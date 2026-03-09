"""
Project-level combined processing endpoint.
Combines extracted text from all documents in a project,
runs the LLM once on the combined text, and evaluates quality holistically.

This avoids per-document FallbackDetector failures when complementary PDFs
together have enough information (e.g., PDF #1 has wind loads, PDF #2 has seismic).
"""

import os
import re
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


async def _enrich_tier1_with_bboxes(results: list, docs: list) -> list:
    """Run Textract OCR on only the pages where answers were found to get bounding boxes.

    This is used for Tier 1 (PDF.js) results which lack coordinate data.
    We run a lightweight OCR pass on just the answer pages, then use
    CoordinateMapper to match answer text to real OCR bounding boxes.
    """
    import boto3
    import fitz
    from llm.coordinate_mapper import CoordinateMapper

    # 1. Collect unique answer pages per document
    answer_pages = set()
    for r in results:
        for pair in r.get("pairs", []):
            ref = pair.get("reference", "")
            m = re.search(r'Page\s+(\d+)', ref, re.IGNORECASE)
            if m:
                answer_pages.add(int(m.group(1)))

    if not answer_pages:
        return results

    logger.info("tier1_bbox_enrichment_start", answer_pages=sorted(answer_pages))

    # 2. Download PDF and extract answer page images, run Textract
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
    )
    textract = boto3.client(
        'textract',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
    )
    bucket = os.getenv('S3_BUCKET', os.getenv('AWS_S3_BUCKET', ''))

    # Build page-level OCR results for coordinate mapping
    page_results = []

    for doc in docs:
        if not doc.s3_key:
            continue
        try:
            # Download PDF from S3
            response = s3.get_object(Bucket=bucket, Key=doc.s3_key)
            pdf_bytes = response['Body'].read()
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_num in sorted(answer_pages):
                if page_num < 1 or page_num > len(pdf_doc):
                    continue

                # Render page to image
                page = pdf_doc[page_num - 1]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")

                if len(img_bytes) > 10 * 1024 * 1024:
                    continue  # Skip oversized pages

                # Call Textract
                try:
                    textract_response = textract.detect_document_text(
                        Document={'Bytes': img_bytes}
                    )
                except Exception as te:
                    logger.warning("textract_page_failed", page=page_num, error=str(te))
                    continue

                # Extract text elements with bboxes
                text_elements = []
                full_text_parts = []
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'WORD':
                        bbox_data = block['Geometry']['BoundingBox']
                        text_elements.append({
                            "text": block['Text'],
                            "confidence": block['Confidence'] / 100.0,
                            "bbox": {
                                "x": int(bbox_data['Left'] * pix.width),
                                "y": int(bbox_data['Top'] * pix.height),
                                "width": int(bbox_data['Width'] * pix.width),
                                "height": int(bbox_data['Height'] * pix.height),
                            },
                        })
                    elif block['BlockType'] == 'LINE':
                        full_text_parts.append(block.get('Text', ''))

                page_results.append({
                    "page_number": page_num,
                    "extracted_text": "\n".join(full_text_parts),
                    "text_elements": text_elements,
                    "page_width": pix.width,
                    "page_height": pix.height,
                })

            pdf_doc.close()
        except Exception as e:
            logger.warning("tier1_pdf_ocr_failed", s3_key=doc.s3_key, error=str(e))
            continue

    if not page_results:
        return results

    # 3. Use CoordinateMapper to match answers to bboxes
    mapper = CoordinateMapper()
    enriched_count = 0

    for r in results:
        for pair in r.get("pairs", []):
            answer = pair.get("answer", "")
            ref = pair.get("reference", "")
            m = re.search(r'Page\s+(\d+)', ref, re.IGNORECASE)
            page_num = int(m.group(1)) if m else None

            coord = mapper.find_answer_coordinates(answer, page_results, page_num)
            if coord:
                bbox = coord["bounding_box"]
                pg = next((p for p in page_results
                           if p.get("page_number") == page_num), None)
                pw = pg.get("page_width", 1000) if pg else 1000
                ph = pg.get("page_height", 1000) if pg else 1000
                pair["bbox"] = {
                    "x": round(bbox["x"] / pw, 4),
                    "y": round(bbox["y"] / ph, 4),
                    "width": round(bbox["width"] / pw, 4),
                    "height": round(bbox["height"] / ph, 4),
                }
                enriched_count += 1

    logger.info("tier1_bbox_enrichment_complete", enriched=enriched_count)
    return results


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
    all_docs = list((await db.execute(all_docs_stmt)).scalars().all())

    if not all_docs:
        raise HTTPException(
            status_code=400,
            detail="No documents found for this project",
        )

    # Deduplicate: keep only the LATEST document per filename
    seen_filenames = {}  # filename -> latest doc
    duplicates = []
    for doc in all_docs:
        if doc.file_name in seen_filenames:
            duplicates.append(seen_filenames[doc.file_name])  # old one is the duplicate
        seen_filenames[doc.file_name] = doc

    if duplicates:
        logger.info("deduplicating_documents",
                     project_id=req.project_id,
                     total=len(all_docs),
                     duplicates=len(duplicates),
                     keeping=len(seen_filenames))
        for dup in duplicates:
            await db.delete(dup)
        await db.flush()
        # Re-fetch clean list
        all_docs = list(seen_filenames.values())

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

    # Clear stale project snapshot from previous runs so self-healing
    # doesn't accidentally use old results for new documents
    project.pending_snapshot_json = None
    flag_modified(project, "pending_snapshot_json")

    # Save extracted_text to each DocumentProcessing record (for future re-processing)
    for doc in all_docs:
        doc_id_str = str(doc.id)
        if doc_id_str in doc_texts and not doc.extracted_text:
            doc.extracted_text = doc_texts[doc_id_str]
        doc.status = "llm_processing"
        doc.processing_path = "pdfjs"
    await db.flush()

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

    # --- DEEP MODE: Skip PDF.js, enqueue ALL docs as single combined job ---
    if req.processing_mode == "deep":
        from api.endpoints.process_aws import enqueue_aws_processing_combined

        all_s3_keys = [doc.s3_key for doc in all_docs if doc.s3_key]
        primary_doc = all_docs[0]
        job_id = await enqueue_aws_processing_combined(
            all_s3_keys, primary_doc, all_docs, project, db
        )

        return {
            "project_id": req.project_id,
            "processing_path": "aws",
            "job_ids": [job_id],
            "message": f"Deep analysis queued for {len(all_s3_keys)} documents (combined)",
        }

    # --- PDF.js Combined Processing ---
    from api.endpoints.process_pdfjs import run_pdfjs_processing

    pdfjs_results, text_quality = await run_pdfjs_processing(
        extracted_text=combined_text,
        text_positions=None,
        doc_id=f"project:{req.project_id}",
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

    # Save results based on whether fallback is needed
    if not should_fallback:
        # Tier 1 won — enrich with bounding boxes before saving
        try:
            pdfjs_results = await _enrich_tier1_with_bboxes(pdfjs_results, all_docs)
        except Exception as e:
            logger.warning("tier1_bbox_enrichment_failed", error=str(e))
            # Non-fatal — results still valid without bboxes

        # Save results for user
        project.pending_snapshot_json = pdfjs_results
        flag_modified(project, "pending_snapshot_json")
        for doc in all_docs:
            doc.results = pdfjs_results
            doc.confidence_avg = avg_confidence
            doc.processing_time_ms = processing_time
            doc.processing_path = "pdfjs"
            doc.processing_tier = 1
            doc.status = "complete"
            flag_modified(doc, "results")
    else:
        # Fallback needed — do NOT save results to user-visible fields.
        # User stays in "Processing..." state until OCR/VLM tier completes.
        for doc in all_docs:
            doc.confidence_avg = avg_confidence
            doc.processing_time_ms = processing_time
            doc.processing_path = "aws"
            doc.status = "queued"
            doc.fallback_reason = fallback_reason

    await db.flush()

    # Handle fallback — enqueue ALL docs as a SINGLE combined worker job
    # (not one job per doc, since answers span across documents)
    if should_fallback:
        logger.info(
            "project_combined_fallback_to_aws",
            project_id=req.project_id,
            reason=fallback_reason,
            num_docs=len(all_docs),
        )
        try:
            from api.endpoints.process_aws import enqueue_aws_processing_combined

            # Collect all S3 keys and enqueue ONE job with all files
            all_s3_keys = [doc.s3_key for doc in all_docs if doc.s3_key]
            if all_s3_keys:
                # Use the first document's ID as the "primary" doc for status tracking
                primary_doc = all_docs[0]
                job_id = await enqueue_aws_processing_combined(
                    all_s3_keys, primary_doc, all_docs, project, db
                )
                logger.info(
                    "aws_combined_job_enqueued",
                    project_id=req.project_id,
                    job_id=job_id,
                    num_files=len(all_s3_keys),
                )
            else:
                raise Exception("No S3 keys found for any documents")
        except Exception as e:
            logger.warning(
                "aws_enqueue_failed",
                project_id=req.project_id,
                error=str(e),
            )
            # AWS enqueue failed — show Tier 1 results as best effort
            # so the user isn't stuck in "Processing..." forever
            project.pending_snapshot_json = pdfjs_results
            flag_modified(project, "pending_snapshot_json")
            for doc in all_docs:
                doc.results = pdfjs_results
                doc.status = "complete"
                doc.processing_path = "pdfjs"
                doc.processing_tier = 1
                flag_modified(doc, "results")
            await db.flush()

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
