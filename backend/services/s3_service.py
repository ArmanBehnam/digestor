"""
AWS S3 service for file uploads, downloads, and presigned URLs.
"""

import os
import structlog
import boto3
from botocore.exceptions import ClientError

logger = structlog.get_logger()

S3_BUCKET = os.getenv("S3_BUCKET", "digestor-unified-storage")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


async def upload_file_to_s3(
    content: bytes,
    s3_key: str,
    content_type: str = None,
    bucket: str = None,
) -> str:
    """Upload file content to S3."""
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
    """Download file content from S3."""
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
    """Generate a presigned download URL."""
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
    """List objects in S3 with a given prefix."""
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
    """Delete an object from S3."""
    bucket = bucket or S3_BUCKET
    s3 = _get_s3()

    try:
        s3.delete_object(Bucket=bucket, Key=s3_key)
        logger.info("s3_delete_success", key=s3_key)
    except ClientError as e:
        logger.error("s3_delete_failed", key=s3_key, error=str(e))
        raise
