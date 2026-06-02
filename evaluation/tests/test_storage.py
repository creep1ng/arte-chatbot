"""Tests for shared evaluation storage S3 credential configuration."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from evaluation.storage import upload_to_s3


class TestUploadToS3Credentials:
    """Tests for boto3 default credential-chain behavior."""

    @patch("evaluation.storage.boto3.client")
    def test_uses_default_credential_chain_when_static_keys_absent(
        self, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        """Missing static keys should not skip uploads in deployed runtimes."""
        file_path = tmp_path / "results.json"
        file_path.write_text('{"ok": true}')
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        with patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=True):
            uploaded = upload_to_s3(file_path, "evaluations/test/results.json")

        assert uploaded is True
        mock_boto.assert_called_once_with("s3", region_name="eu-west-1")
        mock_s3.upload_file.assert_called_once()

    @patch("evaluation.storage.boto3.client")
    def test_uses_static_local_keys_when_present(
        self, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        """Explicit local AWS keys remain supported for manual uploads."""
        file_path = tmp_path / "results.json"
        file_path.write_text('{"ok": true}')
        env = {
            "AWS_ACCESS_KEY_ID": "local-access",
            "AWS_SECRET_ACCESS_KEY": "local-secret",
            "AWS_SESSION_TOKEN": "local-token",
            "AWS_REGION": "us-west-2",
        }

        with patch.dict(os.environ, env, clear=True):
            uploaded = upload_to_s3(file_path, "evaluations/test/results.json")

        assert uploaded is True
        mock_boto.assert_called_once_with(
            "s3",
            aws_access_key_id="local-access",
            aws_secret_access_key="local-secret",
            aws_session_token="local-token",
            region_name="us-west-2",
        )
