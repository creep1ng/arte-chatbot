"""File Inputs client module for OpenAI Files API integration.

This module provides a client to upload PDF files to OpenAI's Files API
and manage file lifecycle for technical datasheet analysis.
"""

import io
import logging
from typing import Optional

from openai import OpenAI
from openai import APIError, AuthenticationError, BadRequestError

from backend.app.config import settings
from backend.app.secret_resolver import configured_secret_value

logger = logging.getLogger(__name__)


class FileUploadError(Exception):
    """Raised when file upload operations fail."""

    pass


class FileInputsClient:
    """Client for interacting with OpenAI Files API for PDF uploads."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize the File Inputs client.

        Args:
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
                     If provided explicitly, takes precedence over settings.
        """
        # Use explicit parameter if provided, otherwise fallback to plaintext env
        # or Lambda runtime secret references resolved through AWS IAM.
        self.api_key = (
            api_key
            if api_key is not None
            else configured_secret_value(
                settings.openai_api_key,
                settings.openai_api_key_secret_ref,
                region_name=settings.aws_region,
            )
        )
        if not self.api_key:
            raise FileUploadError("OpenAI API key not configured")

        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy initialization of the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                timeout=settings.openai_timeout_seconds,
            )
        return self._client

    def upload_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        timeout_seconds: Optional[float] = None,
    ) -> str:
        """Upload a PDF file to OpenAI Files API with purpose="user_data".

        Args:
            pdf_bytes: Raw bytes of the PDF file.
            filename: Name for the file (e.g., "jinko-tiger-pro-460w.pdf").

        Returns:
            The file_id from OpenAI that can be used in Chat Completions.

        Raises:
            FileUploadError: If the upload fails.
        """
        if not self.api_key:
            raise FileUploadError("OpenAI API key not configured")

        if not filename.lower().endswith(".pdf"):
            raise FileUploadError("Only PDF files can be uploaded")
        if len(pdf_bytes) > settings.max_pdf_bytes:
            raise FileUploadError("PDF exceeds maximum allowed size")
        if not pdf_bytes.startswith(b"%PDF"):
            raise FileUploadError("Invalid PDF content")

        try:
            logger.debug(
                "File Input upload initiated: size_bytes=%d",
                len(pdf_bytes),
            )

            # Create a file-like object from bytes
            file_obj = io.BytesIO(pdf_bytes)
            file_obj.name = filename

            # Upload the file with purpose="user_data" for use in Chat Completions
            request_client = self.client
            if timeout_seconds is not None:
                request_client = request_client.with_options(
                    timeout=min(timeout_seconds, settings.openai_timeout_seconds),
                    max_retries=0,
                )
            response = request_client.files.create(
                file=file_obj,
                purpose="user_data",
            )

            file_id = response.id
            logger.info("File Input upload completed: size_bytes=%d", len(pdf_bytes))
            return file_id

        except AuthenticationError as e:
            logger.error("OpenAI authentication error during File Input upload")
            raise FileUploadError("Invalid OpenAI API key") from e
        except BadRequestError as e:
            logger.error("OpenAI rejected File Input upload")
            raise FileUploadError("Invalid file format or request") from e
        except APIError as e:
            logger.error(
                "OpenAI File Input upload failed: error_type=%s",
                type(e).__name__,
            )
            raise FileUploadError("OpenAI API error during File Input upload") from e
        except Exception as e:
            logger.error(
                "Unexpected File Input upload failure: error_type=%s",
                type(e).__name__,
            )
            raise FileUploadError("Unexpected File Input upload failure") from e

    def delete_file(
        self, file_id: str, timeout_seconds: Optional[float] = None
    ) -> None:
        """Delete a file from OpenAI Files API.

        Args:
            file_id: The file ID to delete.

        Raises:
            FileUploadError: If the deletion fails.
        """
        if not self.api_key:
            raise FileUploadError("OpenAI API key not configured")

        try:
            logger.debug("File Input deletion initiated")
            request_client = self.client
            if timeout_seconds is not None:
                request_client = request_client.with_options(
                    timeout=min(timeout_seconds, settings.openai_timeout_seconds),
                    max_retries=0,
                )
            request_client.files.delete(file_id)
            logger.info("File Input deletion completed")
        except AuthenticationError as e:
            logger.error("OpenAI authentication error during File Input deletion")
            raise FileUploadError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error(
                "OpenAI File Input deletion failed: error_type=%s",
                type(e).__name__,
            )
            raise FileUploadError("Error deleting file") from e
        except Exception as e:
            logger.error(
                "Unexpected File Input deletion failure: error_type=%s",
                type(e).__name__,
            )
            raise FileUploadError("Unexpected File Input deletion failure") from e
