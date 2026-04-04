"""
Unit tests for the file_inputs.py module.

Tests the File Inputs client for OpenAI Files API integration.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestFileInputsClientInitialization:
    """Tests for FileInputsClient initialization.
    
    These tests use patch to mock the settings object in both config and file_inputs modules,
    and reimport FileInputsClient within the patch context to ensure proper behavior.
    """

    def test_file_inputs_client_default_env_vars(self) -> None:
        """Test FileInputsClient initialization with default env vars."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "sk-test-key123"
        
        with patch("backend.app.config.settings", mock_settings):
            with patch("backend.app.file_inputs.settings", mock_settings):
                import importlib
                import backend.app.file_inputs
                importlib.reload(backend.app.file_inputs)
                
                client = backend.app.file_inputs.FileInputsClient()
                assert client.api_key == "sk-test-key123"

    def test_file_inputs_client_explicit_api_key(self) -> None:
        """Test FileInputsClient initialization with explicit API key."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = None
        
        with patch("backend.app.config.settings", mock_settings):
            with patch("backend.app.file_inputs.settings", mock_settings):
                import importlib
                import backend.app.file_inputs
                importlib.reload(backend.app.file_inputs)
                
                client = backend.app.file_inputs.FileInputsClient(api_key="sk-explicit-key456")
                assert client.api_key == "sk-explicit-key456"

    def test_file_inputs_client_raises_without_api_key(self) -> None:
        """Test FileInputsClient raises error when no API key available."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = None
        
        with patch("backend.app.config.settings", mock_settings):
            with patch("backend.app.file_inputs.settings", mock_settings):
                import importlib
                import backend.app.file_inputs
                importlib.reload(backend.app.file_inputs)
                
                # Import FileUploadError from the reloaded module
                FileUploadError = backend.app.file_inputs.FileUploadError
                
                with pytest.raises(FileUploadError) as exc_info:
                    backend.app.file_inputs.FileInputsClient()

                assert "API key not configured" in str(exc_info.value)

    def test_file_inputs_client_uses_env_var(self) -> None:
        """Test FileInputsClient uses OPENAI_API_KEY env var when no explicit key."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "sk-env-key"
        
        with patch("backend.app.config.settings", mock_settings):
            with patch("backend.app.file_inputs.settings", mock_settings):
                import importlib
                import backend.app.file_inputs
                importlib.reload(backend.app.file_inputs)
                
                client = backend.app.file_inputs.FileInputsClient()
                assert client.api_key == "sk-env-key"

    def test_file_inputs_client_explicit_overrides_env(self) -> None:
        """Test explicit API key overrides env var."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "sk-settings-key"
        
        with patch("backend.app.config.settings", mock_settings):
            with patch("backend.app.file_inputs.settings", mock_settings):
                import importlib
                import backend.app.file_inputs
                importlib.reload(backend.app.file_inputs)
                
                client = backend.app.file_inputs.FileInputsClient(api_key="sk-explicit")
                assert client.api_key == "sk-explicit"


class TestFileInputsClientUpload:
    """Tests for upload_pdf method."""

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_upload_pdf_success(self, mock_openai_class: MagicMock) -> None:
        """Test upload_pdf returns file_id on success."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_file = MagicMock()
        mock_file.id = "file-abc123xyz"
        mock_client.files.create.return_value = mock_file

        from backend.app.file_inputs import FileInputsClient
        client = FileInputsClient(api_key="sk-test-key")
        result = await client.upload_pdf(b"%PDF-1.4 test", "test-panel.pdf")

        assert result == "file-abc123xyz"
        mock_client.files.create.assert_called_once()

        call_kwargs = mock_client.files.create.call_args.kwargs
        assert call_kwargs["purpose"] == "user_data"

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_upload_pdf_raises_auth_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test upload_pdf raises FileUploadError on authentication error."""
        from openai import AuthenticationError
        from backend.app.file_inputs import FileInputsClient, FileUploadError

        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = AuthenticationError(
            message="Invalid key", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-invalid-key")

        with pytest.raises(FileUploadError) as exc_info:
            await client.upload_pdf(b"test content", "test.pdf")

        assert "Invalid OpenAI API key" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_upload_pdf_raises_bad_request_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test upload_pdf raises FileUploadError on bad request."""
        from openai import BadRequestError
        from backend.app.file_inputs import FileInputsClient, FileUploadError

        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = BadRequestError(
            message="Invalid file", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            await client.upload_pdf(b"not a pdf", "test.txt")

        assert "Invalid file format" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_upload_pdf_raises_api_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test upload_pdf raises FileUploadError on generic API error."""
        from openai import APIError
        from backend.app.file_inputs import FileInputsClient, FileUploadError

        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.create.side_effect = APIError(
            message="Rate limit", request=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            await client.upload_pdf(b"test content", "test.pdf")

        assert "OpenAI API error" in str(exc_info.value)


class TestFileInputsClientDelete:
    """Tests for delete_file method."""

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_delete_file_success(self, mock_openai_class: MagicMock) -> None:
        """Test delete_file calls OpenAI API correctly."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        from backend.app.file_inputs import FileInputsClient
        client = FileInputsClient(api_key="sk-test-key")
        await client.delete_file("file-abc123")

        mock_client.files.delete.assert_called_once_with("file-abc123")

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_delete_file_raises_auth_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test delete_file raises FileUploadError on authentication error."""
        from openai import AuthenticationError
        from backend.app.file_inputs import FileInputsClient, FileUploadError

        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.delete.side_effect = AuthenticationError(
            message="Invalid key", response=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-invalid-key")

        with pytest.raises(FileUploadError) as exc_info:
            await client.delete_file("file-abc123")

        assert "Invalid OpenAI API key" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("backend.app.file_inputs.AsyncOpenAI")
    async def test_delete_file_raises_api_error(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test delete_file raises FileUploadError on API error."""
        from openai import APIError
        from backend.app.file_inputs import FileInputsClient, FileUploadError

        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.files.delete.side_effect = APIError(
            message="Server error", request=MagicMock(), body={}
        )

        client = FileInputsClient(api_key="sk-test-key")

        with pytest.raises(FileUploadError) as exc_info:
            await client.delete_file("file-abc123")

        assert "Error deleting file" in str(exc_info.value)


class TestFileInputsClientLazyInitialization:
    """Tests for lazy client initialization."""

    @patch("backend.app.file_inputs.AsyncOpenAI")
    def test_client_property_lazy_init(self, mock_openai_class: MagicMock) -> None:
        """Test that AsyncOpenAI client is not initialized until accessed."""
        from backend.app.file_inputs import FileInputsClient
        client = FileInputsClient(api_key="sk-test-key")

        assert client._client is None

        _ = client.client

        assert client._client is not None
        mock_openai_class.assert_called_once_with(api_key="sk-test-key")


class TestFileUploadError:
    """Tests for FileUploadError exception."""

    def test_file_upload_error_is_exception(self) -> None:
        """Test FileUploadError inherits from Exception."""
        from backend.app.file_inputs import FileUploadError
        error = FileUploadError("Test error")
        assert isinstance(error, Exception)

    def test_file_upload_error_message(self) -> None:
        """Test FileUploadError preserves error message."""
        from backend.app.file_inputs import FileUploadError
        error = FileUploadError("Custom error message")
        assert str(error) == "Custom error message"
