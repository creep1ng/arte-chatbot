"""Tests for RedisCache async wrapper.

Uses fakeredis.FakeAsyncRedis to exercise all Redis operations without
a real server.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import RedisError

from backend.app.redis_cache import RedisCache


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def cache(fake_redis: FakeAsyncRedis) -> RedisCache:
    with patch("backend.app.redis_cache.redis.asyncio.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake_redis
        return RedisCache(redis_url="redis://localhost:6379/0")


class TestKeyNaming:
    """Key builder must follow the documented convention."""

    def test_build_key_without_field(self, cache: RedisCache) -> None:
        key = cache._build_key("conversation", "42")
        assert key == "chatwoot:1:conversation:42"

    def test_build_key_with_field(self, cache: RedisCache) -> None:
        key = cache._build_key("conversation", "42", "metadata")
        assert key == "chatwoot:1:conversation:42:metadata"

    def test_custom_prefix(self, fake_redis: FakeAsyncRedis) -> None:
        with patch(
            "backend.app.redis_cache.redis.asyncio.Redis", return_value=fake_redis
        ):
            custom = RedisCache(redis_url="redis://localhost", prefix="custom")
        assert custom._build_key("scope", "id") == "custom:1:scope:id"


class TestStringOperations:
    """GET / SET / DELETE / EXISTS."""

    @pytest.mark.asyncio
    async def test_get_existing(self, cache: RedisCache) -> None:
        await cache.set("k", "v")
        assert await cache.get("k") == "v"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, cache: RedisCache) -> None:
        assert await cache.get("missing") is None

    @pytest.mark.asyncio
    async def test_set_and_ttl(self, cache: RedisCache) -> None:
        assert await cache.set("k", "v", ttl=60) is True

    @pytest.mark.asyncio
    async def test_delete_existing(self, cache: RedisCache) -> None:
        await cache.set("k", "v")
        assert await cache.delete("k") is True
        assert await cache.get("k") is None

    @pytest.mark.asyncio
    async def test_delete_missing(self, cache: RedisCache) -> None:
        assert await cache.delete("missing") is True

    @pytest.mark.asyncio
    async def test_exists(self, cache: RedisCache) -> None:
        await cache.set("k", "v")
        assert await cache.exists("k") is True
        assert await cache.exists("missing") is False


class TestHashOperations:
    """HGET / HSET / HGETALL."""

    @pytest.mark.asyncio
    async def test_hset_and_hget(self, cache: RedisCache) -> None:
        assert await cache.hset("hash", "field", "val") is True
        assert await cache.hget("hash", "field") == "val"

    @pytest.mark.asyncio
    async def test_hget_missing(self, cache: RedisCache) -> None:
        assert await cache.hget("hash", "field") is None

    @pytest.mark.asyncio
    async def test_hgetall(self, cache: RedisCache) -> None:
        await cache.hset("hash", "a", "1")
        await cache.hset("hash", "b", "2")
        result = await cache.hgetall("hash")
        assert result == {"a": "1", "b": "2"}

    @pytest.mark.asyncio
    async def test_hgetall_empty(self, cache: RedisCache) -> None:
        assert await cache.hgetall("empty") == {}


class TestListOperations:
    """LPUSH / LRANGE / LTRIM."""

    @pytest.mark.asyncio
    async def test_lpush(self, cache: RedisCache) -> None:
        length = await cache.lpush("list", "a")
        assert length == 1
        length = await cache.lpush("list", "b")
        assert length == 2

    @pytest.mark.asyncio
    async def test_lrange(self, cache: RedisCache) -> None:
        await cache.lpush("list", "a")
        await cache.lpush("list", "b")
        await cache.lpush("list", "c")
        result = await cache.lrange("list", 0, -1)
        assert result == ["c", "b", "a"]

    @pytest.mark.asyncio
    async def test_ltrim(self, cache: RedisCache) -> None:
        await cache.lpush("list", "a")
        await cache.lpush("list", "b")
        assert await cache.ltrim("list", 0, 0) is True
        assert await cache.lrange("list", 0, -1) == ["b"]


class TestSetOperations:
    """SADD / SISMEMBER."""

    @pytest.mark.asyncio
    async def test_sadd(self, cache: RedisCache) -> None:
        assert await cache.sadd("set", "member1") is True

    @pytest.mark.asyncio
    async def test_sismember(self, cache: RedisCache) -> None:
        await cache.sadd("set", "member1")
        assert await cache.sismember("set", "member1") is True
        assert await cache.sismember("set", "member2") is False


class TestLockOperations:
    """Distributed lock via SET NX EX."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, cache: RedisCache) -> None:
        assert await cache.acquire_lock("my_lock", ttl_seconds=10) is True

    @pytest.mark.asyncio
    async def test_acquire_lock_already_held(self, cache: RedisCache) -> None:
        await cache.acquire_lock("my_lock", ttl_seconds=10)
        assert await cache.acquire_lock("my_lock", ttl_seconds=10) is False

    @pytest.mark.asyncio
    async def test_release_lock(self, cache: RedisCache) -> None:
        await cache.acquire_lock("my_lock", ttl_seconds=10)
        assert await cache.release_lock("my_lock") is True
        assert await cache.acquire_lock("my_lock", ttl_seconds=10) is True

    @pytest.mark.asyncio
    async def test_release_lock_missing(self, cache: RedisCache) -> None:
        assert await cache.release_lock("my_lock") is True


class TestErrorHandling:
    """On RedisError the cache must return safe defaults and not raise."""

    @pytest.mark.asyncio
    async def test_get_on_redis_error_returns_none(self, cache: RedisCache) -> None:
        cache._redis.get = AsyncMock(side_effect=RedisError("redis down"))  # type: ignore[misc]
        assert await cache.get("k") is None

    @pytest.mark.asyncio
    async def test_set_on_redis_error_returns_false(self, cache: RedisCache) -> None:
        cache._redis.set = AsyncMock(side_effect=RedisError("redis down"))  # type: ignore[misc]
        assert await cache.set("k", "v") is False

    @pytest.mark.asyncio
    async def test_delete_on_redis_error_returns_false(self, cache: RedisCache) -> None:
        cache._redis.delete = AsyncMock(side_effect=RedisError("redis down"))  # type: ignore[misc]
        assert await cache.delete("k") is False

    @pytest.mark.asyncio
    async def test_exists_on_redis_error_returns_false(self, cache: RedisCache) -> None:
        cache._redis.exists = AsyncMock(side_effect=RedisError("redis down"))  # type: ignore[misc]
        assert await cache.exists("k") is False


class TestHashDelete:
    """HDEL operation."""

    @pytest.mark.asyncio
    async def test_hdel_existing(self, cache: RedisCache) -> None:
        await cache.hset("hash", "field", "val")
        assert await cache.hdel("hash", "field") is True
        assert await cache.hget("hash", "field") is None

    @pytest.mark.asyncio
    async def test_hdel_missing(self, cache: RedisCache) -> None:
        assert await cache.hdel("hash", "field") is True


class TestExpire:
    """EXPIRE operation."""

    @pytest.mark.asyncio
    async def test_expire_sets_ttl(self, cache: RedisCache) -> None:
        await cache.set("k", "v")
        assert await cache.expire("k", 60) is True

    @pytest.mark.asyncio
    async def test_expire_missing_key(self, cache: RedisCache) -> None:
        assert await cache.expire("missing", 60) is True


class TestHealthCheck:
    """Health check must reflect Redis connectivity."""

    @pytest.mark.asyncio
    async def test_health_check_ok(self, cache: RedisCache) -> None:
        assert await cache.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_fail(self, cache: RedisCache) -> None:
        cache._redis.ping = AsyncMock(side_effect=RedisError("redis down"))  # type: ignore[misc]
        assert await cache.health_check() is False
