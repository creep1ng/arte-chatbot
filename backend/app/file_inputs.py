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
        """
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise FileUploadError("OpenAI API key not configured")

        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy initialization of the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def upload_pdf(self, pdf_bytes: bytes, filename: str) -> str:
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

        try:
            logger.info(f"Uploading PDF to OpenAI Files API: {filename}")

            # Create a file-like object from bytes
            file_obj = io.BytesIO(pdf_bytes)
            file_obj.name = filename

            # Upload the file with purpose="user_data" for use in Chat Completions
            response = self.client.files.create(
                file=file_obj,
                purpose="user_data",
            )

            file_id = response.id
            logger.info(f"Successfully uploaded file with ID: {file_id}")
            return file_id

        except AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise FileUploadError("Invalid OpenAI API key") from e
        except BadRequestError as e:
            logger.error(f"OpenAI bad request error: {e}")
            raise FileUploadError(f"Invalid file format or request: {e}") from e
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise FileUploadError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error uploading file: {e}")
            raise FileUploadError(f"Unexpected error: {e}") from e

    def delete_file(self, file_id: str) -> None:
        """Delete a file from OpenAI Files API.

        Args:
            file_id: The file ID to delete.

        Raises:
            FileUploadError: If the deletion fails.
        """
        if not self.api_key:
            raise FileUploadError("OpenAI API key not configured")

        try:
            logger.info(f"Deleting OpenAI file: {file_id}")
            self.client.files.delete(file_id)
            logger.info(f"Successfully deleted file: {file_id}")
        except AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise FileUploadError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error(f"OpenAI API error deleting file: {e}")
            raise FileUploadError(f"Error deleting file: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error deleting file: {e}")
            raise FileUploadError(f"Unexpected error: {e}") from e
