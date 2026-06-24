"""Backend-wide pytest isolation for local environment dependent settings."""

import os
from collections.abc import Iterator

import pytest


_BACKEND_TEST_ENV = {
    "ARTE_CHATBOT_DISABLE_DOTENV": "1",
    "OPENAI_API_KEY": "test-openai-key",
    "CHAT_API_KEY": "test-chat-key",
    "AWS_BUCKET_NAME": "test-bucket",
    "LOG_LEVEL": "INFO",
    "STATE_BACKEND": "memory",
    "MULTI_MESSAGE_BUFFER_ENABLED": "false",
    "BUFFER_WINDOW_SECONDS": "5",
    "SPLIT_MESSAGES_ENABLED": "false",
    "WHATSAPP_FORMATTER_ENABLED": "false",
    "GREETING_ENABLED": "false",
    "OPENAI_API_KEY_SECRET_REF": "",
    "CHAT_API_KEY_SECRET_REF": "",
}

for key, value in _BACKEND_TEST_ENV.items():
    os.environ[key] = value


def _reset_runtime_state() -> None:
    """Reset process-local app state that can leak across backend tests."""
    from backend.app import message_buffer
    from backend.app.config import settings
    from backend.app.rate_limit import rate_limiter
    from backend.app.session import session_manager

    settings.reset()
    rate_limiter.reset()
    rate_limiter.set_state_repository(None)
    session_manager.set_state_repository(None)

    with session_manager._lock:
        session_manager.sessions.clear()
        session_manager.profiles.clear()
        session_manager.token_totals.clear()
        session_manager.session_owners.clear()

    message_buffer.set_state_repository(None)
    message_buffer._buffer.clear()
    message_buffer._pending_results.clear()
    message_buffer._pending_chat_responses.clear()
    message_buffer._processing_sessions.clear()

    for task in list(message_buffer._buffer_tasks.values()):
        if not task.done():
            task.cancel()
    message_buffer._buffer_tasks.clear()


@pytest.fixture(autouse=True)
def _isolate_backend_runtime_state() -> Iterator[None]:
    """Keep backend tests deterministic regardless of local `.env` or prior tests."""
    _reset_runtime_state()
    yield
    _reset_runtime_state()
