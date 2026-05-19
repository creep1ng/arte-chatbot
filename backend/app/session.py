"""
Servicio de gestión de sesiones para el chatbot.

Mantiene la API síncrona usada por ``/chat`` y añade métodos asíncronos
Redis-backed para el flujo Chatwoot.
"""

import logging
import threading
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.app.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """Representa un turno en la conversación."""

    question: str
    answer: str
    timestamp: datetime
    source_documents: list[str] = Field(default_factory=list)


class TokenTotals(BaseModel):
    """Acumulador de tokens consumidos por sesión.

    Attributes:
        input_tokens: Total de tokens de entrada consumidos.
        output_tokens: Total de tokens de salida generados.
        total_tokens: Total de tokens (input + output).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SessionManager:
    """Gestiona sesiones con memoria local y métodos Redis async opcionales.

    Args:
        max_turns: Máximo de turnos preservados por sesión.
        redis_cache: Redis opcional para flujo Chatwoot.
        chatwoot_client: Cliente opcional para hidratación futura desde Chatwoot.
    """

    _TTL_SECONDS = 86400

    def __init__(
        self,
        max_turns: int = 20,
        redis_cache: Optional[RedisCache] = None,
        chatwoot_client: Optional[Any] = None,
    ) -> None:
        self.max_turns = max_turns
        self._redis = redis_cache
        self._chatwoot = chatwoot_client
        self._lock = threading.Lock()
        self._sessions: dict[str, list[ChatTurn]] = {}
        self._profiles: dict[str, str] = {}
        self._token_totals: dict[str, TokenTotals] = {}
        self._conversation_map: dict[str, str] = {}
        self._reverse_map: dict[str, str] = {}

    @property
    def sessions(self) -> dict[str, list[ChatTurn]]:
        """Expose legacy in-memory sessions for tests/debugging."""
        return self._sessions

    @property
    def profiles(self) -> dict[str, str]:
        """Expose legacy in-memory profiles for tests/debugging."""
        return self._profiles

    @property
    def token_totals(self) -> dict[str, TokenTotals]:
        """Expose legacy in-memory token totals for tests/debugging."""
        return self._token_totals

    def _history_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"session:{session_id}:history"
        return self._redis._build_key("session", session_id, "history")

    def _conversation_metadata_key(self, conversation_id: str) -> str:
        if self._redis is None:
            return f"conversation:{conversation_id}:metadata"
        return self._redis._build_key("conversation", conversation_id, "metadata")

    def _session_conversation_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"session:{session_id}:conversation_id"
        return self._redis._build_key("session", session_id, "conversation_id")

    def _profile_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"profile:{session_id}"
        return self._redis._build_key("profile", session_id)

    def _tokens_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"tokens:{session_id}"
        return self._redis._build_key("tokens", session_id)

    def add_turn(
        self,
        session_id: str,
        question: str,
        answer: str,
        source_documents: Optional[list[str]] = None,
    ) -> None:
        """Añade un turno a la memoria local usada por ``/chat``."""
        turn = ChatTurn(
            question=question,
            answer=answer,
            timestamp=datetime.now(),
            source_documents=source_documents or [],
        )
        self._append_memory_turn(session_id, turn)

    def get_history(self, session_id: str) -> list[ChatTurn]:
        """Obtiene el historial local síncrono de una sesión."""
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def get_context_string(self, session_id: str) -> str:
        """Obtiene el historial local formateado para incluir en el prompt."""
        return self._format_context(self.get_history(session_id))

    def clear_session(self, session_id: str) -> None:
        """Elimina los datos locales de una sesión."""
        with self._lock:
            conversation_id = self._conversation_map.pop(session_id, None)
            if conversation_id is not None:
                self._reverse_map.pop(conversation_id, None)
            self._sessions.pop(session_id, None)
            self._profiles.pop(session_id, None)
            self._token_totals.pop(session_id, None)

    def set_user_profile(self, session_id: str, profile: str) -> None:
        """Almacena el perfil local de usuario para una sesión."""
        with self._lock:
            self._profiles[session_id] = profile

    def get_user_profile(self, session_id: str) -> Optional[str]:
        """Obtiene el perfil local de usuario de una sesión."""
        with self._lock:
            return self._profiles.get(session_id)

    def add_token_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        """Acumula el uso local de tokens para una sesión."""
        with self._lock:
            if session_id not in self._token_totals:
                self._token_totals[session_id] = TokenTotals()
            self._token_totals[session_id].input_tokens += input_tokens
            self._token_totals[session_id].output_tokens += output_tokens
            self._token_totals[session_id].total_tokens += total_tokens

    def get_token_totals(self, session_id: str) -> TokenTotals:
        """Obtiene los totales locales de tokens acumulados."""
        with self._lock:
            return self._token_totals.get(session_id, TokenTotals())

    def get_session_count(self) -> int:
        """Obtiene el número de sesiones locales activas."""
        with self._lock:
            return len(self._sessions)

    async def get_or_create_session_for_conversation(
        self, conversation_id: str, account_id: int = 1
    ) -> str:
        """Get or create a session mapped to a Chatwoot conversation.

        Args:
            conversation_id: Chatwoot conversation identifier.
            account_id: Chatwoot account identifier retained for future metadata.

        Returns:
            Internal session ID associated with the conversation.
        """
        if self._redis is not None:
            try:
                metadata_key = self._conversation_metadata_key(conversation_id)
                existing = await self._redis.hget(metadata_key, "session_id")
                if existing:
                    return existing

                session_id = str(uuid.uuid4())
                await self._redis.hset(metadata_key, "session_id", session_id)
                await self._redis.hset(metadata_key, "status", "open")
                await self._redis.hset(metadata_key, "account_id", str(account_id))
                await self._redis.expire(metadata_key, self._TTL_SECONDS)
                reverse_key = self._session_conversation_key(session_id)
                await self._redis.set(
                    reverse_key, conversation_id, ttl=self._TTL_SECONDS
                )
                return session_id
            except Exception as exc:
                logger.warning("Redis session mapping failed, using memory: %s", exc)

        with self._lock:
            existing = self._reverse_map.get(conversation_id)
            if existing is not None:
                return existing
            session_id = str(uuid.uuid4())
            self._conversation_map[session_id] = conversation_id
            self._reverse_map[conversation_id] = session_id
            return session_id

    async def get_conversation_for_session(
        self, session_id: str, account_id: int = 1
    ) -> Optional[str]:
        """Return the Chatwoot conversation ID for an internal session."""
        del account_id
        if self._redis is not None:
            try:
                result = await self._redis.get(
                    self._session_conversation_key(session_id)
                )
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("Redis reverse mapping failed, using memory: %s", exc)

        with self._lock:
            return self._conversation_map.get(session_id)

    async def add_turn_async(
        self,
        session_id: str,
        question: str,
        answer: str,
        source_documents: list[str],
    ) -> None:
        """Append a conversation turn to Redis history with local fallback."""
        turn = ChatTurn(
            question=question,
            answer=answer,
            timestamp=datetime.now(),
            source_documents=source_documents,
        )
        if self._redis is not None:
            try:
                key = self._history_key(session_id)
                await self._redis.lpush(key, turn.model_dump_json())
                await self._redis.ltrim(key, 0, self.max_turns - 1)
                await self._redis.expire(key, self._TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("Redis add_turn_async failed, using memory: %s", exc)

        self._append_memory_turn(session_id, turn)

    async def get_history_async(
        self, session_id: str, limit: int = 10
    ) -> list[ChatTurn]:
        """Get Redis-backed history with Chatwoot/cache-miss fallback hook."""
        if self._redis is not None:
            try:
                raw_items = await self._redis.lrange(
                    self._history_key(session_id), 0, limit - 1
                )
                if raw_items:
                    return [
                        ChatTurn.model_validate_json(raw)
                        for raw in reversed(raw_items[-limit:])
                    ]

                if self._chatwoot is not None:
                    conversation_id = await self.get_conversation_for_session(
                        session_id
                    )
                    if conversation_id is not None:
                        data = await self._chatwoot.fetch_messages(
                            int(conversation_id), limit=limit * 2
                        )
                        await self.hydrate_history_from_chatwoot(
                            session_id, data.get("payload", [])
                        )
                        return await self.get_history_async(session_id, limit=limit)
            except Exception as exc:
                logger.warning("Redis get_history_async failed, using memory: %s", exc)

        with self._lock:
            return list(self._sessions.get(session_id, []))[-limit:]

    async def hydrate_history_from_chatwoot(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Transform Chatwoot messages into ChatTurn entries and cache them."""
        turns = self._parse_chatwoot_messages(messages)
        for turn in turns[-self.max_turns :]:
            await self.add_turn_async(
                session_id,
                turn.question,
                turn.answer,
                turn.source_documents,
            )

    async def map_conversation(self, session_id: str, conversation_id: str) -> None:
        """Backward-compatible async mapping helper."""
        if self._redis is not None:
            try:
                metadata_key = self._conversation_metadata_key(conversation_id)
                await self._redis.hset(metadata_key, "session_id", session_id)
                await self._redis.expire(metadata_key, self._TTL_SECONDS)
                await self._redis.set(
                    self._session_conversation_key(session_id),
                    conversation_id,
                    ttl=self._TTL_SECONDS,
                )
                return
            except Exception as exc:
                logger.warning("Redis map_conversation failed, using memory: %s", exc)

        with self._lock:
            self._conversation_map[session_id] = conversation_id
            self._reverse_map[conversation_id] = session_id

    async def get_conversation_id(self, session_id: str) -> Optional[str]:
        """Backward-compatible alias for get_conversation_for_session."""
        return await self.get_conversation_for_session(session_id)

    async def get_session_id(self, conversation_id: str) -> Optional[str]:
        """Backward-compatible lookup from conversation ID to session ID."""
        if self._redis is not None:
            try:
                result = await self._redis.hget(
                    self._conversation_metadata_key(conversation_id), "session_id"
                )
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("Redis get_session_id failed, using memory: %s", exc)

        with self._lock:
            return self._reverse_map.get(conversation_id)

    def _append_memory_turn(self, session_id: str, turn: ChatTurn) -> None:
        """Append a turn to the in-memory fallback store."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(turn)
            if len(self._sessions[session_id]) > self.max_turns:
                self._sessions[session_id] = self._sessions[session_id][
                    -self.max_turns :
                ]

    def _format_context(self, history: list[ChatTurn]) -> str:
        """Format a list of turns for prompt context."""
        if not history:
            return ""

        context_parts = []
        for index, turn in enumerate(history, 1):
            context_parts.append(f"Turno {index}:")
            context_parts.append(f"Usuario: {turn.question}")
            context_parts.append(f"Asistente: {turn.answer}")
            if turn.source_documents:
                context_parts.append(f"Fuentes: {', '.join(turn.source_documents)}")
            context_parts.append("")
        return "\n".join(context_parts).strip()

    def _parse_chatwoot_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[ChatTurn]:
        """Parse Chatwoot incoming/outgoing messages into turns."""
        turns: list[ChatTurn] = []
        pending_question: Optional[str] = None

        for message in messages:
            content = str(message.get("content") or "").strip()
            if not content:
                continue

            if self._is_incoming_message(message):
                if pending_question is not None:
                    turns.append(
                        ChatTurn(
                            question=pending_question,
                            answer="",
                            timestamp=datetime.now(),
                            source_documents=[],
                        )
                    )
                pending_question = content
                continue

            if pending_question is not None:
                turns.append(
                    ChatTurn(
                        question=pending_question,
                        answer=content,
                        timestamp=datetime.now(),
                        source_documents=[],
                    )
                )
                pending_question = None

        if pending_question is not None:
            turns.append(
                ChatTurn(
                    question=pending_question,
                    answer="",
                    timestamp=datetime.now(),
                    source_documents=[],
                )
            )
        return turns

    def _is_incoming_message(self, message: dict[str, Any]) -> bool:
        """Return True for Chatwoot contact/incoming messages."""
        message_type = message.get("message_type")
        sender_type = message.get("sender_type") or message.get("sender", {}).get(
            "type"
        )
        return message_type in ("incoming", 0) or sender_type == "contact"


# Instancia global del gestor de sesiones
session_manager = SessionManager()
