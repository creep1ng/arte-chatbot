"""S3 client module for downloading technical datasheets from AWS S3.

This module provides a client to interact with AWS S3 for downloading
PDF files containing technical product datasheets.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from backend.app.config import settings

logger = logging.getLogger(__name__)


class S3DownloadError(Exception):
    """Raised when S3 download operations fail."""

    pass


class S3UploadError(Exception):
    """Raised when S3 upload operations fail."""

    pass


class S3Client:
    """Client for interacting with AWS S3 to download PDF files."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
    ) -> None:
        """Initialize the S3 client.

        Args:
            bucket_name: Name of the S3 bucket. Defaults to AWS_BUCKET_NAME env var.
                         If provided explicitly, takes precedence over env/settings.
            aws_access_key_id: AWS access key ID. Defaults to AWS_ACCESS_KEY_ID env var.
                               If provided explicitly, takes precedence over env/settings.
            aws_secret_access_key: AWS secret access key. Defaults to AWS_SECRET_ACCESS_KEY env var.
                                   If provided explicitly, takes precedence over env/settings.
            aws_region: AWS region. Defaults to AWS_REGION env var.
                        If provided explicitly, takes precedence over env/settings.
        """
        # Use explicit parameters if provided, otherwise fallback to env/settings
        self.bucket_name = (
            bucket_name
            if bucket_name is not None
            else (os.getenv("AWS_BUCKET_NAME") or settings.aws_bucket_name)
        )
        self.aws_access_key_id = (
            aws_access_key_id
            if aws_access_key_id is not None
            else (os.getenv("AWS_ACCESS_KEY_ID") or settings.aws_access_key_id)
        )
        self.aws_secret_access_key = (
            aws_secret_access_key
            if aws_secret_access_key is not None
            else (os.getenv("AWS_SECRET_ACCESS_KEY") or settings.aws_secret_access_key)
        )
        self.aws_region = (
            aws_region
            if aws_region is not None
            else (os.getenv("AWS_REGION") or settings.aws_region)
        )

        if not self.bucket_name:
            logger.warning("AWS_BUCKET_NAME not configured")

        self._client = None

    @property
    def client(self):
        """Lazy initialization of the boto3 S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
        return self._client

    def download_pdf(self, s3_key: str) -> bytes:
        """Download a PDF file from S3 and return raw bytes.

        Args:
            s3_key: The S3 key (path) to the PDF file.
                    Example: "paneles/jinko-tiger-pro-460w.pdf"

        Returns:
            Raw bytes of the PDF file.

        Raises:
            S3DownloadError: If the download fails.
        """
        if not self.bucket_name:
            raise S3DownloadError("S3 bucket name not configured")

        try:
            logger.debug(
                "S3 download initiated: bucket=%s, key=%s",
                self.bucket_name,
                s3_key,
            )
            logger.info("Downloading S3 object: %s/%s", self.bucket_name, s3_key)
            response = self.client.get_object(Bucket=self.bucket_name, Key=s3_key)
            pdf_bytes = response["Body"].read()
            logger.debug(
                "S3 download complete: key=%s, size_bytes=%d",
                s3_key,
                len(pdf_bytes),
            )
            logger.info("Downloaded %d bytes from %s", len(pdf_bytes), s3_key)
            return pdf_bytes
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("S3 client error (%s): %s", error_code, e)
            if error_code == "NoSuchKey":
                raise S3DownloadError(f"File not found in S3: {s3_key}") from e
            raise S3DownloadError(f"S3 download failed: {e}") from e
        except NoCredentialsError:
            logger.error("AWS credentials not available")
            raise S3DownloadError("AWS credentials not configured") from None
        except Exception as e:
            logger.exception("Unexpected error downloading from S3: %s", e)
            raise S3DownloadError(f"Unexpected S3 error: {e}") from e

    def file_exists(self, s3_key: str) -> bool:
        """Check if a file exists in S3.

        Args:
            s3_key: The S3 key (path) to check.

        Returns:
            True if the file exists, False otherwise.
        """
        if not self.bucket_name:
            return False

        try:
            self.client.head_object(Bucket=self.bucket_name, Key=s3_key)
            logger.debug("S3 file exists: bucket=%s, key=%s", self.bucket_name, s3_key)
            return True
        except ClientError:
            logger.debug(
                "S3 file not found: bucket=%s, key=%s", self.bucket_name, s3_key
            )
            return False

    def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/json",
    ) -> None:
        """Upload data to S3.

        Args:
            key: The S3 key (path) for the object.
            data: Raw bytes to upload.
            content_type: MIME type of the object. Defaults to application/json.

        Raises:
            S3UploadError: If the upload fails.
        """
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")

        try:
            logger.debug(
                "S3 upload initiated: bucket=%s, key=%s, size_bytes=%d",
                self.bucket_name,
                key,
                len(data),
            )
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.info("Uploaded %d bytes to %s", len(data), key)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("S3 upload client error (%s): %s", error_code, e)
            raise S3UploadError(f"S3 upload failed: {e}") from e
        except NoCredentialsError:
            logger.error("AWS credentials not available for upload")
            raise S3UploadError("AWS credentials not configured") from None
        except Exception as e:
            logger.exception("Unexpected error uploading to S3: %s", e)
            raise S3UploadError(f"Unexpected S3 upload error: {e}") from e

    async def list_objects(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List objects under a prefix using list_objects_v2.

        Args:
            prefix: S3 key prefix to filter objects.

        Returns:
            List of dicts with keys such as Key, Size, LastModified.

        Raises:
            S3DownloadError: If the listing fails or bucket is not configured.
        """
        if not self.bucket_name:
            raise S3DownloadError("S3 bucket name not configured")

        def _list() -> List[Dict[str, Any]]:
            try:
                paginator = self.client.get_paginator("list_objects_v2")
                results: List[Dict[str, Any]] = []
                for page in paginator.paginate(
                    Bucket=self.bucket_name, Prefix=prefix
                ):
                    results.extend(page.get("Contents", []))
                return results
            except ClientError as e:
                raise S3DownloadError(f"S3 list failed: {e}") from e

        return await asyncio.to_thread(_list)

    async def head_object(self, key: str) -> Dict[str, Any]:
        """Return metadata for a single S3 object.

        Args:
            key: The S3 key (path) to inspect.

        Returns:
            Dict with metadata fields such as ETag, ContentLength, LastModified.

        Raises:
            S3DownloadError: If the object does not exist or the request fails.
        """
        if not self.bucket_name:
            raise S3DownloadError("S3 bucket name not configured")

        def _head() -> Dict[str, Any]:
            try:
                response = self.client.head_object(
                    Bucket=self.bucket_name, Key=key
                )
                return dict(response)
            except ClientError as e:
                raise S3DownloadError(f"S3 head_object failed: {e}") from e

        return await asyncio.to_thread(_head)

    async def delete_object(self, key: str) -> None:
        """Delete a single object from S3.

        Args:
            key: The S3 key (path) to delete.

        Raises:
            S3UploadError: If the deletion fails or bucket is not configured.
        """
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")

        def _delete() -> None:
            try:
                self.client.delete_object(Bucket=self.bucket_name, Key=key)
            except ClientError as e:
                raise S3UploadError(f"S3 delete failed: {e}") from e

        await asyncio.to_thread(_delete)

    async def delete_objects(self, keys: List[str]) -> None:
        """Delete multiple objects via delete_objects batch API.

        Args:
            keys: List of S3 keys to delete.

        Raises:
            S3UploadError: If the batch deletion fails or bucket is not configured.
        """
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")

        def _delete_batch() -> None:
            try:
                self.client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={
                        "Objects": [{"Key": k} for k in keys],
                        "Quiet": True,
                    },
                )
            except ClientError as e:
                raise S3UploadError(f"S3 batch delete failed: {e}") from e

        await asyncio.to_thread(_delete_batch)

    async def generate_presigned_post(
        self,
        key: str,
        content_type: str = "application/pdf",
        expires: int = 3600,
    ) -> Dict[str, Any]:
        """Generate a presigned POST URL for direct browser upload.

        Args:
            key: The S3 key (path) where the uploaded object will be stored.
            content_type: Expected Content-Type of the upload. Defaults to application/pdf.
            expires: Expiration time in seconds. Defaults to 3600.

        Returns:
            Dict with "url" and "fields" for the presigned POST.

        Raises:
            S3UploadError: If generation fails or bucket is not configured.
        """
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")

        def _generate() -> Dict[str, Any]:
            try:
                return self.client.generate_presigned_post(
                    Bucket=self.bucket_name,
                    Key=key,
                    Fields={"Content-Type": content_type},
                    Conditions=[
                        {"Content-Type": content_type},
                        ["content-length-range", 1024, 104_857_600],
                    ],
                    ExpiresIn=expires,
                )
            except ClientError as e:
                raise S3UploadError(
                    f"Presigned post generation failed: {e}"
                ) from e

        return await asyncio.to_thread(_generate)
