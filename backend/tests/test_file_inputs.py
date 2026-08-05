"""
Unit tests for the file_inputs.py module.

Tests the File Inputs client for OpenAI Files API integration.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from backend.app.file_inputs import FileInputsClient, FileUploadError


def _configure_openai_settings_mock(
    mock_settings: MagicMock,
    api_key: str | None,
) -> None:
    """Configure mocked settings for tests that do not use secret refs."""
    mock_settings.openai_api_key = api_key
    mock_settings.openai_api_key_secret_ref = None
    mock_settings.aws_region = "us-east-1"
    mock_settings.openai_timeout_seconds = 30.0


class TestFileInputsClientInitialization:
    """Tests for FileInputsClient initialization."""

    @patch("backend.app.file_inputs.settings")
    def test_file_inputs_client_default_env_vars(
        self, mock_settings: MagicMock
    ) -> None:
        """Test FileInputsClient initialization with default env vars."""
        _configure_openai_settings_mock(mock_settings, "sk-test-key123")
        client = FileInputsClient()
        assert client.api_key == "sk-test-key123"

    def test_file_inputs_client_explicit_api_key(self) -> None:
        """Test FileInputsClient initialization with explicit API key."""
        client = FileInputsClient(api_key="sk-explicit-key456")
        assert client.api_key == "sk-explicit-key456"

    @patch("backend.app.file_inputs.settings")
    def test_file_inputs_client_raises_without_api_key(
        self, mock_settings: MagicMock
    ) -> None:
        """Test FileInputsClient raises error when no API key available."""
        _configure_openai_settings_mock(mock_settings, None)
        with pytest.raises(FileUploadError) as exc_info:
            FileInputsClient()

        assert "API key not configured" in str(exc_info.value)

    @patch("backend.app.file_inputs.settings")
    def test_file_inputs_client_uses_env_var(self, mock_settings: MagicMock) -> None:
        """Test FileInputsClient uses settings when no explicit key."""
        _configure_openai_settings_mock(mock_settings, "sk-env-key")
        client = FileInputsClient()
        assert client.api_key == "sk-env-key"

    def test_file_inputs_client_explicit_overrides_env(self) -> None:
        """Test explicit API key overrides settings."""
        client = FileInputsClient(api_key="sk-explicit")
        assert client.api_key == "sk-explicit"


class TestFileInputsClientUpload:
    """Tests for upload_pdf method."""

    @patch("backend.app.file_inputs.OpenAI")
    def test_file_lifecycle_logs_omit_names_and_provider_ids(
        self,
        mock_openai_class: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="backend.app.file_inputs")
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.return_value.id = "file-private-123"
        client = FileInputsClient(api_key="sk-test-key")

        file_id = client.upload_pdf(b"%PDF-1.4 private", "cliente@example.com.pdf")
        client.delete_file(file_id)

        assert "size_bytes=16" in caplog.text
        assert "cliente@example.com.pdf" not in caplog.text
        assert "file-private-123" not in caplog.text

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_failure_logs_omit_error_body(
        self,
        mock_openai_class: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        secret = "cliente@example.com private provider body"
        caplog.set_level(logging.ERROR, logger="backend.app.file_inputs")
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = RuntimeError(secret)
        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError, match="Unexpected File Input"):
            client.upload_pdf(b"%PDF-1.4 private", "private.pdf")

        assert "error_type=RuntimeError" in caplog.text
        assert secret not in caplog.text

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_pdf_success(self, mock_openai_class: MagicMock) -> None:
        """Test upload_pdf returns file_id on success."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock response
        mock_file = MagicMock()
        mock_file.id = "file-abc123xyz"
        mock_client.files.create.return_value = mock_file

        client = FileInputsClient(api_key="sk-test-key")
        result = client.upload_pdf(b"%PDF-1.4 test", "test-panel.pdf")

        assert result == "file-abc123xyz"
        mock_client.files.create.assert_called_once()

        # Verify the call arguments
        call_kwargs = mock_client.files.create.call_args.kwargs
        assert call_kwargs["purpose"] == "user_data"

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_pdf_uses_bounded_zero_retry_client(
        self, mock_openai_class: MagicMock
    ) -> None:
        base_client = mock_openai_class.return_value
        bounded_client = base_client.with_options.return_value
        bounded_client.files.create.return_value.id = "file-bounded"

        result = FileInputsClient(api_key="sk-test-key").upload_pdf(
            b"%PDF-1.4 test", "test.pdf", timeout_seconds=2.5
        )

        assert result == "file-bounded"
        base_client.with_options.assert_called_once_with(timeout=2.5, max_retries=0)

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_pdf_raises_auth_error(self, mock_openai_class: MagicMock) -> None:
        """Test upload_pdf raises FileUploadError on authentication error."""
        from openai import AuthenticationError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = AuthenticationError(
            message="Invalid key", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-invalid-key")

        with pytest.raises(FileUploadError) as exc_info:
            client.upload_pdf(b"%PDF-1.4 test content", "test.pdf")

        assert "Invalid OpenAI API key" in str(exc_info.value)

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_pdf_raises_bad_request_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test upload_pdf raises FileUploadError on bad request."""
        from openai import BadRequestError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = BadRequestError(
            message="Invalid file", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            client.upload_pdf(b"%PDF-1.4 test content", "test.pdf")

        assert "Invalid file format" in str(exc_info.value)

    @patch("backend.app.file_inputs.OpenAI")
    def test_upload_pdf_raises_api_error(self, mock_openai_class: MagicMock) -> None:
        """Test upload_pdf raises FileUploadError on generic API error."""
        from openai import APIError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = APIError(
            message="Rate limit", request=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            client.upload_pdf(b"%PDF-1.4 test content", "test.pdf")

        assert "OpenAI API error" in str(exc_info.value)


class TestFileInputsClientDelete:
    """Tests for delete_file method."""

    @patch("backend.app.file_inputs.OpenAI")
    def test_delete_file_success(self, mock_openai_class: MagicMock) -> None:
        """Test delete_file calls OpenAI API correctly."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        client = FileInputsClient(api_key="sk-test-key")
        client.delete_file("file-abc123")

        mock_client.files.delete.assert_called_once_with("file-abc123")

    @patch("backend.app.file_inputs.OpenAI")
    def test_delete_file_uses_bounded_zero_retry_client(
        self, mock_openai_class: MagicMock
    ) -> None:
        base_client = mock_openai_class.return_value
        bounded_client = base_client.with_options.return_value

        FileInputsClient(api_key="sk-test-key").delete_file(
            "file-abc123", timeout_seconds=1.5
        )

        base_client.with_options.assert_called_once_with(timeout=1.5, max_retries=0)
        bounded_client.files.delete.assert_called_once_with("file-abc123")

    @patch("backend.app.file_inputs.OpenAI")
    def test_delete_file_raises_auth_error(self, mock_openai_class: MagicMock) -> None:
        """Test delete_file raises FileUploadError on authentication error."""
        from openai import AuthenticationError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.delete.side_effect = AuthenticationError(
            message="Invalid key", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-invalid-key")

        with pytest.raises(FileUploadError) as exc_info:
            client.delete_file("file-abc123")

        assert "Invalid OpenAI API key" in str(exc_info.value)

    @patch("backend.app.file_inputs.OpenAI")
    def test_delete_file_raises_api_error(self, mock_openai_class: MagicMock) -> None:
        """Test delete_file raises FileUploadError on API error."""
        from openai import APIError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.delete.side_effect = APIError(
            message="Server error", request=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            client.delete_file("file-abc123")

        assert "Error deleting file" in str(exc_info.value)


class TestFileInputsClientLazyInitialization:
    """Tests for lazy client initialization."""

    @patch("backend.app.file_inputs.OpenAI")
    def test_client_property_lazy_init(self, mock_openai_class: MagicMock) -> None:
        """Test that OpenAI client is not initialized until accessed."""
        client = FileInputsClient(api_key="sk-test-key")

        # Client should not be initialized yet
        assert client._client is None

        # Access the client property
        _ = client.client

        # Now it should be initialized
        assert client._client is not None
        mock_openai_class.assert_called_once_with(api_key="sk-test-key", timeout=30.0)

    def test_upload_pdf_rejects_non_pdf_filename(self) -> None:
        """Test upload_pdf rejects non-PDF filenames before upload."""
        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError, match="Only PDF files"):
            client.upload_pdf(b"%PDF-1.4 test content", "test.txt")

    def test_upload_pdf_rejects_invalid_pdf_content(self) -> None:
        """Test upload_pdf rejects non-PDF bytes before upload."""
        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError, match="Invalid PDF content"):
            client.upload_pdf(b"not a pdf", "test.pdf")


class TestFileUploadError:
    """Tests for FileUploadError exception."""

    def test_file_upload_error_is_exception(self) -> None:
        """Test FileUploadError inherits from Exception."""
        error = FileUploadError("Test error")
        assert isinstance(error, Exception)

    def test_file_upload_error_message(self) -> None:
        """Test FileUploadError preserves error message."""
        error = FileUploadError("Custom error message")
        assert str(error) == "Custom error message"
