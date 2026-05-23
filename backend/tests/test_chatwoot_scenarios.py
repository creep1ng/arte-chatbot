"""Mocked scenario tests for Chatwoot webhook flows.

These tests exercise the FastAPI endpoint plus real ``ChatwootHandler``
dispatching with mocked collaborators. They intentionally avoid real Redis and
Chatwoot network calls.
"""

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.chatwoot_handler import ChatwootHandler
from backend.app.config import settings
from backend.app.escalation_handler import EscalationHandler


class InMemoryRedisCache:
    """Small async RedisCache test double safe across TestClient event loops."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}
        self._values: dict[str, str] = {}

    def _build_key(self, scope: str, entity_id: str, field: str | None = None) -> str:
        """Build keys using the production Chatwoot namespace shape."""
        key = f"chatwoot:1:{scope}:{entity_id}"
        if field is not None:
            key = f"{key}:{field}"
        return key

    async def sismember(self, key: str, member: str) -> bool:
        """Return whether a set member exists."""
        return member in self._sets.get(key, set())

    async def sadd(self, key: str, member: str) -> bool:
        """Add a set member."""
        self._sets.setdefault(key, set()).add(member)
        return True

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Store a string value."""
        del ttl
        self._values[key] = value
        return True


class DummyProfile:
    """Minimal channel profile used by handler scenario tests."""

    buffer_window_seconds = 5


class DummyConfigProvider:
    """Config provider stub for scenario tests."""

    def get(self, key: str) -> Any:
        """Return unset config values."""
        return None

    def get_channel_profile(self, inbox_id: str) -> DummyProfile:
        """Return the same deterministic profile for every inbox."""
        del inbox_id
        return DummyProfile()

    def get_label(self, name: str) -> str:
        """Resolve escalation labels deterministically."""
        labels = {
            "escalated": "escalated",
            "quote": "quote",
            "technical": "technical",
            "order": "order",
        }
        return labels.get(name, name)

    def get_handoff_target(self) -> int:
        """Return a configured handoff team for scenario coverage."""
        return 55

    def is_chatwoot_enabled(self) -> bool:
        """Return enabled for tests that construct this provider."""
        return True


def _signed_headers(payload: bytes, secret: str = "test-secret") -> dict[str, str]:
    """Build Chatwoot signature headers for *payload*."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {"X-Chatwoot-Signature": digest}


def _message_payload(
    *, message_id: int = 101, sender_type: str = "contact"
) -> dict[str, Any]:
    """Return a valid Chatwoot ``message_created`` webhook payload."""
    return {
        "event": "message_created",
        "account": {"id": 1},
        "conversation": {
            "id": 42,
            "status": "open",
            "inbox_id": 7,
            "contact_id": 9,
        },
        "sender": {"id": 11, "type": sender_type, "name": "Cliente"},
        "message": {
            "id": message_id,
            "content": "Hola",
            "content_type": "text",
            "private": False,
        },
    }


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    """Reset lazy settings around scenario tests."""
    settings.reset()


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Import ``backend.main`` with deterministic test env vars."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("CHAT_API_KEY", "test-chat")
    monkeypatch.setenv("CHATWOOT_ENABLED", "true")
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


@pytest.fixture
def redis_cache() -> InMemoryRedisCache:
    """Return an in-memory RedisCache-compatible test double."""
    return InMemoryRedisCache()


@pytest.fixture
def handler_dependencies() -> dict[str, Any]:
    """Return mocked dependencies used to build a real handler."""
    return {
        "client": AsyncMock(),
        "buffer": AsyncMock(),
        "sessions": AsyncMock(),
        "config": DummyConfigProvider(),
    }


def _override_handler(
    main_module: Any,
    redis_cache: InMemoryRedisCache,
    dependencies: dict[str, Any],
) -> ChatwootHandler:
    """Install a FastAPI override returning a real ChatwootHandler."""
    handler = ChatwootHandler(
        chatwoot_client=dependencies["client"],
        redis_cache=redis_cache,
        config_provider=dependencies["config"],
        message_buffer=dependencies["buffer"],
        session_manager=dependencies["sessions"],
    )
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    return handler


def test_valid_contact_message_dispatches_through_handler(
    client: TestClient,
    main_module: Any,
    redis_cache: InMemoryRedisCache,
    handler_dependencies: dict[str, Any],
) -> None:
    """Contact messages should traverse endpoint, handler, and dependencies."""
    _override_handler(main_module, redis_cache, handler_dependencies)
    body = json.dumps(_message_payload()).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    handler_dependencies[
        "sessions"
    ].get_or_create_session_for_conversation.assert_awaited_once_with(
        "42", account_id=1
    )
    handler_dependencies["buffer"].add_message.assert_awaited_once_with("42", "Hola", 5)
    handler_dependencies["client"].send_typing_indicator.assert_awaited_once_with(42)
    main_module.app.dependency_overrides.clear()


def test_human_agent_message_cancels_buffer_without_bot_reply(
    client: TestClient,
    main_module: Any,
    redis_cache: InMemoryRedisCache,
    handler_dependencies: dict[str, Any],
) -> None:
    """Human-agent messages should cancel pending bot work and not reply."""
    _override_handler(main_module, redis_cache, handler_dependencies)
    body = json.dumps(_message_payload(message_id=102, sender_type="user")).encode()

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    handler_dependencies["buffer"].flush_and_cancel.assert_awaited_once_with("42")
    handler_dependencies["buffer"].add_message.assert_not_awaited()
    handler_dependencies["client"].send_typing_indicator.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_duplicate_webhook_is_accepted_without_second_processing(
    client: TestClient,
    main_module: Any,
    redis_cache: InMemoryRedisCache,
    handler_dependencies: dict[str, Any],
) -> None:
    """Duplicate messages should return accepted and skip handler side effects."""
    _override_handler(main_module, redis_cache, handler_dependencies)
    body = json.dumps(_message_payload(message_id=103)).encode()
    headers = _signed_headers(body)

    first = client.post("/webhook/chatwoot", content=body, headers=headers)
    second = client.post("/webhook/chatwoot", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    handler_dependencies["buffer"].add_message.assert_awaited_once()
    handler_dependencies[
        "sessions"
    ].get_or_create_session_for_conversation.assert_awaited_once()
    main_module.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_escalation_calls_chatwoot_actions_in_expected_order() -> None:
    """Escalation should label, open, assign, then notify the user."""
    calls: list[str] = []

    async def add_label(conversation_id: int, label: str) -> None:
        calls.append(f"label:{conversation_id}:{label}")

    async def toggle_status(conversation_id: int, status: str) -> None:
        calls.append(f"status:{conversation_id}:{status}")

    async def assign_conversation(conversation_id: int, team_id: int) -> None:
        calls.append(f"assign:{conversation_id}:{team_id}")

    async def send_message(conversation_id: int, message: str) -> None:
        del message
        calls.append(f"message:{conversation_id}")

    chatwoot_client = AsyncMock()
    chatwoot_client.add_label.side_effect = add_label
    chatwoot_client.toggle_status.side_effect = toggle_status
    chatwoot_client.assign_conversation.side_effect = assign_conversation
    chatwoot_client.send_message.side_effect = send_message
    handler = EscalationHandler(
        chatwoot_client=chatwoot_client,
        config_provider=DummyConfigProvider(),
    )

    result = await handler.escalate_to_human(
        42,
        reason="quote requested",
        intent_type="escalate_quote",
    )

    assert result is True
    assert calls == [
        "label:42:escalated",
        "label:42:quote",
        "status:42:open",
        "assign:42:55",
        "message:42",
    ]


def test_invalid_signature_returns_401(
    client: TestClient,
    main_module: Any,
) -> None:
    """Invalid signatures should reject requests before dispatch."""
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )

    response = client.post(
        "/webhook/chatwoot",
        json=_message_payload(message_id=104),
        headers={"X-Chatwoot-Signature": "garbage"},
    )

    assert response.status_code == 401
    handler.handle_event.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_invalid_payload_returns_422_before_dispatch(
    client: TestClient,
    main_module: Any,
) -> None:
    """Schema-invalid signed payloads should return 422."""
    handler = AsyncMock()
    main_module.app.dependency_overrides[main_module.get_chatwoot_handler] = lambda: (
        handler
    )
    body = b'{"event":"message_created"}'

    response = client.post(
        "/webhook/chatwoot",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 422
    handler.handle_event.assert_not_awaited()
    main_module.app.dependency_overrides.clear()


def test_disabled_chatwoot_returns_503_before_parsing_or_dispatch(
    client: TestClient,
    main_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled integration should reject even malformed bodies early."""
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
