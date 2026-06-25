"""Repository integration tests for Chatwoot Lambda-safe state."""

from unittest.mock import AsyncMock

import pytest

from backend.app.chatwoot_handler import ChatwootHandler
from backend.app.dynamodb_state_repository import DynamoDBStateRepository
from backend.app.message_buffer import ChatwootMessageBuffer
from backend.app.schemas import (
    ChatwootConversation,
    ChatwootSender,
    ConversationCreatedPayload,
)
from backend.app.session import SessionManager
from backend.tests.test_state_repository import FakeDynamoDBTable


class DummyConfigProvider:
    """Minimal config provider for repository integration tests."""

    def get_channel_profile(self, inbox_id: str) -> object:
        """Return deterministic buffer settings."""
        del inbox_id
        profile = type("Profile", (), {})()
        profile.buffer_window_seconds = 5
        return profile


@pytest.fixture
def repository() -> DynamoDBStateRepository:
    """Return a repository backed by an isolated fake table."""
    return DynamoDBStateRepository(table=FakeDynamoDBTable(), key_prefix="test")


@pytest.mark.asyncio
async def test_session_mapping_and_buffer_share_repository_without_collisions(
    repository: DynamoDBStateRepository,
) -> None:
    """Session metadata and Chatwoot buffers coexist in the same table."""
    session_manager = SessionManager(state_repository=repository)
    message_buffer = ChatwootMessageBuffer(repository)

    session_id = await session_manager.get_or_create_session_for_conversation(
        "42", account_id=1
    )
    await message_buffer.add_message("42", "Hola", window_seconds=5)

    assert await session_manager.get_session_id("42") == session_id
    assert repository.get_chatwoot_conversation_id(session_id) == "42"
    assert repository.get_buffer_state("chatwoot:42").messages[0].message == "Hola"


@pytest.mark.asyncio
async def test_conversation_created_handler_mapping_is_idempotent(
    repository: DynamoDBStateRepository,
) -> None:
    """Repeated conversation_created webhooks keep one session mapping."""
    session_manager = SessionManager(state_repository=repository)
    handler = ChatwootHandler(
        chatwoot_client=AsyncMock(),
        config_provider=DummyConfigProvider(),
        state_repository=repository,
        session_manager=session_manager,
    )
    payload = ConversationCreatedPayload(
        event="conversation_created",
        account={"id": 1},
        conversation=ChatwootConversation(
            id=314, status="open", inbox_id=7, contact_id=9
        ),
        sender=ChatwootSender(id=9, type="contact"),
    )

    await handler._handle_conversation_created(payload)
    first_session = await session_manager.get_session_id("314")
    await handler._handle_conversation_created(payload)
    second_session = await session_manager.get_session_id("314")

    assert first_session is not None
    assert second_session == first_session


@pytest.mark.asyncio
async def test_cache_miss_hydrates_history_from_chatwoot_source_of_truth(
    repository: DynamoDBStateRepository,
) -> None:
    """History cache misses can hydrate from Chatwoot once."""
    chatwoot_client = AsyncMock()
    chatwoot_client.fetch_messages.return_value = {
        "payload": [
            {"content": "Necesito paneles", "message_type": "incoming"},
            {"content": "Te ayudo con paneles", "message_type": "outgoing"},
        ]
    }
    session_manager = SessionManager(
        state_repository=repository,
        chatwoot_client=chatwoot_client,
    )
    await session_manager.map_conversation("session-1", "42")

    first_history = await session_manager.get_history_async("session-1")
    second_history = await session_manager.get_history_async("session-1")

    assert first_history[0].question == "Necesito paneles"
    assert second_history[0].answer == "Te ayudo con paneles"
    chatwoot_client.fetch_messages.assert_awaited_once_with(42, limit=20)


@pytest.mark.asyncio
async def test_chatwoot_buffer_flushes_once_from_repository(
    repository: DynamoDBStateRepository,
) -> None:
    """Flushing a Chatwoot repository buffer clears stored messages."""
    message_buffer = ChatwootMessageBuffer(repository)
    await message_buffer.add_message("42", "Uno", window_seconds=5)
    await message_buffer.add_message("42", "Dos", window_seconds=5)

    assert await message_buffer.flush("42") == "Uno\nDos"
    assert await message_buffer.flush("42") is None
