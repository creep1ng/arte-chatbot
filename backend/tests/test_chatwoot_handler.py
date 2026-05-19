"""Tests for ChatwootHandler webhook event dispatcher.

Validates event routing, idempotency deduplication, and structured
logging for all supported webhook types.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.chatwoot_handler import ChatwootHandler
from backend.app.schemas import (
    ChatwootConversation,
    ChatwootMessage,
    ChatwootSender,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    MessageCreatedPayload,
)


@pytest.fixture
def chatwoot_client() -> Any:
    client = AsyncMock()
    client.send_typing_indicator.return_value = True
    return client


@pytest.fixture
def redis_cache() -> Any:
    cache = AsyncMock()
    cache._prefix = "chatwoot"
    cache._account_id = 1
    cache._build_key = lambda scope, entity_id, field=None: (
        f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
    )
    return cache


@pytest.fixture
def config_provider() -> Any:
    provider = MagicMock()
    provider.is_chatwoot_enabled.return_value = True
    profile = MagicMock()
    profile.buffer_window_seconds = 7
    provider.get_channel_profile.return_value = profile
    return provider


@pytest.fixture
def message_buffer() -> Any:
    buffer = AsyncMock()
    return buffer


@pytest.fixture
def session_manager() -> Any:
    manager = AsyncMock()
    manager.get_or_create_session_for_conversation.return_value = "session-42"
    return manager


@pytest.fixture
def escalation_handler() -> Any:
    return AsyncMock()


@pytest.fixture
def handler(
    chatwoot_client: Any,
    redis_cache: Any,
    config_provider: Any,
    message_buffer: Any,
    session_manager: Any,
    escalation_handler: Any,
) -> ChatwootHandler:
    return ChatwootHandler(
        chatwoot_client=chatwoot_client,
        redis_cache=redis_cache,
        config_provider=config_provider,
        message_buffer=message_buffer,
        session_manager=session_manager,
        escalation_handler=escalation_handler,
    )


def _message_payload(
    sender_type: str = "contact",
    message_id: int = 101,
    content: str = "hello",
) -> MessageCreatedPayload:
    return MessageCreatedPayload(
        event="message_created",
        account={"id": 1},
        conversation=ChatwootConversation(
            id=42, status="open", inbox_id=1, contact_id=5
        ),
        sender=ChatwootSender(id=7, type=sender_type, name="Test"),
        message=ChatwootMessage(id=message_id, content=content),
    )


class TestIdempotency:
    """Duplicate message detection via Redis set."""

    @pytest.mark.asyncio
    async def test_is_duplicate_true(
        self, handler: ChatwootHandler, redis_cache: Any
    ) -> None:
        redis_cache.sismember.return_value = True
        assert await handler._is_duplicate(101) is True
        redis_cache.sismember.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_duplicate_false(
        self, handler: ChatwootHandler, redis_cache: Any
    ) -> None:
        redis_cache.sismember.return_value = False
        assert await handler._is_duplicate(101) is False

    @pytest.mark.asyncio
    async def test_mark_processed(
        self, handler: ChatwootHandler, redis_cache: Any
    ) -> None:
        redis_cache.sadd.return_value = True
        assert await handler._mark_processed(101) is True
        redis_cache.sadd.assert_awaited_once()


class TestHandleMessageCreated:
    """Dispatch of 'message_created' events."""

    @pytest.mark.asyncio
    async def test_contact_message_creates_session_and_adds_buffer(
        self,
        handler: ChatwootHandler,
        session_manager: Any,
        message_buffer: Any,
    ) -> None:
        payload = _message_payload(sender_type="contact", content="hola")

        await handler._handle_message_created(payload)

        session_manager.get_or_create_session_for_conversation.assert_awaited_once_with(
            "42", account_id=1
        )
        message_buffer.add_message.assert_awaited_once_with("42", "hola", 7)

    @pytest.mark.asyncio
    async def test_contact_message_sends_typing_indicator(
        self, handler: ChatwootHandler, chatwoot_client: Any
    ) -> None:
        payload = _message_payload(sender_type="contact")

        await handler._handle_message_created(payload)

        chatwoot_client.send_typing_indicator.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_human_message_flushes_and_cancels(
        self, handler: ChatwootHandler, message_buffer: Any
    ) -> None:
        payload = _message_payload(sender_type="user")

        await handler._handle_message_created(payload)

        message_buffer.flush_and_cancel.assert_awaited_once_with("42")

    @pytest.mark.asyncio
    async def test_duplicate_message_ignored_before_buffer(
        self, handler: ChatwootHandler, message_buffer: Any
    ) -> None:
        payload = _message_payload(sender_type="contact")
        handler._is_duplicate = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await handler.handle_event(payload)

        message_buffer.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_contact_message_logs_received(
        self, handler: ChatwootHandler, caplog: Any
    ) -> None:
        payload = _message_payload(sender_type="contact")
        with caplog.at_level("INFO"):
            await handler._handle_message_created(payload)
        assert "user message received" in caplog.text

    @pytest.mark.asyncio
    async def test_user_message_logs_agent_detected(
        self, handler: ChatwootHandler, caplog: Any
    ) -> None:
        payload = _message_payload(sender_type="user")
        with caplog.at_level("INFO"):
            await handler._handle_message_created(payload)
        assert "human agent message detected" in caplog.text

    @pytest.mark.asyncio
    async def test_extracts_conversation_id(
        self, handler: ChatwootHandler, caplog: Any
    ) -> None:
        payload = _message_payload(sender_type="contact")
        with caplog.at_level("INFO"):
            await handler._handle_message_created(payload)
        assert "conversation_id=42" in caplog.text


class TestHandleConversationCreated:
    """Dispatch of 'conversation_created' events."""

    @pytest.mark.asyncio
    async def test_logs_event(self, handler: ChatwootHandler, caplog: Any) -> None:
        payload = ConversationCreatedPayload(
            event="conversation_created",
            account={"id": 1},
            conversation=ChatwootConversation(
                id=99, status="open", inbox_id=1, contact_id=5
            ),
            sender=ChatwootSender(id=7, type="contact"),
        )
        with caplog.at_level("INFO"):
            await handler._handle_conversation_created(payload)
        assert "conversation_created" in caplog.text
        assert "conversation_id=99" in caplog.text


class TestHandleConversationStatusChanged:
    """Dispatch of 'conversation_status_changed' events."""

    @pytest.mark.asyncio
    async def test_logs_event(self, handler: ChatwootHandler, caplog: Any) -> None:
        payload = ConversationStatusChangedPayload(
            event="conversation_status_changed",
            account={"id": 1},
            conversation=ChatwootConversation(
                id=77, status="resolved", inbox_id=1, contact_id=5
            ),
            sender=ChatwootSender(id=7, type="user"),
            status="resolved",
        )
        with caplog.at_level("INFO"):
            await handler._handle_conversation_status_changed(payload)
        assert "conversation_status_changed" in caplog.text
        assert "conversation_id=77" in caplog.text


class TestHandleEvent:
    """Main dispatcher routes to the correct handler."""

    @pytest.mark.asyncio
    async def test_routes_message_created(self, handler: ChatwootHandler) -> None:
        payload = _message_payload()
        handler._is_duplicate = AsyncMock(return_value=False)  # type: ignore[method-assign]
        handler._handle_message_created = AsyncMock()  # type: ignore[method-assign]
        handler._mark_processed = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await handler.handle_event(payload)
        handler._handle_message_created.assert_awaited_once_with(payload)
        handler._mark_processed.assert_awaited_once_with(101)

    @pytest.mark.asyncio
    async def test_routes_conversation_created(self, handler: ChatwootHandler) -> None:
        payload = ConversationCreatedPayload(
            event="conversation_created",
            account={"id": 1},
            conversation=ChatwootConversation(
                id=99, status="open", inbox_id=1, contact_id=5
            ),
            sender=ChatwootSender(id=7, type="contact"),
        )
        handler._handle_conversation_created = AsyncMock()  # type: ignore[method-assign]
        handler._mark_processed = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await handler.handle_event(payload)
        handler._handle_conversation_created.assert_awaited_once_with(payload)

    @pytest.mark.asyncio
    async def test_routes_status_changed(self, handler: ChatwootHandler) -> None:
        payload = ConversationStatusChangedPayload(
            event="conversation_status_changed",
            account={"id": 1},
            conversation=ChatwootConversation(
                id=77, status="resolved", inbox_id=1, contact_id=5
            ),
            sender=ChatwootSender(id=7, type="user"),
            status="resolved",
        )
        handler._handle_conversation_status_changed = AsyncMock()  # type: ignore[method-assign]
        handler._mark_processed = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await handler.handle_event(payload)
        handler._handle_conversation_status_changed.assert_awaited_once_with(payload)

    @pytest.mark.asyncio
    async def test_skips_duplicate_message(self, handler: ChatwootHandler) -> None:
        payload = _message_payload()
        handler._is_duplicate = AsyncMock(return_value=True)  # type: ignore[method-assign]
        handler._handle_message_created = AsyncMock()  # type: ignore[method-assign]
        await handler.handle_event(payload)
        handler._handle_message_created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_event_logs_warning(
        self, handler: ChatwootHandler, caplog: Any
    ) -> None:
        payload = MessageCreatedPayload(
            event="unknown_event",
            account={"id": 1},
            conversation=ChatwootConversation(
                id=42, status="open", inbox_id=1, contact_id=5
            ),
            sender=ChatwootSender(id=7, type="contact"),
            message=ChatwootMessage(id=101, content="hi"),
        )
        with caplog.at_level("WARNING"):
            await handler.handle_event(payload)
        assert "unknown_event" in caplog.text
