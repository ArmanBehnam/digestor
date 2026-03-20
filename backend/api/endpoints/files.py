"""
File management endpoints - presigned URLs for S3 downloads.
Includes local file serving for development when S3 is unavailable.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import List

from api.dependencies import get_current_user
from services.s3_service import generate_presigned_url, download_from_s3, _should_use_local, _local_path

logger = structlog.get_logger()
router = APIRouter()


class PresignedUrlsRequest(BaseModel):
    paths: List[str]


@router.get("/files/presigned-url")
async def get_presigned_url(
    path: str = Query(..., description="S3 key for the file"),
    current_user: dict = Depends(get_current_user),
):
    """Generate a presigned download URL for a single file."""
    if not path:
        raise HTTPException(status_code=400, detail="path parameter required")

    try:
        signed_url = await generate_presigned_url(path)
        return {"signed_url": signed_url}
    except Exception as e:
        logger.error("presigned_url_error", path=path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate URL: {str(e)}")


@router.post("/files/presigned-urls")
async def get_presigned_urls(
    req: PresignedUrlsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate presigned download URLs for multiple files."""
    if not req.paths:
        return []

    results = []
    for path in req.paths:
        try:
            signed_url = await generate_presigned_url(path)
            results.append({"path": path, "signed_url": signed_url})
        except Exception as e:
            logger.error("presigned_url_error", path=path, error=str(e))
            results.append({"path": path, "signed_url": None, "error": str(e)})

    return results


@router.api_route("/local-files/{file_path:path}", methods=["GET", "HEAD"])
async def serve_local_file(file_path: str, request: Request):
    """Serve locally-stored files in development mode (replaces S3 presigned URLs).
    No auth required — mimics S3 presigned URL behavior where the URL itself is the credential.
    Only active when S3 is unavailable in development.
    Supports HEAD for PDF.js range-request probing.
    """
    if not _should_use_local():
        raise HTTPException(status_code=404, detail="Local file serving only available in development")

    local_file = _local_path(file_path)

    if not local_file.exists() or not local_file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    suffix = local_file.suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
    }
    media_type = content_types.get(suffix, "application/octet-stream")

    # HEAD request: return headers only (PDF.js probes this for range support)
    if request.method == "HEAD":
        return Response(
            headers={
                "Content-Type": media_type,
                "Content-Length": str(local_file.stat().st_size),
                "Accept-Ranges": "bytes",
            }
        )

    return FileResponse(
        path=str(local_file),
        media_type=media_type,
        content_disposition_type="inline",
    )
