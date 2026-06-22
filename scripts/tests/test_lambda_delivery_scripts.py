"""Tests for Lambda delivery package, smoke, and rollback helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import zipfile

from botocore.exceptions import ClientError
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_lambda_package import (
    assert_sha256,
    dependency_install_command,
    scan_package,
    sha256_file,
)
from lambda_rollback import (
    discover_alias_target,
    rollback_lambda_alias,
)
from lambda_smoke import SmokeConfig, run_smoke


class FakeHttpClient:
    """HTTP test double for smoke checks."""

    def get(self, url: str, **_: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"status": "healthy"}, request=request)

    def post(self, url: str, **_: object) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "response": "ok",
                "session_id": "smoke-session",
                "num_sources": 1,
                "source_documents": [{"ruta": "raw/paneles/example.pdf"}],
            },
            request=request,
        )


class FakeTable:
    """DynamoDB Table test double."""

    def query(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["ExpressionAttributeValues"] == {
            ":pk": "local-staging#ci#SESSION#smoke-session"
        }
        return {"Items": [{"PK": "local-staging#ci#SESSION#smoke-session"}]}


class FakeDynamoDBResource:
    """DynamoDB resource test double."""

    def Table(self, table_name: str) -> FakeTable:  # noqa: N802 - boto3 API shape
        assert table_name == "state-table"
        return FakeTable()


class FakeDeniedDynamoDBClient:
    """DynamoDB client that simulates IAM denial."""

    def describe_table(self, *, TableName: str) -> None:  # noqa: N803 - boto3 API shape
        assert TableName == "denied-table"
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "DescribeTable",
        )


class FakeLambdaClient:
    """Lambda client test double for alias discovery and rollback."""

    def __init__(self) -> None:
        self.version = "7"
        self.updated_to = ""

    def get_alias(self, *, FunctionName: str, Name: str) -> dict[str, object]:  # noqa: N803
        assert FunctionName == "backend"
        assert Name == "live"
        return {"FunctionVersion": self.version, "RoutingConfig": {}}

    def update_alias(
        self,
        *,
        FunctionName: str,
        Name: str,
        FunctionVersion: str,
        Description: str,
    ) -> None:
        assert FunctionName == "backend"
        assert Name == "live"
        assert Description == "Rollback to version 6"
        self.updated_to = FunctionVersion
        self.version = FunctionVersion


def test_package_scan_rejects_env_files_and_plaintext_secret_markers(
    tmp_path: Path,
) -> None:
    """Lambda package scan must fail on local env files and obvious secrets."""
    package_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("backend/main.py", "print('ok')")
        archive.writestr(".env.deploy", "CHAT_API_KEY=secret")

    findings = scan_package(package_path)

    assert any("forbidden secret path" in finding for finding in findings)


def test_package_sha256_assertion_detects_mismatch(tmp_path: Path) -> None:
    """Package hash checks protect same-package promotion."""
    package_path = tmp_path / "package.zip"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("backend/main.py", "print('ok')")

    digest = sha256_file(package_path)
    assert_sha256(package_path, digest)
    with pytest.raises(SystemExit):
        assert_sha256(package_path, "0" * 64)


def test_dependency_install_uses_uv_pip_target_for_uv_run_compatibility(
    tmp_path: Path,
) -> None:
    """Package builds must not require pip inside the active uv environment."""
    requirements_path = tmp_path / "requirements.txt"
    package_root = tmp_path / "package"

    command = dependency_install_command(requirements_path, package_root)

    assert command[:3] == ["uv", "pip", "install"]
    assert "--python" in command
    assert sys.executable in command
    assert "--target" in command
    assert str(package_root) in command


def test_smoke_rejects_staging_when_base_url_matches_production() -> None:
    """Staging smoke must not accidentally target production."""
    config = SmokeConfig(
        base_url="https://chatbot.artesolutions.com.co",
        chat_api_key="key",
        forbidden_urls=("https://chatbot.artesolutions.com.co",),
    )

    with pytest.raises(RuntimeError, match="production host|forbidden"):
        run_smoke(config, http_client=FakeHttpClient())


def test_smoke_validates_health_chat_state_and_iam_denial() -> None:
    """Smoke checks cover direct endpoint, File Inputs, DynamoDB, and IAM denial."""
    config = SmokeConfig(
        base_url="https://staging-chatbot-api-ci.example.com",
        chat_api_key="key",
        require_source_docs=True,
        state_table_name="state-table",
        state_key_prefix="local-staging#ci",
        iam_denied_dynamodb_table_name="denied-table",
    )

    evidence = run_smoke(
        config,
        http_client=FakeHttpClient(),
        dynamodb_resource=FakeDynamoDBResource(),
        dynamodb_client=FakeDeniedDynamoDBClient(),
    )

    assert "health ok: healthy" in evidence
    assert "file inputs ok: source_documents=1" in evidence
    assert "dynamodb persistence ok" in evidence
    assert "iam denied ok: dynamodb" in evidence


def test_rollback_discovers_and_restores_lambda_alias() -> None:
    """Rollback helper must discover the old target before alias restore."""
    client = FakeLambdaClient()

    before = discover_alias_target(client, function_name="backend", alias_name="live")
    after = rollback_lambda_alias(
        client,
        function_name="backend",
        alias_name="live",
        target_version="6",
    )

    assert before.function_version == "7"
    assert client.updated_to == "6"
    assert after.function_version == "6"
