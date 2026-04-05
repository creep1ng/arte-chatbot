"""
Unit tests for the s3_client.py module.

Tests the S3 client for downloading technical datasheets from AWS S3.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from backend.app.s3_client import S3Client, S3DownloadError


class TestS3ClientInitialization:
    """Tests for S3Client initialization."""

    @patch("backend.app.s3_client.settings")
    def test_s3_client_default_env_vars(self, mock_settings: MagicMock) -> None:
        """Test S3Client initialization with default env vars."""
        mock_settings.aws_bucket_name = ""
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        mock_settings.aws_region = "us-east-1"
        
        with patch.dict(os.environ, {}, clear=True):
            client = S3Client()
            # Should not raise, but bucket_name will be empty
            assert client.bucket_name == ""

    @patch.dict(os.environ, {"AWS_BUCKET_NAME": "test-bucket"}, clear=True)
    def test_s3_client_with_bucket_env_var(self) -> None:
        """Test S3Client initialization reads bucket from env var."""
        client = S3Client()
        assert client.bucket_name == "test-bucket"

    def test_s3_client_explicit_parameters(self) -> None:
        """Test S3Client initialization with explicit parameters."""
        client = S3Client(
            bucket_name="my-bucket",
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            aws_region="us-west-2",
        )
        assert client.bucket_name == "my-bucket"
        assert client.aws_access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert client.aws_region == "us-west-2"

    @patch("backend.app.s3_client.settings")
    def test_s3_client_default_region(self, mock_settings: MagicMock) -> None:
        """Test S3Client uses region when not specified via parameter."""
        mock_settings.aws_bucket_name = ""
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        mock_settings.aws_region = "eu-west-1"
        
        with patch.dict(os.environ, {}, clear=True):
            client = S3Client()
            assert client.aws_region == "eu-west-1"

    @patch("backend.app.s3_client.settings")
    def test_s3_client_default_region_fallback(self, mock_settings: MagicMock) -> None:
        """Test S3Client falls back to us-east-1 when no region specified."""
        mock_settings.aws_bucket_name = ""
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None
        mock_settings.aws_region = "us-east-1"
        
        with patch.dict(os.environ, {}, clear=True):
            client = S3Client()
            assert client.aws_region == "us-east-1"


class TestS3DownloadPdf:
    """Tests for download_pdf method."""

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_success(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf returns bytes on success."""
        # Setup mock
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        # Mock response with PDF bytes
        mock_body = MagicMock()
        mock_body.read.return_value = b"%PDF-1.4 test content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        client = S3Client(bucket_name="test-bucket")
        result = client.download_pdf("paneles/test-panel.pdf")

        assert isinstance(result, bytes)
        assert b"%PDF-1.4" in result
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="paneles/test-panel.pdf"
        )

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_file_not_found(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf raises S3DownloadError when file not found."""
        from botocore.exceptions import ClientError

        # Setup mock to raise NoSuchKey error
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client.download_pdf("paneles/nonexistent.pdf")

        assert "File not found in S3" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_no_bucket_configured(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf raises error when bucket not configured."""
        client = S3Client(bucket_name="")

        with pytest.raises(S3DownloadError) as exc_info:
            client.download_pdf("test.pdf")

        assert "bucket name not configured" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_generic_client_error(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf raises S3DownloadError on generic client error."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client.download_pdf("test.pdf")

        assert "S3 download failed" in str(exc_info.value)

    @patch("backend.app.s3_client.boto3")
    def test_download_pdf_no_credentials(self, mock_boto3: MagicMock) -> None:
        """Test download_pdf raises error when credentials not available."""
        from botocore.exceptions import NoCredentialsError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.get_object.side_effect = NoCredentialsError()

        client = S3Client(bucket_name="test-bucket")

        with pytest.raises(S3DownloadError) as exc_info:
            client.download_pdf("test.pdf")

        assert "credentials" in str(exc_info.value).lower()


class TestS3FileExists:
    """Tests for file_exists method."""

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_returns_true(self, mock_boto3: MagicMock) -> None:
        """Test file_exists returns True when file exists."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.return_value = {}  # No exception means file exists

        client = S3Client(bucket_name="test-bucket")
        result = client.file_exists("paneles/test.pdf")

        assert result is True
        mock_s3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="paneles/test.pdf"
        )

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_returns_false(self, mock_boto3: MagicMock) -> None:
        """Test file_exists returns False when file doesn't exist."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        client = S3Client(bucket_name="test-bucket")
        result = client.file_exists("paneles/nonexistent.pdf")

        assert result is False

    @patch("backend.app.s3_client.boto3")
    def test_file_exists_no_bucket(self, mock_boto3: MagicMock) -> None:
        """Test file_exists returns False when bucket not configured."""
        client = S3Client(bucket_name="")

        result = client.file_exists("test.pdf")

        assert result is False
        # boto3 should not be called
        mock_boto3.client.assert_not_called()


class TestS3ClientLazyInitialization:
    """Tests for lazy client initialization."""

    @patch("backend.app.s3_client.boto3")
    def test_client_property_lazy_init(self, mock_boto3: MagicMock) -> None:
        """Test that boto3 client is not initialized until accessed."""
        client = S3Client(bucket_name="test-bucket")

        # Client should not be initialized yet
        assert client._client is None

        # Access the client property
        _ = client.client

        # Now it should be initialized
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