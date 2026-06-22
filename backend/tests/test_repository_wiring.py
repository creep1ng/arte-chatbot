"""Tests for repository-backed runtime wiring used by Lambda."""

import pytest

from backend.app.dynamodb_state_repository import DynamoDBStateRepository
from backend.app.rate_limit import InMemoryRateLimiter
from backend.app.session import SessionManager
from backend.tests.test_state_repository import FakeDynamoDBTable


def test_session_manager_delegates_state_to_repository() -> None:
    """Session state is restored from the configured repository."""
    repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
    manager = SessionManager(state_repository=repository)

    manager.bind_session("repo-session", "principal-a")
    manager.add_turn("repo-session", "Pregunta", "Respuesta", ["doc.pdf"])
    manager.add_token_usage("repo-session", 10, 5, 15)
    manager.set_user_profile("repo-session", "intermedio")

    history = manager.get_history("repo-session")

    assert manager.has_session_owner("repo-session") is True
    assert manager.is_session_owner("repo-session", "principal-a") is True
    assert history[0].question == "Pregunta"
    assert history[0].source_documents == ["doc.pdf"]
    assert manager.get_token_totals("repo-session").total_tokens == 15
    assert manager.get_user_profile("repo-session") == "intermedio"


def test_rate_limiter_delegates_to_repository() -> None:
    """Rate-limit checks use shared repository counters when configured."""
    repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
    limiter = InMemoryRateLimiter()
    limiter.set_state_repository(repository)

    first = limiter.check("principal-a", limit=1, window_seconds=60)
    second = limiter.check("principal-a", limit=1, window_seconds=60)

    assert first.allowed is True
    assert second.allowed is False
    assert second.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_message_buffer_delegates_polling_state_to_repository() -> None:
    """Buffer and pending response state survive module-level memory resets."""
    from backend.app import message_buffer

    repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
    message_buffer.set_state_repository(repository)
    try:
        await message_buffer.add_to_buffer("repo-buffer", "Hola")
        await message_buffer.add_to_buffer("repo-buffer", "paneles")

        assert message_buffer.get_buffer_count("repo-buffer") == 2
        assert await message_buffer.flush_buffer("repo-buffer") == "Hola\npaneles"

        message_buffer.set_pending_chat_response("repo-buffer", '{"response":"ok"}')

        message_buffer._buffer.clear()
        message_buffer._pending_chat_responses.clear()

        assert message_buffer.pop_pending_chat_response("repo-buffer") == (
            '{"response":"ok"}'
        )
        assert message_buffer.pop_pending_chat_response("repo-buffer") is None
    finally:
        message_buffer.set_state_repository(None)
