"""Tests for hybrid Redis SessionManager.

Uses fakeredis to exercise Redis-backed session operations without a
real Redis server.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fakeredis import FakeAsyncRedis

from backend.app.chatwoot_client import ChatwootClient
from backend.app.redis_cache import RedisCache
from backend.app.session import SessionManager


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def redis_cache(fake_redis: FakeAsyncRedis) -> RedisCache:
    with patch("backend.app.redis_cache.redis.asyncio.Redis") as MockRedis:
        MockRedis.from_url.return_value = fake_redis
        return RedisCache(redis_url="redis://localhost:6379/0")


@pytest.fixture
def session_manager(redis_cache: RedisCache) -> SessionManager:
    return SessionManager(redis_cache=redis_cache)


class TestAddTurn:
    """Storing conversation turns in Redis."""

    @pytest.mark.asyncio
    async def test_add_turn_creates_redis_list(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn("s1", "¿Qué es solar?", "Energía del sol")
        history = await session_manager.get_history("s1")
        assert len(history) == 1
        assert history[0].question == "¿Qué es solar?"
        assert history[0].answer == "Energía del sol"

    @pytest.mark.asyncio
    async def test_add_turn_trims_to_max(self, session_manager: SessionManager) -> None:
        sm = SessionManager(redis_cache=session_manager._redis, max_turns=2)
        for i in range(4):
            await sm.add_turn("s1", f"Pregunta {i}", f"Respuesta {i}")
        history = await sm.get_history("s1")
        assert len(history) == 2
        assert history[0].question == "Pregunta 2"
        assert history[1].question == "Pregunta 3"

    @pytest.mark.asyncio
    async def test_add_turn_includes_source_documents(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn(
            "s1", "¿Panel?", "Sí", source_documents=["doc1.pdf"]
        )
        history = await session_manager.get_history("s1")
        assert history[0].source_documents == ["doc1.pdf"]


class TestGetHistory:
    """Retrieving history from Redis with fallbacks."""

    @pytest.mark.asyncio
    async def test_get_history_from_redis(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn("s1", "Hola", "Buenas")
        await session_manager.add_turn("s1", "Adiós", "Hasta luego")
        history = await session_manager.get_history("s1")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_history_empty(self, session_manager: SessionManager) -> None:
        history = await session_manager.get_history("s1")
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_chatwoot_fallback(self, redis_cache: RedisCache) -> None:
        mock_client = AsyncMock(spec=ChatwootClient)
        mock_client.fetch_messages.return_value = {
            "payload": [
                {"content": "Hola", "message_type": 0, "sender_type": "contact"},
                {"content": "Buenas", "message_type": 1, "sender_type": "user"},
            ]
        }

        sm = SessionManager(redis_cache=redis_cache, chatwoot_client=mock_client)
        # Map conversation so fallback knows which conversation to fetch
        await sm.map_conversation("s1", "42")

        history = await sm.get_history("s1")
        assert len(history) == 1  # Only contact message becomes a turn
        mock_client.fetch_messages.assert_awaited_once_with(42, limit=10)

    @pytest.mark.asyncio
    async def test_get_history_redis_unavailable_fallback(self) -> None:
        from redis.exceptions import RedisError

        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.lpush.side_effect = RedisError("redis down")
        mock_redis.lrange.side_effect = RedisError("redis down")

        sm = SessionManager(redis_cache=mock_redis)
        await sm.add_turn("s1", "Hola", "Buenas")
        # Should fall back to in-memory
        history = await sm.get_history("s1")
        assert len(history) == 1
        assert history[0].question == "Hola"


class TestGetContextString:
    """Formatting history for LLM context."""

    @pytest.mark.asyncio
    async def test_get_context_string(self, session_manager: SessionManager) -> None:
        await session_manager.add_turn("s1", "¿Panel?", "Sí", ["doc1.pdf"])
        ctx = await session_manager.get_context_string("s1")
        assert "Turno 1:" in ctx
        assert "Usuario: ¿Panel?" in ctx
        assert "Asistente: Sí" in ctx
        assert "Fuentes: doc1.pdf" in ctx

    @pytest.mark.asyncio
    async def test_get_context_string_empty(
        self, session_manager: SessionManager
    ) -> None:
        ctx = await session_manager.get_context_string("s1")
        assert ctx == ""


class TestUserProfile:
    """Profile storage in Redis."""

    @pytest.mark.asyncio
    async def test_set_and_get_profile(self, session_manager: SessionManager) -> None:
        await session_manager.set_user_profile("s1", "novato")
        profile = await session_manager.get_user_profile("s1")
        assert profile == "novato"

    @pytest.mark.asyncio
    async def test_get_profile_missing(self, session_manager: SessionManager) -> None:
        profile = await session_manager.get_user_profile("s1")
        assert profile is None


class TestTokenUsage:
    """Token accumulation via Redis hash."""

    @pytest.mark.asyncio
    async def test_add_token_usage(self, session_manager: SessionManager) -> None:
        await session_manager.add_token_usage("s1", 100, 50, 150)
        totals = await session_manager.get_token_totals("s1")
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.total_tokens == 150

    @pytest.mark.asyncio
    async def test_add_token_usage_accumulates(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_token_usage("s1", 100, 50, 150)
        await session_manager.add_token_usage("s1", 200, 100, 300)
        totals = await session_manager.get_token_totals("s1")
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150
        assert totals.total_tokens == 450


class TestConversationMapping:
    """Session ID ↔ Conversation ID mapping."""

    @pytest.mark.asyncio
    async def test_map_conversation(self, session_manager: SessionManager) -> None:
        await session_manager.map_conversation("s1", "42")
        conv_id = await session_manager.get_conversation_id("s1")
        assert conv_id == "42"

    @pytest.mark.asyncio
    async def test_get_session_id_reverse(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.map_conversation("s1", "42")
        session_id = await session_manager.get_session_id("42")
        assert session_id == "s1"

    @pytest.mark.asyncio
    async def test_get_conversation_id_missing(
        self, session_manager: SessionManager
    ) -> None:
        assert await session_manager.get_conversation_id("s1") is None

    @pytest.mark.asyncio
    async def test_get_session_id_missing(
        self, session_manager: SessionManager
    ) -> None:
        assert await session_manager.get_session_id("42") is None


class TestClearSession:
    """Clearing session data from Redis."""

    @pytest.mark.asyncio
    async def test_clear_session_removes_all(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn("s1", "Hola", "Buenas")
        await session_manager.set_user_profile("s1", "novato")
        await session_manager.add_token_usage("s1", 10, 5, 15)
        await session_manager.map_conversation("s1", "42")

        await session_manager.clear_session("s1")

        assert await session_manager.get_history("s1") == []
        assert await session_manager.get_user_profile("s1") is None
        totals = await session_manager.get_token_totals("s1")
        assert totals.total_tokens == 0
        assert await session_manager.get_conversation_id("s1") is None


class TestFallbackWhenRedisUnavailable:
    """Graceful degradation when Redis is down."""

    @pytest.mark.asyncio
    async def test_add_turn_fallback(self) -> None:
        from redis.exceptions import RedisError

        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.lpush.side_effect = RedisError("redis down")
        mock_redis.lrange.side_effect = RedisError("redis down")

        sm = SessionManager(redis_cache=mock_redis)
        await sm.add_turn("s1", "Hola", "Buenas")
        history = await sm.get_history("s1")
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_set_profile_fallback(self) -> None:
        from redis.exceptions import RedisError

        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.set.side_effect = RedisError("redis down")
        mock_redis.get.side_effect = RedisError("redis down")

        sm = SessionManager(redis_cache=mock_redis)
        await sm.set_user_profile("s1", "experto")
        profile = await sm.get_user_profile("s1")
        assert profile == "experto"

    @pytest.mark.asyncio
    async def test_token_usage_fallback(self) -> None:
        from redis.exceptions import RedisError

        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.hgetall.side_effect = RedisError("redis down")
        mock_redis.hset.side_effect = RedisError("redis down")

        sm = SessionManager(redis_cache=mock_redis)
        await sm.add_token_usage("s1", 100, 50, 150)
        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 100
