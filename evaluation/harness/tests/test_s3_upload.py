from pathlib import Path
from unittest.mock import MagicMock, patch

from evaluation.harness.s3_upload import (
    build_prefix,
    generate_metadata,
    get_harness_version,
    upload_results,
    upload_results_with_metadata,
)


class TestBuildPrefix:
    def test_ci_prefix_format(self) -> None:
        prefix = build_prefix("ci", "main", "20240515_120000")
        assert prefix == "evaluation/ci/main/20240515_120000/"

    def test_manual_prefix_format(self) -> None:
        prefix = build_prefix("manual", "alice", "20240515_120000")
        assert prefix == "evaluation/manual/alice/20240515_120000/"

    def test_manual_prefix_without_timestamp(self) -> None:
        prefix = build_prefix("manual", "bob")
        assert prefix.startswith("evaluation/manual/bob/")
        assert prefix.endswith("/")

    def test_ci_prefix_without_timestamp(self) -> None:
        prefix = build_prefix("ci", "develop")
        assert prefix.startswith("evaluation/ci/develop/")
        assert prefix.endswith("/")


class TestGenerateMetadata:
    @patch("evaluation.harness.s3_upload.subprocess.run")
    def test_returns_expected_fields(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="abc1234", returncode=0)
        metadata = generate_metadata("ci", "github-actions")
        assert "git_commit" in metadata
        assert "git_branch" in metadata
        assert metadata["trigger"] == "ci"
        assert metadata["runner"] == "github-actions"
        assert "timestamp_utc" in metadata
        assert "harness_version" in metadata

    @patch("evaluation.harness.s3_upload.subprocess.run")
    def test_fallback_on_git_failure(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = Exception("git not found")
        metadata = generate_metadata("manual", "local")
        assert metadata["git_commit"] == "unknown"
        assert metadata["git_branch"] == "unknown"


class TestGetHarnessVersion:
    def test_returns_12_char_hash(self) -> None:
        version = get_harness_version()
        assert len(version) == 12
        assert version.isalnum() or any(c in version for c in "abcdef")


class TestUploadResults:
    @patch.dict(
        "os.environ",
        {"AWS_ACCESS_KEY_ID": "fake", "AWS_SECRET_ACCESS_KEY": "fake"},
    )
    @patch("evaluation.harness.s3_upload.boto3.client")
    def test_uploads_all_json_and_csv_files(
        self, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        json_file = tmp_path / "results.json"
        json_file.write_text('{"test": true}')
        csv_file = tmp_path / "results.csv"
        csv_file.write_text("a,b\n1,2")

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        keys = upload_results(tmp_path, "evaluation/manual/test/")

        assert len(keys) == 2
        assert "results.json" in keys[0]
        assert "results.csv" in keys[1]
        assert mock_s3.upload_file.call_count == 2

    @patch.dict(
        "os.environ",
        {
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("evaluation.harness.s3_upload.boto3.client")
    def test_uses_default_credential_chain_when_no_static_credentials(
        self, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        json_file = tmp_path / "results.json"
        json_file.write_text('{"test": true}')

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        keys = upload_results(tmp_path, "test/")
        assert keys == ["test/results.json"]
        mock_boto.assert_called_once_with("s3", region_name="us-east-1")

    @patch.dict(
        "os.environ",
        {"AWS_ACCESS_KEY_ID": "fake", "AWS_SECRET_ACCESS_KEY": "fake"},
    )
    @patch("evaluation.harness.s3_upload.boto3.client")
    def test_handles_s3_error_gracefully(
        self, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        from botocore.exceptions import ClientError

        json_file = tmp_path / "results.json"
        json_file.write_text('{"test": true}')

        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "InternalError"}}, "PutObject"
        )
        mock_boto.return_value = mock_s3

        keys = upload_results(tmp_path, "test/")
        assert keys == []


class TestUploadResultsWithMetadata:
    @patch.dict(
        "os.environ",
        {"AWS_ACCESS_KEY_ID": "fake", "AWS_SECRET_ACCESS_KEY": "fake"},
    )
    @patch("evaluation.harness.s3_upload.boto3.client")
    @patch("evaluation.harness.s3_upload.subprocess.run")
    def test_uploads_metadata_with_default_credential_chain(
        self, mock_run: MagicMock, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(stdout="abc1234", returncode=0)

        json_file = tmp_path / "results.json"
        json_file.write_text('{"test": true}')

        with patch.dict(
            "os.environ",
            {
                "AWS_ACCESS_KEY_ID": "",
                "AWS_SECRET_ACCESS_KEY": "",
                "AWS_REGION": "us-east-1",
            },
        ):
            keys = upload_results_with_metadata(
                tmp_path, "evaluation/manual/testuser/", "manual", "testuser"
            )
        assert keys == [
            "evaluation/manual/testuser/results.json",
            "evaluation/manual/testuser/metadata.json",
        ]
        assert mock_boto.call_args_list[0].args == ("s3",)
        assert mock_boto.call_args_list[0].kwargs == {"region_name": "us-east-1"}

    @patch.dict(
        "os.environ",
        {"AWS_ACCESS_KEY_ID": "fake", "AWS_SECRET_ACCESS_KEY": "fake"},
    )
    @patch("evaluation.harness.s3_upload.boto3.client")
    @patch("evaluation.harness.s3_upload.subprocess.run")
    def test_uploads_results_plus_metadata(
        self, mock_run: MagicMock, mock_boto: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(stdout="abc1234", returncode=0)

        json_file = tmp_path / "results.json"
        json_file.write_text('{"test": true}')

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        keys = upload_results_with_metadata(
            tmp_path, "evaluation/manual/testuser/", "manual", "testuser"
        )

        assert len(keys) == 2
        assert any("metadata.json" in k for k in keys)
        assert any("results.json" in k for k in keys)
