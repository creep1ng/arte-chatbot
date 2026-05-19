"""fakeredis integration tests for Chatwoot Redis-backed state."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis import FakeAsyncRedis

from backend.app.message_buffer import MessageBuffer
from backend.app.redis_cache import RedisCache
from backend.app.session import SessionManager


class DummyConfigProvider:
    """Minimal buffer config provider for Redis integration tests."""

    def get(self, key: str) -> int | None:
        """Return deterministic buffer settings."""
        if key == "buffer_window_seconds":
            return 5
        if key == "buffer_max_messages":
            return 5
        return None


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    """Return a shared fake Redis instance."""
    return FakeAsyncRedis(decode_responses=True)


def _cache(fake_redis: FakeAsyncRedis, account_id: int | str) -> RedisCache:
    """Build a RedisCache sharing the given fakeredis instance."""
    with patch("backend.app.redis_cache.redis.asyncio.Redis") as mock_redis:
        mock_redis.from_url.return_value = fake_redis
        return RedisCache(
            redis_url="redis://localhost:6379/0",
            account_id=account_id,
        )


@pytest.mark.asyncio
async def test_session_mapping_and_buffer_share_namespace_without_collisions(
    fake_redis: FakeAsyncRedis,
) -> None:
    """Session metadata and buffers should coexist in one account namespace."""
    redis_cache = _cache(fake_redis, account_id=1)
    session_manager = SessionManager(redis_cache=redis_cache)
    message_buffer = MessageBuffer(redis_cache, DummyConfigProvider())

    session_id = await session_manager.get_or_create_session_for_conversation(
        "42", account_id=1
    )
    await message_buffer.add_message("42", "Hola", window_seconds=5)

    assert await session_manager.get_session_id("42") == session_id
    assert await message_buffer.get_count("42") == 1
    assert await fake_redis.exists("chatwoot:1:conversation:42:metadata") == 1
    assert await fake_redis.exists("chatwoot:1:buffer:42") == 1


@pytest.mark.asyncio
async def test_unconfigured_namespace_does_not_collide_with_account_one(
    fake_redis: FakeAsyncRedis,
) -> None:
    """Disabled/unconfigured Chatwoot state must not share account 1 keys."""
    account_cache = _cache(fake_redis, account_id=1)
    unconfigured_cache = _cache(fake_redis, account_id="unconfigured")
    account_buffer = MessageBuffer(account_cache, DummyConfigProvider())
    unconfigured_buffer = MessageBuffer(unconfigured_cache, DummyConfigProvider())

    await account_buffer.add_message("42", "Cuenta 1", window_seconds=5)
    await unconfigured_buffer.add_message("42", "Sin configurar", window_seconds=5)

    assert await account_buffer.flush("42") == "Cuenta 1"
    assert await unconfigured_buffer.flush("42") == "Sin configurar"


@pytest.mark.asyncio
async def test_cache_miss_hydrates_history_from_chatwoot_source_of_truth(
    fake_redis: FakeAsyncRedis,
) -> None:
    """History cache misses should fetch Chatwoot once and then use Redis."""
    redis_cache = _cache(fake_redis, account_id=1)
    chatwoot_client = AsyncMock()
    chatwoot_client.fetch_messages.return_value = {
        "payload": [
            {"content": "Necesito paneles", "message_type": "incoming"},
            {"content": "Te ayudo con paneles", "message_type": "outgoing"},
        ]
    }
    session_manager = SessionManager(
        redis_cache=redis_cache,
        chatwoot_client=chatwoot_client,
    )
    await session_manager.map_conversation("session-1", "42")

    first_history = await session_manager.get_history_async("session-1")
    second_history = await session_manager.get_history_async("session-1")

    assert first_history[0].question == "Necesito paneles"
    assert second_history[0].answer == "Te ayudo con paneles"
    chatwoot_client.fetch_messages.assert_awaited_once_with(42, limit=20)


@pytest.mark.asyncio
async def test_distributed_lock_prevents_double_flush(
    fake_redis: FakeAsyncRedis,
) -> None:
    """Concurrent flush attempts should produce a single joined message."""
    redis_cache = _cache(fake_redis, account_id=1)
    message_buffer = MessageBuffer(redis_cache, DummyConfigProvider())
    await message_buffer.add_message("42", "Uno", window_seconds=5)
    await message_buffer.add_message("42", "Dos", window_seconds=5)

    first, second = await asyncio.gather(
        message_buffer.flush("42"),
        message_buffer.flush("42"),
    )

    assert sorted([first, second], key=lambda value: value is not None) == [
        None,
        "Uno\nDos",
    ]
