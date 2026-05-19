"""Async Redis wrapper with structured key naming and graceful failures.

All operations return safe defaults (``None``/``False``) when Redis is
unavailable so callers never need to catch connection errors.
"""

import logging
from typing import Optional, Union

import redis.asyncio
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisCache:
    """High-level async Redis client with key namespacing.

    Args:
        redis_url: Redis connection URL (e.g. ``redis://localhost:6379/0``).
        password: Optional Redis password.
        prefix: Key prefix for namespacing. Defaults to ``"chatwoot"``.
        account_id: Chatwoot account ID embedded in every key.
            Defaults to ``"unconfigured"`` to avoid collisions when Chatwoot is
            disabled or not fully configured.
    """

    def __init__(
        self,
        redis_url: str,
        password: Optional[str] = None,
        prefix: str = "chatwoot",
        account_id: Union[int, str] = "unconfigured",
    ) -> None:
        self._prefix = prefix
        self._account_id = account_id
        self._redis = redis.asyncio.Redis.from_url(
            redis_url,
            password=password,
            decode_responses=True,
        )

    def _build_key(
        self, scope: str, entity_id: str, field: Optional[str] = None
    ) -> str:
        """Build a namespaced Redis key.

        Format: ``{prefix}:{account_id}:{scope}:{entity_id}[:{field}]``
        """
        key = f"{self._prefix}:{self._account_id}:{scope}:{entity_id}"
        if field is not None:
            key = f"{key}:{field}"
        return key

    async def get(self, key: str) -> Optional[str]:
        """Fetch a string value."""
        try:
            result = await self._redis.get(key)
            return result if result is None else str(result)
        except RedisError as exc:
            logger.warning("Redis get failed: %s", exc)
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Store a string value with optional TTL in seconds."""
        try:
            await self._redis.set(key, value, ex=ttl)
            return True
        except RedisError as exc:
            logger.warning("Redis set failed: %s", exc)
            return False

    async def delete(self, key: str) -> bool:
        """Remove a key."""
        try:
            await self._redis.delete(key)
            return True
        except RedisError as exc:
            logger.warning("Redis delete failed: %s", exc)
            return False

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        try:
            return bool(await self._redis.exists(key))
        except RedisError as exc:
            logger.warning("Redis exists failed: %s", exc)
            return False

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Fetch a hash field."""
        try:
            result = await self._redis.hget(key, field)
            return result if result is None else str(result)
        except RedisError as exc:
            logger.warning("Redis hget failed: %s", exc)
            return None

    async def hset(self, key: str, field: str, value: str) -> bool:
        """Set a hash field."""
        try:
            await self._redis.hset(key, field, value)
            return True
        except RedisError as exc:
            logger.warning("Redis hset failed: %s", exc)
            return False

    async def hgetall(self, key: str) -> dict[str, str]:
        """Fetch all fields of a hash."""
        try:
            result = await self._redis.hgetall(key)
            return {str(k): str(v) for k, v in result.items()}
        except RedisError as exc:
            logger.warning("Redis hgetall failed: %s", exc)
            return {}

    async def lpush(self, key: str, value: str) -> int:
        """Push a value onto the left of a list."""
        try:
            return int(await self._redis.lpush(key, value))
        except RedisError as exc:
            logger.warning("Redis lpush failed: %s", exc)
            return 0

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Return a slice of a list."""
        try:
            result = await self._redis.lrange(key, start, stop)
            return [str(v) for v in result]
        except RedisError as exc:
            logger.warning("Redis lrange failed: %s", exc)
            return []

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim a list to the given range."""
        try:
            await self._redis.ltrim(key, start, stop)
            return True
        except RedisError as exc:
            logger.warning("Redis ltrim failed: %s", exc)
            return False

    async def sadd(self, key: str, member: str) -> bool:
        """Add a member to a set."""
        try:
            await self._redis.sadd(key, member)
            return True
        except RedisError as exc:
            logger.warning("Redis sadd failed: %s", exc)
            return False

    async def sismember(self, key: str, member: str) -> bool:
        """Check whether *member* is in *key* set."""
        try:
            return bool(await self._redis.sismember(key, member))
        except RedisError as exc:
            logger.warning("Redis sismember failed: %s", exc)
            return False

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 30) -> bool:
        """Acquire a distributed lock using ``SET NX EX``.

        Returns:
            ``True`` if the lock was acquired, ``False`` if it is already held.
        """
        try:
            result = await self._redis.set(lock_key, "1", nx=True, ex=ttl_seconds)
            return result is not None
        except RedisError as exc:
            logger.warning("Redis acquire_lock failed: %s", exc)
            return False

    async def release_lock(self, lock_key: str) -> bool:
        """Release a distributed lock by deleting the key."""
        try:
            await self._redis.delete(lock_key)
            return True
        except RedisError as exc:
            logger.warning("Redis release_lock failed: %s", exc)
            return False

    async def hdel(self, key: str, field: str) -> bool:
        """Delete a hash field."""
        try:
            await self._redis.hdel(key, field)
            return True
        except RedisError as exc:
            logger.warning("Redis hdel failed: %s", exc)
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key."""
        try:
            await self._redis.expire(key, ttl)
            return True
        except RedisError as exc:
            logger.warning("Redis expire failed: %s", exc)
            return False

    async def health_check(self) -> bool:
        """Return ``True`` if Redis responds to ``PING``."""
        try:
            await self._redis.ping()
            return True
        except RedisError as exc:
            logger.warning("Redis health_check failed: %s", exc)
            return False
