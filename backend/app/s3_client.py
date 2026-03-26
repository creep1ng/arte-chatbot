"""S3 client module for downloading technical datasheets from AWS S3.

This module provides a client to interact with AWS S3 for downloading
PDF files containing technical product datasheets.
"""

import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from backend.app.config import settings

logger = logging.getLogger(__name__)


class S3DownloadError(Exception):
    """Raised when S3 download operations fail."""

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
            aws_access_key_id: AWS access key ID. Defaults to AWS_ACCESS_KEY_ID env var.
            aws_secret_access_key: AWS secret access key. Defaults to AWS_SECRET_ACCESS_KEY env var.
            aws_region: AWS region. Defaults to AWS_REGION env var.
        """
        self.bucket_name = (
            bucket_name if bucket_name is not None else os.getenv("AWS_BUCKET_NAME", "")
        )
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key_id = (
            aws_access_key_id
            or os.getenv("AWS_ACCESS_KEY_ID")
            or settings.aws_access_key_id
        )
        self.aws_secret_access_key = (
            aws_secret_access_key
            or os.getenv("AWS_SECRET_ACCESS_KEY")
            or settings.aws_secret_access_key
        )
        self.aws_region = aws_region or os.getenv("AWS_REGION") or settings.aws_region

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
            logger.info(f"Downloading S3 object: {self.bucket_name}/{s3_key}")
            response = self.client.get_object(Bucket=self.bucket_name, Key=s3_key)
            pdf_bytes = response["Body"].read()
            logger.info(f"Downloaded {len(pdf_bytes)} bytes from {s3_key}")
            return pdf_bytes
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"S3 client error ({error_code}): {e}")
            if error_code == "NoSuchKey":
                raise S3DownloadError(f"File not found in S3: {s3_key}") from e
            raise S3DownloadError(f"S3 download failed: {e}") from e
        except NoCredentialsError:
            logger.error("AWS credentials not available")
            raise S3DownloadError("AWS credentials not configured") from None
        except Exception as e:
            logger.exception(f"Unexpected error downloading from S3: {e}")
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
            return True
        except ClientError:
            return False
