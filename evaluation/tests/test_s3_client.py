"""Tests for evaluation S3 reports client credential configuration."""

import os
from unittest.mock import MagicMock, patch

from evaluation.s3_client import S3ReportsClient


class TestS3ReportsClientCredentials:
    """Tests for boto3 credential provider usage."""

    @patch("evaluation.s3_client.boto3.client")
    def test_uses_default_credential_chain_when_static_keys_absent(
        self, mock_boto: MagicMock
    ) -> None:
        """The reports client must allow ECS/OIDC credentials from boto3."""
        with patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=True):
            S3ReportsClient()

        mock_boto.assert_called_once_with("s3", region_name="eu-west-1")

    @patch("evaluation.s3_client.boto3.client")
    def test_uses_static_local_keys_when_present(self, mock_boto: MagicMock) -> None:
        """Explicit local AWS keys remain supported for manual evaluation uploads."""
        env = {
            "AWS_ACCESS_KEY_ID": "local-access",
            "AWS_SECRET_ACCESS_KEY": "local-secret",
            "AWS_SESSION_TOKEN": "local-token",
            "AWS_REGION": "us-west-2",
        }
        with patch.dict(os.environ, env, clear=True):
            S3ReportsClient()

        mock_boto.assert_called_once_with(
            "s3",
            aws_access_key_id="local-access",
            aws_secret_access_key="local-secret",
            aws_session_token="local-token",
            region_name="us-west-2",
        )
