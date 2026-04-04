"""
Unit tests for the s3_client.py module.

Tests the S3 client for downloading technical datasheets from AWS S3.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.app.s3_client import S3DownloadError


class TestS3ClientInitialization:
    """Tests for S3Client initialization.
    
    These tests use patch to mock the settings object before importing S3Client,
    ensuring that environment variable changes are reflected during initialization.
    """

    def test_s3_client_default_env_vars(self) -> None:
        """Test S3Client initialization with default env vars."""
        mock_settings = MagicMock()
        mock_settings.aws_bucket_name = ""
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        
        with patch.dict(os.environ, {}, clear=True):
            with patch("backend.app.s3_client.settings", mock_settings):
                from backend.app.s3_client import S3Client
                client = S3Client()
                assert client.bucket_name == ""

    def test_s3_client_with_bucket_env_var(self) -> None:
        """Test S3Client initialization reads bucket from env var."""
        mock_settings = MagicMock()
        mock_settings.aws_bucket_name = "default-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        
        with patch.dict(os.environ, {"AWS_BUCKET_NAME": "test-bucket"}, clear=True):
            with patch("backend.app.s3_client.settings", mock_settings):
                from backend.app.s3_client import S3Client
                client = S3Client()
                assert client.bucket_name == "test-bucket"

    def test_s3_client_explicit_parameters(self) -> None:
        """Test S3Client initialization with explicit parameters."""
        from backend.app.s3_client import S3Client
        client = S3Client(
            bucket_name="my-bucket",
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            aws_region="us-west-2",
        )
        assert client.bucket_name == "my-bucket"
        assert client.aws_access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert client.aws_region == "us-west-2"

    def test_s3_client_default_region(self) -> None:
        """Test S3Client uses default region when not specified."""
        mock_settings = MagicMock()
        mock_settings.aws_bucket_name = "test-bucket"
        mock_settings.aws_region = "default-region"
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        
        with patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=True):
            with patch("backend.app.s3_client.settings", mock_settings):
                from backend.app.s3_client import S3Client
                client = S3Client()
                assert client.aws_region == "eu-west-1"

    def test_s3_client_default_region_fallback(self) -> None:
        """Test S3Client falls back to us-east-1 when no region env var."""
        mock_settings = MagicMock()
        mock_settings.aws_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        
        with patch.dict(os.environ, {}, clear=True):
            with patch("backend.app.s3_client.settings", mock_settings):
                from backend.app.s3_client import S3Client
                client = S3Client()
                assert client.aws_region == "us-east-1"


class TestS3DownloadPdfSync:
    """Tests for _download_pdf_sync method."""

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_sync_success(self, mock_boto3: MagicMock) -> None:
        """Test _download_pdf_sync returns bytes on success."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"%PDF-1.4 test content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        client = S3Client(bucket_name="test-bucket")
        result = client._download_pdf_sync("paneles/test-panel.pdf")

        assert isinstance(result, bytes)
        assert b"%PDF-1.4" in result
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="paneles/test-panel.pdf"
        )

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_sync_file_not_found(self, mock_boto3: MagicMock) -> None:
        """Test _download_pdf_sync raises S3DownloadError when file not found."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client._download_pdf_sync("paneles/nonexistent.pdf")

        assert "File not found in S3" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_sync_no_bucket_configured(
        self, mock_boto3: MagicMock
    ) -> None:
        """Test _download_pdf_sync raises error when bucket not configured."""
        client = S3Client(bucket_name="")

        with pytest.raises(S3DownloadError) as exc_info:
            client._download_pdf_sync("test.pdf")

        assert "bucket name not configured" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_sync_generic_client_error(
        self, mock_boto3: MagicMock
    ) -> None:
        """Test _download_pdf_sync raises S3DownloadError on generic client error."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client._download_pdf_sync("test.pdf")

        assert "S3 download failed" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_sync_no_credentials(self, mock_boto3: MagicMock) -> None:
        """Test _download_pdf_sync raises error when credentials not available."""
        from botocore.exceptions import NoCredentialsError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.get_object.side_effect = NoCredentialsError()

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client._download_pdf_sync("test.pdf")

        assert "credentials" in str(exc_info.value).lower()


class TestS3DownloadPdf:
    """Tests for async download_pdf method."""

    @pytest.mark.asyncio
    @patch("backend.app.s3_client.boto3")
    async def test_download_pdf_success(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf returns bytes on success."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"%PDF-1.4 test content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        client = S3Client(bucket_name="test-bucket")
        result = await client.download_pdf("paneles/test-panel.pdf")

        assert isinstance(result, bytes)
        assert b"%PDF-1.4" in result

    @pytest.mark.asyncio
    @patch("backend.app.s3_client.boto3")
    async def test_download_pdf_file_not_found(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf raises S3DownloadError when file not found."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            await client.download_pdf("paneles/nonexistent.pdf")

        assert "File not found in S3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_pdf_no_bucket_configured(self) -> None:
        """Test download_pdf raises error when bucket not configured."""
        client = S3Client(bucket_name="")

        with pytest.raises(S3DownloadError) as exc_info:
            await client.download_pdf("test.pdf")

        assert "bucket name not configured" in str(exc_info.value)


class TestS3FileExistsSync:
    """Tests for _file_exists_sync method."""

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_sync_returns_true(self, mock_boto3: MagicMock) -> None:
        """Test _file_exists_sync returns True when file exists."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.return_value = {}

        client = S3Client(bucket_name="test-bucket")
        result = client._file_exists_sync("paneles/test.pdf")

        assert result is True
        mock_s3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="paneles/test.pdf"
        )

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_sync_returns_false(self, mock_boto3: MagicMock) -> None:
        """Test _file_exists_sync returns False when file doesn't exist."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        client = S3Client(bucket_name="test-bucket")
        result = client._file_exists_sync("paneles/nonexistent.pdf")

        assert result is False

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_sync_no_bucket(self, mock_boto3: MagicMock) -> None:
        """Test _file_exists_sync returns False when bucket not configured."""
        client = S3Client(bucket_name="")

        result = client._file_exists_sync("test.pdf")

        assert result is False
        mock_boto3.client.assert_not_called()


class TestS3FileExists:
    """Tests for async file_exists method."""

    @pytest.mark.asyncio
    @patch("backend.app.s3_client.boto3")
    async def test_file_exists_returns_true(self, mock_boto3: MagicMock) -> None:
        """Test file_exists returns True when file exists."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.return_value = {}

        client = S3Client(bucket_name="test-bucket")
        result = await client.file_exists("paneles/test.pdf")

        assert result is True

    @pytest.mark.asyncio
    @patch("backend.app.s3_client.boto3")
    async def test_file_exists_returns_false(self, mock_boto3: MagicMock) -> None:
        """Test file_exists returns False when file doesn't exist."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        client = S3Client(bucket_name="test-bucket")
        result = await client.file_exists("paneles/nonexistent.pdf")

        assert result is False

    @pytest.mark.asyncio
    async def test_file_exists_no_bucket(self) -> None:
        """Test file_exists returns False when bucket not configured."""
        client = S3Client(bucket_name="")

        result = await client.file_exists("test.pdf")

        assert result is False


class TestS3ClientLazyInitialization:
    """Tests for lazy client initialization."""

    @patch("backend.app.s3_client.boto3")
    def test_client_property_lazy_init(self, mock_boto3: MagicMock) -> None:
        """Test that boto3 client is not initialized until accessed."""
        client = S3Client(bucket_name="test-bucket")

        assert client._client is None

        _ = client.client

        assert client._client is not None
        mock_boto3.client.assert_called_once()


class TestS3DownloadError:
    """Tests for S3DownloadError exception."""

    def test_s3_download_error_is_exception(self) -> None:
        """Test S3DownloadError inherits from Exception."""
        error = S3DownloadError("Test error")
        assert isinstance(error, Exception)

    def test_s3_download_error_message(self) -> None:
        """Test S3DownloadError preserves error message."""
        error = S3DownloadError("Custom error message")
        assert str(error) == "Custom error message"
