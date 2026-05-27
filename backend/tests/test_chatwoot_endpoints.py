"""Endpoint wiring tests for Chatwoot webhook and health routes."""

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings


def _signed_headers(payload: bytes, secret: str = "test-secret") -> dict[str, str]:
    """Build Chatwoot signature headers for *payload*."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {"X-Chatwoot-Signature": digest}


def _chatwoot_signed_headers(
    payload: bytes,
    secret: str = "test-secret",
    timestamp: str = "1779820000",
) -> dict[str, str]:
    """Build real Chatwoot AgentBot timestamped signature headers."""
    signed_payload = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return {
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": f"sha256={digest}",
    }


def _valid_payload() -> dict[str, Any]:
    """Return a valid message_created webhook payload."""
    return {
        "event": "message_created",
        "account": {"id": 1},
        "conversation": {
            "id": 42,
            "status": "open",
            "inbox_id": 7,
            "contact_id": 9,
        },
        "sender": {"id": 11, "type": "contact", "name": "Cliente"},
        "message": {
            "id": 101,
            "content": "Hola",
            "content_type": "text",
            "private": False,
        },
    }


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    """Reset lazy settings around endpoint tests."""
    settings.reset()


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Import backend.main with baseline environment variables present."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("CHAT_API_KEY", "test-chat")
    monkeypatch.setenv("CHATWOOT_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("CHATWOOT_API_URL", "https://chatwoot.test")
    monkeypatch.setenv("CHATWOOT_AGENT_BOT_TOKEN", "test-token")
    monkeypatch.setenv("CHATWOOT_ACCOUNT_ID", "1")
    monkeypatch.setenv("CHATWOOT_INBOX_ID", "7")
    settings.reset()

    import backend.main as main

    return main


@pytest.fixture
def client(main_module: Any) -> TestClient:
    """Return a TestClient for the FastAPI app."""
    return TestClient(main_module.app)


def test_chatwoot_webhook_disabled_does_not_dispatch(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled integration should return 503 before parsing or dispatching."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "false")
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )

    response = client.post("/webhook/chatwoot", content=b"not-json")

    assert response.status_code == 503
    assert response.json() == {"detail": "Chatwoot integration disabled"}
    handler.handle_event.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_valid_signature_dispatches_handler(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid signed payloads should dispatch to ChatwootHandler."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    payload = _valid_payload()
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    handler.handle_event.assert_awaited_once()
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_accepts_real_timestamped_signature(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real Chatwoot AgentBot signatures include timestamp in HMAC input."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    payload = _valid_payload()
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_chatwoot_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    handler.handle_event.assert_awaited_once()
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_accepts_unknown_event_without_account(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real Chatwoot lifecycle payloads may omit account data."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    payload = {
        "event": "conversation_opened",
        "additional_attributes": {},
        "messages": [],
    }
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_chatwoot_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    handler.handle_event.assert_awaited_once()
    parsed_payload = handler.handle_event.await_args.args[0]
    assert parsed_payload.event == "conversation_opened"
    assert parsed_payload.account == {}
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_invalid_signature_returns_401(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid HMAC signatures should be rejected."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )

    response = client.post(
        "/webhook/chatwoot",
        json=_valid_payload(),
        headers={"X-Chatwoot-Signature": "bad"},
    )

    assert response.status_code == 401
    handler.handle_event.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_missing_secret_returns_401(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled webhooks without a secret should fail closed."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    monkeypatch.delenv("CHATWOOT_WEBHOOK_SECRET", raising=False)
    settings.reset()
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    body = json.dumps(_valid_payload()).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 401
    handler.handle_event.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_chatwoot_webhook_empty_body_valid_signature_returns_422(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty signed bodies should pass auth and fail payload validation."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    body = b""

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 422


def test_chatwoot_webhook_empty_body_invalid_signature_returns_401(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty bodies with invalid signatures should fail auth."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()

    response = client.post(
        "/webhook/chatwoot",
        content=b"",
        headers={"X-Chatwoot-Signature": "invalid"},
    )

    assert response.status_code == 401


def test_chatwoot_webhook_invalid_payload_returns_422(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema-invalid signed payloads should return 422."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    body = b'{"event":"message_created"}'

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 422


def test_chatwoot_webhook_handler_exception_returns_500(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handler failures should return 500 so Chatwoot retries."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    handler = AsyncMock()
    handler.handle_event.side_effect = RuntimeError("boom")
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    body = json.dumps(_valid_payload()).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 500
    main_module.app.dependency_overrides.clear()


def test_chatwoot_health_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disabled integration should report disabled status."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "false")
    settings.reset()

    response = client.get("/health/chatwoot")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert response.json()["chatwoot_enabled"] is False


def test_chatwoot_health_enabled_redis_healthy(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled integration with healthy Redis and config should be healthy."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    redis_cache = AsyncMock()
    redis_cache.health_check.return_value = True
    main_module.app.dependency_overrides[main_module.get_redis_cache] = lambda: (
        redis_cache
    )

    response = client.get("/health/chatwoot")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "chatwoot_enabled": True,
        "redis": "healthy",
        "chatwoot_api": "configured",
    }
    main_module.app.dependency_overrides.clear()


def test_chatwoot_health_enabled_redis_unavailable(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis failures should degrade but not fail health."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    settings.reset()
    redis_cache = AsyncMock()
    redis_cache.health_check.return_value = False
    main_module.app.dependency_overrides[main_module.get_redis_cache] = lambda: (
        redis_cache
    )

    response = client.get("/health/chatwoot")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["redis"] == "unavailable"
    main_module.app.dependency_overrides.clear()


def test_chatwoot_health_missing_chatwoot_config(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Chatwoot API config should report degraded/not_configured."""
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
    monkeypatch.delenv("CHATWOOT_API_URL", raising=False)
    settings.reset()
    redis_cache = AsyncMock()
    redis_cache.health_check.return_value = True
    main_module.app.dependency_overrides[main_module.get_redis_cache] = lambda: (
        redis_cache
    )

    response = client.get("/health/chatwoot")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["chatwoot_api"] == "not_configured"
    main_module.app.dependency_overrides.clear()


def test_get_redis_cache_uses_unconfigured_namespace_when_account_missing(
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Chatwoot account IDs must not share account 1 cache keys."""
    monkeypatch.delenv("CHATWOOT_ACCOUNT_ID", raising=False)
    settings.reset()

    redis_cache = main_module.get_redis_cache()

    assert redis_cache._build_key("scope", "id") == ("chatwoot:unconfigured:scope:id")
