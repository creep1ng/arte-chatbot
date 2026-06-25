"""Tests for repository-backed Chatwoot message buffering."""

import pytest

from backend.app.dynamodb_state_repository import DynamoDBStateRepository
from backend.app.message_buffer import BufferResult, ChatwootMessageBuffer
from backend.tests.test_state_repository import FakeDynamoDBTable


@pytest.fixture
def repository() -> DynamoDBStateRepository:
    """Return an isolated fake DynamoDB repository."""
    return DynamoDBStateRepository(table=FakeDynamoDBTable())


def test_buffer_result_defaults() -> None:
    """BufferResult remains available for legacy callers/tests."""
    result = BufferResult(is_buffering=True)
    assert result.is_buffering is True
    assert result.joined_message is None


@pytest.mark.asyncio
async def test_add_message_persists_repository_state(
    repository: DynamoDBStateRepository,
) -> None:
    """Chatwoot messages are persisted via the shared repository."""
    message_buffer = ChatwootMessageBuffer(repository)

    state = await message_buffer.add_message("42", "hola", window_seconds=5)

    assert state.conversation_id == "42"
    assert state.messages == ["hola"]
    stored = repository.get_buffer_state("chatwoot:42")
    assert [message.message for message in stored.messages] == ["hola"]


@pytest.mark.asyncio
async def test_flush_returns_joined_messages_and_clears_repository(
    repository: DynamoDBStateRepository,
) -> None:
    """Flushing returns the joined text and clears durable buffer messages."""
    message_buffer = ChatwootMessageBuffer(repository)
    await message_buffer.add_message("42", "hello", window_seconds=5)
    await message_buffer.add_message("42", "world", window_seconds=5)

    assert await message_buffer.flush("42") == "hello\nworld"
    assert repository.get_buffer_state("chatwoot:42").messages == []


@pytest.mark.asyncio
async def test_flush_and_cancel_uses_same_durable_flush(
    repository: DynamoDBStateRepository,
) -> None:
    """Human-agent intervention flushes the durable conversation buffer."""
    message_buffer = ChatwootMessageBuffer(repository)
    await message_buffer.add_message("42", "hello", window_seconds=5)

    assert await message_buffer.flush_and_cancel("42") == "hello"
    assert await message_buffer.flush_and_cancel("42") is None


@pytest.mark.asyncio
async def test_local_fallback_is_instance_scoped() -> None:
    """Local fallback supports tests/dev without production state dependencies."""
    first = ChatwootMessageBuffer()
    second = ChatwootMessageBuffer()

    await first.add_message("42", "Cuenta 1", window_seconds=5)
    await second.add_message("42", "Sin configurar", window_seconds=5)

    assert await first.flush("42") == "Cuenta 1"
    assert await second.flush("42") == "Sin configurar"
