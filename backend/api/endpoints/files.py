"""
File management endpoints - presigned URLs for S3 downloads.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List

from api.dependencies import get_current_user
from services.s3_service import generate_presigned_url

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
