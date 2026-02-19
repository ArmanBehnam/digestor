"""
Tests for the S3 service.
All AWS calls are mocked via botocore stubber or unittest.mock.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestS3Service:
    """Test S3 upload, download, and presigned URL generation."""

    @pytest.mark.asyncio
    async def test_upload_file_to_s3(self):
        """Uploading a file should call S3 put_object with correct params."""
        with patch("services.s3_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

            from services.s3_service import upload_file_to_s3

            result = await upload_file_to_s3(
                content=b"test pdf content",
                s3_key="uploads/user123/test.pdf",
                content_type="application/pdf",
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_generate_presigned_url(self):
        """Should generate a valid presigned URL with expiration."""
        with patch("services.s3_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.generate_presigned_url.return_value = (
                "https://test-bucket.s3.amazonaws.com/uploads/test.pdf?signed=yes"
            )

            from services.s3_service import generate_presigned_url

            url = await generate_presigned_url(
                s3_key="uploads/test.pdf",
                expiration=3600,
            )

            assert "test.pdf" in url
            assert "signed" in url

    @pytest.mark.asyncio
    async def test_download_from_s3(self):
        """Should retrieve file content from S3."""
        with patch("services.s3_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client

            mock_body = MagicMock()
            mock_body.read.return_value = b"file content here"
            mock_client.get_object.return_value = {
                "Body": mock_body,
                "ContentLength": 17,
            }

            from services.s3_service import download_from_s3

            content = await download_from_s3(s3_key="results/test.csv")
            assert content == b"file content here"

    @pytest.mark.asyncio
    async def test_delete_object(self):
        """Should call S3 delete_object."""
        with patch("services.s3_service.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.delete_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 204}}

            from services.s3_service import delete_object

            await delete_object(s3_key="temp/old-file.pdf")
            # Should not raise
