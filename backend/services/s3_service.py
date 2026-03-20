"""
AWS S3 service for file uploads, downloads, and presigned URLs.
Falls back to local filesystem storage when S3 is unavailable (development).
"""

import os
import pathlib
import structlog
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError

logger = structlog.get_logger()

S3_BUCKET = os.getenv("S3_BUCKET", "digestor-unified-uploads-dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOCAL_UPLOAD_DIR = pathlib.Path(os.getenv("LOCAL_UPLOAD_DIR", "/app/local_uploads"))

_s3_client = None
_use_local = None  # tri-state: None=not checked, True=local, False=s3


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


def _should_use_local() -> bool:
    """Check if we should use local storage (cached after first check)."""
    global _use_local
    if _use_local is not None:
        return _use_local

    # Only fall back to local in development
    if ENVIRONMENT not in ("development", "dev", "local"):
        _use_local = False
        return False

    # Test S3 connectivity
    try:
        s3 = _get_s3()
        s3.head_bucket(Bucket=S3_BUCKET)
        _use_local = False
        logger.info("s3_available", bucket=S3_BUCKET)
    except Exception:
        _use_local = True
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.warning("s3_unavailable_using_local", path=str(LOCAL_UPLOAD_DIR))

    return _use_local


def _local_path(s3_key: str) -> pathlib.Path:
    """Get local filesystem path for an S3 key."""
    return LOCAL_UPLOAD_DIR / s3_key


async def upload_file_to_s3(
    content: bytes,
    s3_key: str,
    content_type: str = None,
    bucket: str = None,
) -> str:
    """Upload file content to S3, or local filesystem in development."""
    if _should_use_local():
        path = _local_path(s3_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.info("local_upload_success", key=s3_key, size=len(content), path=str(path))
        return s3_key

    bucket = bucket or S3_BUCKET
    content_type = content_type or "application/octet-stream"
    s3 = _get_s3()

    try:
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        logger.info("s3_upload_success", key=s3_key, size=len(content))
        return s3_key
    except ClientError as e:
        logger.error("s3_upload_failed", key=s3_key, error=str(e))
        raise


async def download_from_s3(s3_key: str, bucket: str = None) -> bytes:
    """Download file content from S3, or local filesystem in development."""
    if _should_use_local():
        path = _local_path(s3_key)
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {s3_key}")
        content = path.read_bytes()
        logger.info("local_download_success", key=s3_key, size=len(content))
        return content

    bucket = bucket or S3_BUCKET
    s3 = _get_s3()

    try:
        response = s3.get_object(Bucket=bucket, Key=s3_key)
        content = response["Body"].read()
        logger.info("s3_download_success", key=s3_key, size=len(content))
        return content
    except ClientError as e:
        logger.error("s3_download_failed", key=s3_key, error=str(e))
        raise


async def generate_presigned_url(
    s3_key: str,
    bucket: str = None,
    expiration: int = 3600,
) -> str:
    """Generate a presigned download URL, or local file URL in development."""
    if _should_use_local():
        # Return a local API path that the frontend can use
        return f"/api/local-files/{s3_key}"

    bucket = bucket or S3_BUCKET
    s3 = _get_s3()

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expiration,
        )
        return url
    except ClientError as e:
        logger.error("presigned_url_failed", key=s3_key, error=str(e))
        raise


async def list_objects(prefix: str, bucket: str = None) -> list:
    """List objects in S3, or local filesystem in development."""
    if _should_use_local():
        local_dir = LOCAL_UPLOAD_DIR / prefix
        if not local_dir.exists():
            return []
        results = []
        for p in local_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(LOCAL_UPLOAD_DIR)).replace("\\", "/")
                stat = p.stat()
                results.append({
                    "key": rel,
                    "size": stat.st_size,
                    "last_modified": str(stat.st_mtime),
                })
        return results

    bucket = bucket or S3_BUCKET
    s3 = _get_s3()

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }
            for obj in response.get("Contents", [])
        ]
    except ClientError as e:
        logger.error("s3_list_failed", prefix=prefix, error=str(e))
        raise


async def delete_object(s3_key: str, bucket: str = None):
    """Delete an object from S3, or local filesystem in development."""
    if _should_use_local():
        path = _local_path(s3_key)
        if path.exists():
            path.unlink()
            logger.info("local_delete_success", key=s3_key)
        return

    bucket = bucket or S3_BUCKET
    s3 = _get_s3()

    try:
        s3.delete_object(Bucket=bucket, Key=s3_key)
        logger.info("s3_delete_success", key=s3_key)
    except ClientError as e:
        logger.error("s3_delete_failed", key=s3_key, error=str(e))
        raise
