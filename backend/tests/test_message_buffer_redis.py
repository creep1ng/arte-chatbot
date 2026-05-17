"""Tests for Redis-backed MessageBuffer.

Uses fakeredis to exercise all buffer operations without a real Redis server.
"""

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis import FakeAsyncRedis

from backend.app.message_buffer import BufferResult, MessageBuffer
from backend.app.redis_cache import RedisCache


class MockConfigProvider:
    """Minimal config provider for tests."""

    def __init__(self, window_seconds: int = 5, max_messages: int = 5) -> None:
        self._window = window_seconds
        self._max = max_messages

    def get(self, key: str) -> Any:
        if key == "buffer_window_seconds":
            return self._window
        if key == "buffer_max_messages":
            return self._max
        return None


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def redis_cache(fake_redis: FakeAsyncRedis) -> RedisCache:
    with patch("backend.app.redis_cache.redis.asyncio.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake_redis
        return RedisCache(redis_url="redis://localhost:6379/0")


@pytest.fixture
def config_provider() -> MockConfigProvider:
    return MockConfigProvider(window_seconds=5, max_messages=5)


@pytest.fixture
def message_buffer(
    redis_cache: RedisCache, config_provider: MockConfigProvider
) -> MessageBuffer:
    return MessageBuffer(redis_cache=redis_cache, config_provider=config_provider)


class TestBufferResultModel:
    """BufferResult Pydantic model must behave correctly."""

    def test_buffer_result_defaults(self) -> None:
        result = BufferResult(is_buffering=True)
        assert result.is_buffering is True
        assert result.joined_message is None

    def test_buffer_result_with_message(self) -> None:
        result = BufferResult(is_buffering=False, joined_message="hello\nworld")
        assert result.is_buffering is False
        assert result.joined_message == "hello\nworld"


class TestAddToBuffer:
    """Accumulating messages in the Redis-backed buffer."""

    @pytest.mark.asyncio
    async def test_add_creates_new_buffer(self, message_buffer: MessageBuffer) -> None:
        result = await message_buffer.add("session-1", "hello")
        assert result.is_buffering is True
        assert result.joined_message is None

    @pytest.mark.asyncio
    async def test_add_appends_message(self, message_buffer: MessageBuffer) -> None:
        await message_buffer.add("session-1", "hello")
        await message_buffer.add("session-1", "world")
        count = await message_buffer.get_count("session-1")
        assert count == 2

    @pytest.mark.asyncio
    async def test_add_returns_joined_on_count_limit(
        self, message_buffer: MessageBuffer
    ) -> None:
        # max_messages = 5 in fixture
        await message_buffer.add("session-1", "a")
        await message_buffer.add("session-1", "b")
        await message_buffer.add("session-1", "c")
        await message_buffer.add("session-1", "d")
        result = await message_buffer.add("session-1", "e")
        assert result.is_buffering is False
        assert result.joined_message == "a\nb\nc\nd\ne"

    @pytest.mark.asyncio
    async def test_add_returns_joined_on_expired_deadline(
        self, message_buffer: MessageBuffer
    ) -> None:
        # Use a tiny window so deadline expires immediately
        provider = MockConfigProvider(window_seconds=0, max_messages=5)
        buf = MessageBuffer(redis_cache=message_buffer._redis, config_provider=provider)
        await buf.add("session-1", "hello")
        # Small sleep to ensure deadline passed
        await asyncio.sleep(0.05)
        result = await buf.add("session-1", "world")
        assert result.is_buffering is False
        assert result.joined_message == "hello\nworld"

    @pytest.mark.asyncio
    async def test_add_on_flushing_buffer_returns_immediately(
        self, message_buffer: MessageBuffer
    ) -> None:
        # Simulate flush_and_cancel setting is_flushing=true
        key = message_buffer._buffer_key("session-1")
        await message_buffer._redis.set(
            key,
            json.dumps(
                {"messages": ["a"], "deadline": time.time() + 60, "is_flushing": True}
            ),
        )
        result = await message_buffer.add("session-1", "b")
        assert result.is_buffering is True
        assert result.joined_message is None


class TestFlush:
    """Flushing buffered messages."""

    @pytest.mark.asyncio
    async def test_flush_returns_joined_messages(
        self, message_buffer: MessageBuffer
    ) -> None:
        await message_buffer.add("session-1", "hello")
        await message_buffer.add("session-1", "world")
        joined = await message_buffer.flush("session-1")
        assert joined == "hello\nworld"

    @pytest.mark.asyncio
    async def test_flush_deletes_redis_key(self, message_buffer: MessageBuffer) -> None:
        await message_buffer.add("session-1", "hello")
        await message_buffer.flush("session-1")
        count = await message_buffer.get_count("session-1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_returns_none(
        self, message_buffer: MessageBuffer
    ) -> None:
        joined = await message_buffer.flush("session-1")
        assert joined is None


class TestFlushAndCancel:
    """Race-condition guard for human-agent intervention."""

    @pytest.mark.asyncio
    async def test_flush_and_cancel_acquires_lock(
        self, message_buffer: MessageBuffer
    ) -> None:
        await message_buffer.add("session-1", "hello")
        joined = await message_buffer.flush_and_cancel("session-1")
        assert joined == "hello"

    @pytest.mark.asyncio
    async def test_flush_and_cancel_sets_is_flushing(
        self, message_buffer: MessageBuffer
    ) -> None:
        await message_buffer.add("session-1", "hello")
        await message_buffer.flush_and_cancel("session-1")
        # After flush, key should be deleted
        count = await message_buffer.get_count("session-1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_and_cancel_empty_buffer(
        self, message_buffer: MessageBuffer
    ) -> None:
        joined = await message_buffer.flush_and_cancel("session-1")
        assert joined is None

    @pytest.mark.asyncio
    async def test_concurrent_adds_prevented_by_lock(
        self, message_buffer: MessageBuffer
    ) -> None:
        await message_buffer.add("session-1", "hello")

        # Acquire lock manually to simulate another flush in progress
        lock_key = message_buffer._lock_key("session-1")
        acquired = await message_buffer._redis.acquire_lock(lock_key, ttl_seconds=30)
        assert acquired is True

        try:
            # flush_and_cancel should not be able to acquire lock
            joined = await message_buffer.flush_and_cancel("session-1")
            assert joined is None
        finally:
            await message_buffer._redis.release_lock(lock_key)


class TestIsBuffering:
    """Checking if a session has buffered messages."""

    @pytest.mark.asyncio
    async def test_is_buffering_true(self, message_buffer: MessageBuffer) -> None:
        await message_buffer.add("session-1", "hello")
        assert await message_buffer.is_buffering("session-1") is True

    @pytest.mark.asyncio
    async def test_is_buffering_false(self, message_buffer: MessageBuffer) -> None:
        assert await message_buffer.is_buffering("session-1") is False


class TestGetCount:
    """Getting the number of buffered messages."""

    @pytest.mark.asyncio
    async def test_get_count(self, message_buffer: MessageBuffer) -> None:
        await message_buffer.add("session-1", "a")
        await message_buffer.add("session-1", "b")
        assert await message_buffer.get_count("session-1") == 2

    @pytest.mark.asyncio
    async def test_get_count_empty(self, message_buffer: MessageBuffer) -> None:
        assert await message_buffer.get_count("session-1") == 0


class TestFallbackWhenRedisUnavailable:
    """Graceful fallback when Redis connection fails."""

    @pytest.mark.asyncio
    async def test_add_falls_back_to_in_memory(self) -> None:
        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.set.return_value = False
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = False

        provider = MockConfigProvider()
        buf = MessageBuffer(redis_cache=mock_redis, config_provider=provider)

        result = await buf.add("session-1", "hello")
        # Should fallback to in-memory and still report buffering
        assert result.is_buffering is True

    @pytest.mark.asyncio
    async def test_flush_falls_back_to_in_memory(self) -> None:
        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.set.return_value = False
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = False

        provider = MockConfigProvider()
        buf = MessageBuffer(redis_cache=mock_redis, config_provider=provider)

        # Add in-memory via fallback
        await buf.add("session-1", "hello")
        joined = await buf.flush("session-1")
        assert joined == "hello"

    @pytest.mark.asyncio
    async def test_is_buffering_falls_back(self) -> None:
        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.set.return_value = False
        mock_redis.get.return_value = None
        mock_redis.exists.return_value = False

        provider = MockConfigProvider()
        buf = MessageBuffer(redis_cache=mock_redis, config_provider=provider)

        await buf.add("session-1", "hello")
        assert await buf.is_buffering("session-1") is True


class TestModuleLevelWrappers:
    """Legacy module-level functions must delegate to MessageBuffer."""

    @pytest.mark.asyncio
    async def test_add_to_buffer_wrapper(self, redis_cache: RedisCache) -> None:
        from backend.app import message_buffer as mb

        # The module-level _message_buffer should be None by default
        # We need to set it for the wrapper to work
        original = mb._message_buffer
        mb._message_buffer = MessageBuffer(
            redis_cache=redis_cache,
            config_provider=MockConfigProvider(),
        )
        try:
            result = await mb.add_to_buffer("session-1", "hello")
            assert result is None  # Still buffering
        finally:
            mb._message_buffer = original

    @pytest.mark.asyncio
    async def test_flush_buffer_wrapper(self, redis_cache: RedisCache) -> None:
        from backend.app import message_buffer as mb

        original = mb._message_buffer
        mb._message_buffer = MessageBuffer(
            redis_cache=redis_cache,
            config_provider=MockConfigProvider(),
        )
        try:
            await mb._message_buffer.add("session-1", "hello")
            joined = await mb.flush_buffer("session-1")
            assert joined == "hello"
        finally:
            mb._message_buffer = original
