"""Tests for hybrid Redis SessionManager.

Uses fakeredis to exercise Redis-backed session operations without a real Redis
server while preserving the legacy synchronous API used by /chat.
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


class TestLegacySyncApi:
    """The existing /chat-facing SessionManager API remains synchronous."""

    def test_add_turn_and_get_history_are_sync(self) -> None:
        sm = SessionManager(max_turns=2)

        sm.add_turn("s1", "Pregunta 1", "Respuesta 1")
        sm.add_turn("s1", "Pregunta 2", "Respuesta 2")
        sm.add_turn("s1", "Pregunta 3", "Respuesta 3")

        history = sm.get_history("s1")
        assert len(history) == 2
        assert history[0].question == "Pregunta 2"
        assert history[1].question == "Pregunta 3"

    def test_profile_and_token_methods_are_sync(self) -> None:
        sm = SessionManager()

        sm.set_user_profile("s1", "experto")
        sm.add_token_usage("s1", 100, 50, 150)

        assert sm.get_user_profile("s1") == "experto"
        assert sm.get_token_totals("s1").total_tokens == 150

    def test_context_and_clear_session_are_sync(self) -> None:
        sm = SessionManager()
        sm.add_turn("s1", "¿Panel?", "Sí", ["doc1.pdf"])

        context = sm.get_context_string("s1")
        assert "Usuario: ¿Panel?" in context

        sm.clear_session("s1")
        assert sm.get_history("s1") == []


class TestAsyncHistory:
    """Redis-backed async history methods."""

    @pytest.mark.asyncio
    async def test_add_turn_async_creates_redis_list(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn_async(
            "s1", "¿Qué es solar?", "Energía del sol", []
        )
        history = await session_manager.get_history_async("s1")
        assert len(history) == 1
        assert history[0].question == "¿Qué es solar?"
        assert history[0].answer == "Energía del sol"

    @pytest.mark.asyncio
    async def test_add_turn_async_trims_to_max(
        self, session_manager: SessionManager
    ) -> None:
        sm = SessionManager(redis_cache=session_manager._redis, max_turns=2)
        for index in range(4):
            await sm.add_turn_async("s1", f"Pregunta {index}", f"Respuesta {index}", [])

        history = await sm.get_history_async("s1")
        assert len(history) == 2
        assert history[0].question == "Pregunta 2"
        assert history[1].question == "Pregunta 3"

    @pytest.mark.asyncio
    async def test_add_turn_async_includes_source_documents(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.add_turn_async("s1", "¿Panel?", "Sí", ["doc1.pdf"])
        history = await session_manager.get_history_async("s1")
        assert history[0].source_documents == ["doc1.pdf"]

    @pytest.mark.asyncio
    async def test_get_history_async_empty(
        self, session_manager: SessionManager
    ) -> None:
        assert await session_manager.get_history_async("s1") == []

    @pytest.mark.asyncio
    async def test_get_history_async_chatwoot_fallback(
        self, redis_cache: RedisCache
    ) -> None:
        mock_client = AsyncMock(spec=ChatwootClient)
        mock_client.fetch_messages.return_value = {
            "payload": [
                {"content": "Hola", "message_type": 0, "sender_type": "contact"},
                {"content": "Buenas", "message_type": 1, "sender_type": "user"},
            ]
        }
        sm = SessionManager(redis_cache=redis_cache, chatwoot_client=mock_client)
        await sm.map_conversation("s1", "42")

        history = await sm.get_history_async("s1")

        assert len(history) == 1
        assert history[0].question == "Hola"
        mock_client.fetch_messages.assert_awaited_once_with(42, limit=20)

    @pytest.mark.asyncio
    async def test_get_history_async_redis_unavailable_fallback(self) -> None:
        from redis.exceptions import RedisError

        mock_redis = AsyncMock(spec=RedisCache)
        mock_redis._build_key = lambda scope, entity_id, field=None: (
            f"chatwoot:1:{scope}:{entity_id}" + (f":{field}" if field else "")
        )
        mock_redis.lpush.side_effect = RedisError("redis down")
        mock_redis.lrange.side_effect = RedisError("redis down")

        sm = SessionManager(redis_cache=mock_redis)
        await sm.add_turn_async("s1", "Hola", "Buenas", [])
        history = await sm.get_history_async("s1")
        assert len(history) == 1
        assert history[0].question == "Hola"

    @pytest.mark.asyncio
    async def test_hydrate_history_from_chatwoot_messages(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.hydrate_history_from_chatwoot(
            "s1",
            [
                {"content": "Necesito cotizar", "message_type": "incoming"},
                {"content": "Te ayudo", "message_type": "outgoing"},
            ],
        )

        history = await session_manager.get_history_async("s1")
        assert len(history) == 1
        assert history[0].question == "Necesito cotizar"
        assert history[0].answer == "Te ayudo"


class TestConversationMapping:
    """Session ID ↔ Conversation ID mapping."""

    @pytest.mark.asyncio
    async def test_get_or_create_session_for_conversation_reuses_mapping(
        self, session_manager: SessionManager
    ) -> None:
        first = await session_manager.get_or_create_session_for_conversation("42")
        second = await session_manager.get_or_create_session_for_conversation("42")

        assert first == second
        assert await session_manager.get_conversation_for_session(first) == "42"

    @pytest.mark.asyncio
    async def test_map_conversation_compatibility(
        self, session_manager: SessionManager
    ) -> None:
        await session_manager.map_conversation("s1", "42")

        assert await session_manager.get_conversation_id("s1") == "42"
        assert await session_manager.get_session_id("42") == "s1"

    @pytest.mark.asyncio
    async def test_missing_mapping_returns_none(
        self, session_manager: SessionManager
    ) -> None:
        assert await session_manager.get_conversation_for_session("s1") is None
        assert await session_manager.get_session_id("42") is None
