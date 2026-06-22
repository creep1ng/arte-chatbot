"""Tests for Lambda runtime secret reference resolution."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException


class FakeAWSSecretClient:
    """Small boto3 client fake for SSM and Secrets Manager secret reads."""

    def __init__(self, service_name: str, values: dict[str, str]) -> None:
        self.service_name = service_name
        self.values = values

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:  # noqa: N803
        assert self.service_name == "ssm"
        assert WithDecryption is True
        return {"Parameter": {"Value": self.values[Name]}}

    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:  # noqa: N803
        assert self.service_name == "secretsmanager"
        return {"SecretString": self.values[SecretId]}


@pytest.fixture()
def secret_ref_environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Configure runtime secret refs without plaintext API key values."""
    values = {
        "/arte/prod/openai-api-key": "resolved-openai-key",
        "arn:aws:secretsmanager:us-east-2:123456789012:secret:chat-api-key": "resolved-chat-key",
        "/arte/prod/chatwoot-agent-bot-token": "resolved-chatwoot-token",
        "/arte/prod/chatwoot-webhook-secret": "resolved-chatwoot-secret",
    }
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("CHAT_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY_SECRET_REF", "/arte/prod/openai-api-key")
    monkeypatch.setenv(
        "CHAT_API_KEY_SECRET_REF",
        "arn:aws:secretsmanager:us-east-2:123456789012:secret:chat-api-key",
    )
    monkeypatch.setenv("CHATWOOT_AGENT_BOT_TOKEN", "")
    monkeypatch.setenv("CHATWOOT_WEBHOOK_SECRET", "")
    monkeypatch.setenv(
        "CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF",
        "/arte/prod/chatwoot-agent-bot-token",
    )
    monkeypatch.setenv(
        "CHATWOOT_WEBHOOK_SECRET_REF",
        "/arte/prod/chatwoot-webhook-secret",
    )
    monkeypatch.setenv("AWS_REGION", "us-east-2")

    from backend.app.config import settings
    from backend.app.secret_resolver import clear_runtime_secret_cache

    settings.reset()
    clear_runtime_secret_cache()

    def fake_boto3_client(
        service_name: str,
        *,
        region_name: str | None = None,
    ) -> FakeAWSSecretClient:
        assert region_name == "us-east-2"
        return FakeAWSSecretClient(service_name, values)

    monkeypatch.setattr("backend.app.secret_resolver.boto3.client", fake_boto3_client)
    return values


def test_file_inputs_uses_openai_secret_ref_for_sdk_client(
    secret_ref_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File Inputs initializes OpenAI with the resolved SSM secret value."""
    del secret_ref_environment
    from backend.app.file_inputs import FileInputsClient

    calls: list[dict[str, Any]] = []

    def fake_openai(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr("backend.app.file_inputs.OpenAI", fake_openai)

    client = FileInputsClient()
    _ = client.client

    assert client.api_key == "resolved-openai-key"
    assert calls[0]["api_key"] == "resolved-openai-key"


def test_llm_client_uses_openai_secret_ref_for_sdk_client(
    secret_ref_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMClient initializes OpenAI with the resolved SSM secret value."""
    del secret_ref_environment
    from backend.app.llm_client import LLMClient

    calls: list[dict[str, Any]] = []

    def fake_openai(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr("backend.app.llm_client.OpenAI", fake_openai)

    client = LLMClient()
    _ = client.openai_client

    assert client.api_key == "resolved-openai-key"
    assert calls[0]["api_key"] == "resolved-openai-key"


def test_auth_uses_chat_api_secret_ref(
    secret_ref_environment: dict[str, str],
) -> None:
    """API-key auth accepts the value resolved from Secrets Manager."""
    del secret_ref_environment
    from backend.app.auth import verify_api_key

    assert verify_api_key("resolved-chat-key") == "resolved-chat-key"

    with pytest.raises(HTTPException) as exc_info:
        verify_api_key("wrong-key")

    assert exc_info.value.status_code == 403


def test_chatwoot_uses_runtime_secret_refs(
    secret_ref_environment: dict[str, str],
) -> None:
    """Chatwoot runtime helpers resolve AgentBot and webhook secrets."""
    from backend.main import (
        _get_chatwoot_agent_bot_token,
        _get_chatwoot_webhook_secret,
    )

    assert _get_chatwoot_agent_bot_token() == secret_ref_environment[
        "/arte/prod/chatwoot-agent-bot-token"
    ]
    assert _get_chatwoot_webhook_secret() == secret_ref_environment[
        "/arte/prod/chatwoot-webhook-secret"
    ]
