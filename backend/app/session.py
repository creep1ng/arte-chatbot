"""
Servicio de gestión de sesiones para el chatbot.
Almacena el historial de conversaciones por session_id.
"""

import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.app.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """Representa un turno en la conversación."""

    question: str
    answer: str
    timestamp: datetime
    source_documents: List[str] = []


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
    """Gestiona las sesiones de conversación con almacenamiento híbrido Redis/memoria."""

    _TTL_SECONDS = 86400  # 24 horas

    def __init__(
        self,
        max_turns: int = 20,
        redis_cache: Optional[RedisCache] = None,
        chatwoot_client: Optional[Any] = None,
    ):
        self.max_turns = max_turns
        self._redis = redis_cache
        self._chatwoot = chatwoot_client
        self._lock = threading.Lock()
        # Fallback in-memory storage
        self._sessions: Dict[str, List[ChatTurn]] = {}
        self._profiles: Dict[str, str] = {}
        self._token_totals: Dict[str, TokenTotals] = {}
        self._conversation_map: Dict[str, str] = {}
        self._reverse_map: Dict[str, str] = {}

    def _history_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"history:{session_id}"
        return self._redis._build_key("history", session_id)

    def _profile_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"profile:{session_id}"
        return self._redis._build_key("profile", session_id)

    def _tokens_key(self, session_id: str) -> str:
        if self._redis is None:
            return f"tokens:{session_id}"
        return self._redis._build_key("tokens", session_id)

    def _mapping_session_key(self) -> str:
        if self._redis is None:
            return "mapping:session"
        return self._redis._build_key("mapping", "session")

    def _mapping_conversation_key(self) -> str:
        if self._redis is None:
            return "mapping:conversation"
        return self._redis._build_key("mapping", "conversation")

    async def add_turn(
        self,
        session_id: str,
        question: str,
        answer: str,
        source_documents: Optional[List[str]] = None,
    ) -> None:
        """
        Añade un turno a la sesión.

        Args:
            session_id: Identificador único de la sesión
            question: Pregunta del usuario
            answer: Respuesta del asistente
            source_documents: Lista de documentos fuente utilizados (opcional)
        """
        turn = ChatTurn(
            question=question,
            answer=answer,
            timestamp=datetime.now(),
            source_documents=source_documents or [],
        )

        if self._redis is not None:
            try:
                key = self._history_key(session_id)
                await self._redis.lpush(key, turn.model_dump_json())
                await self._redis.ltrim(key, 0, self.max_turns - 1)
                await self._redis.expire(key, self._TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("Redis add_turn failed, falling back to memory: %s", exc)

        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(turn)
            if len(self._sessions[session_id]) > self.max_turns:
                self._sessions[session_id] = self._sessions[session_id][
                    -self.max_turns :
                ]

    async def get_history(self, session_id: str) -> List[ChatTurn]:
        """
        Obtiene el historial de una sesión.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            Lista de turnos de la sesión, ordenados cronológicamente
        """
        if self._redis is not None:
            try:
                key = self._history_key(session_id)
                raw_items = await self._redis.lrange(key, 0, -1)
                if raw_items:
                    history = []
                    for raw in reversed(raw_items):
                        try:
                            history.append(ChatTurn.model_validate_json(raw))
                        except Exception:
                            logger.warning("Failed to parse ChatTurn JSON: %s", raw)
                    return history

                # Cache miss: try Chatwoot API fallback
                if self._chatwoot is not None:
                    conversation_id = await self.get_conversation_id(session_id)
                    if conversation_id:
                        try:
                            data = await self._chatwoot.fetch_messages(
                                int(conversation_id), limit=10
                            )
                            turns = self._parse_chatwoot_messages(data)
                            for turn in turns:
                                await self._redis.lpush(key, turn.model_dump_json())
                            await self._redis.ltrim(key, 0, self.max_turns - 1)
                            return turns
                        except Exception as exc:
                            logger.warning(
                                "Chatwoot fetch_messages fallback failed: %s", exc
                            )
            except Exception as exc:
                logger.warning("Redis get_history failed, using memory: %s", exc)

        with self._lock:
            return list(self._sessions.get(session_id, []))

    def _parse_chatwoot_messages(self, data: dict[str, Any]) -> List[ChatTurn]:
        """Parse Chatwoot message payload into ChatTurn objects."""
        payload = data.get("payload", [])
        turns: List[ChatTurn] = []
        i = 0
        while i < len(payload):
            msg = payload[i]
            if msg.get("sender_type") == "contact" or msg.get("message_type") == 0:
                question = msg.get("content") or ""
                answer = ""
                # Look for the next non-contact message as the answer
                if i + 1 < len(payload):
                    next_msg = payload[i + 1]
                    if next_msg.get("sender_type") != "contact":
                        answer = next_msg.get("content") or ""
                        i += 1
                turns.append(
                    ChatTurn(
                        question=question,
                        answer=answer,
                        timestamp=datetime.now(),
                        source_documents=[],
                    )
                )
            i += 1
        return turns

    async def get_context_string(self, session_id: str) -> str:
        """
        Obtiene el historial formateado como string para incluir en el prompt.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            String con el historial formateado
        """
        history = await self.get_history(session_id)
        if not history:
            return ""

        context_parts = []
        for i, turn in enumerate(history, 1):
            context_parts.append(f"Turno {i}:")
            context_parts.append(f"Usuario: {turn.question}")
            context_parts.append(f"Asistente: {turn.answer}")
            if turn.source_documents:
                context_parts.append(f"Fuentes: {', '.join(turn.source_documents)}")
            context_parts.append("")  # Línea vacía entre turnos

        return "\n".join(context_parts).strip()

    async def clear_session(self, session_id: str) -> None:
        """
        Elimina una sesión.

        Args:
            session_id: Identificador único de la sesión
        """
        if self._redis is not None:
            try:
                await self._redis.delete(self._history_key(session_id))
                await self._redis.delete(self._profile_key(session_id))
                await self._redis.delete(self._tokens_key(session_id))
                # Remove from mapping hashes
                conv_id = await self._redis.hget(
                    self._mapping_session_key(), session_id
                )
                if conv_id:
                    await self._redis.hdel(self._mapping_session_key(), session_id)
                    await self._redis.hdel(self._mapping_conversation_key(), conv_id)
            except Exception as exc:
                logger.warning("Redis clear_session failed: %s", exc)

        with self._lock:
            conv_id = self._conversation_map.pop(session_id, None)
            if conv_id is not None:
                self._reverse_map.pop(conv_id, None)
            self._sessions.pop(session_id, None)
            self._profiles.pop(session_id, None)
            self._token_totals.pop(session_id, None)

    async def set_user_profile(self, session_id: str, profile: str) -> None:
        """
        Almacena el perfil de usuario para una sesión.

        Args:
            session_id: Identificador único de la sesión
            profile: Perfil de usuario (novato, intermedio, experto)
        """
        if self._redis is not None:
            try:
                await self._redis.set(
                    self._profile_key(session_id), profile, ttl=self._TTL_SECONDS
                )
                return
            except Exception as exc:
                logger.warning("Redis set_user_profile failed, using memory: %s", exc)

        with self._lock:
            self._profiles[session_id] = profile

    async def get_user_profile(self, session_id: str) -> Optional[str]:
        """
        Obtiene el perfil de usuario de una sesión.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            El perfil de usuario si existe, None en caso contrario
        """
        if self._redis is not None:
            try:
                result = await self._redis.get(self._profile_key(session_id))
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("Redis get_user_profile failed, using memory: %s", exc)

        with self._lock:
            return self._profiles.get(session_id)

    async def add_token_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        """Acumula el uso de tokens para una sesión.

        Args:
            session_id: Identificador único de la sesión.
            input_tokens: Tokens de entrada a acumular.
            output_tokens: Tokens de salida a acumular.
            total_tokens: Total de tokens a acumular.
        """
        if self._redis is not None:
            try:
                key = self._tokens_key(session_id)
                # For accumulation we read current values first, then write back
                current = await self._redis.hgetall(key)
                new_input = int(current.get("input_tokens", 0)) + input_tokens
                new_output = int(current.get("output_tokens", 0)) + output_tokens
                new_total = int(current.get("total_tokens", 0)) + total_tokens
                await self._redis.hset(key, "input_tokens", str(new_input))
                await self._redis.hset(key, "output_tokens", str(new_output))
                await self._redis.hset(key, "total_tokens", str(new_total))
                await self._redis.expire(key, self._TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("Redis add_token_usage failed, using memory: %s", exc)

        with self._lock:
            if session_id not in self._token_totals:
                self._token_totals[session_id] = TokenTotals()
            self._token_totals[session_id].input_tokens += input_tokens
            self._token_totals[session_id].output_tokens += output_tokens
            self._token_totals[session_id].total_tokens += total_tokens

    async def get_token_totals(self, session_id: str) -> TokenTotals:
        """Obtiene los totales de tokens acumulados de una sesión.

        Args:
            session_id: Identificador único de la sesión.

        Returns:
            TokenTotals con los valores acumulados, o TokenTotals() en ceros
            si la sesión no existe.
        """
        if self._redis is not None:
            try:
                result = await self._redis.hgetall(self._tokens_key(session_id))
                if result:
                    return TokenTotals(
                        input_tokens=int(result.get("input_tokens", 0)),
                        output_tokens=int(result.get("output_tokens", 0)),
                        total_tokens=int(result.get("total_tokens", 0)),
                    )
            except Exception as exc:
                logger.warning("Redis get_token_totals failed, using memory: %s", exc)

        with self._lock:
            return self._token_totals.get(session_id, TokenTotals())

    def get_session_count(self) -> int:
        """
        Obtiene el número de sesiones activas.

        Returns:
            Número de sesiones activas
        """
        return len(self._sessions)

    async def map_conversation(self, session_id: str, conversation_id: str) -> None:
        """Almacena el mapeo session_id ↔ conversation_id.

        Args:
            session_id: Identificador de sesión interno.
            conversation_id: Identificador de conversación en Chatwoot.
        """
        if self._redis is not None:
            try:
                await self._redis.hset(
                    self._mapping_session_key(), session_id, conversation_id
                )
                await self._redis.hset(
                    self._mapping_conversation_key(), conversation_id, session_id
                )
                return
            except Exception as exc:
                logger.warning("Redis map_conversation failed, using memory: %s", exc)

        with self._lock:
            self._conversation_map[session_id] = conversation_id
            self._reverse_map[conversation_id] = session_id

    async def get_conversation_id(self, session_id: str) -> Optional[str]:
        """Obtiene el conversation_id asociado a un session_id.

        Args:
            session_id: Identificador de sesión interno.

        Returns:
            conversation_id si existe, None en caso contrario.
        """
        if self._redis is not None:
            try:
                result = await self._redis.hget(self._mapping_session_key(), session_id)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(
                    "Redis get_conversation_id failed, using memory: %s", exc
                )

        with self._lock:
            return self._conversation_map.get(session_id)

    async def get_session_id(self, conversation_id: str) -> Optional[str]:
        """Obtiene el session_id asociado a un conversation_id.

        Args:
            conversation_id: Identificador de conversación en Chatwoot.

        Returns:
            session_id si existe, None en caso contrario.
        """
        if self._redis is not None:
            try:
                result = await self._redis.hget(
                    self._mapping_conversation_key(), conversation_id
                )
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("Redis get_session_id failed, using memory: %s", exc)

        with self._lock:
            return self._reverse_map.get(conversation_id)


# Instancia global del gestor de sesiones (sin Redis por defecto para compatibilidad)
session_manager = SessionManager()
