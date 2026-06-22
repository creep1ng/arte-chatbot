"""Servicio de gestión de sesiones para el chatbot.

Almacena el historial de conversaciones por session_id.
"""

from datetime import datetime
import threading
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.app.state_repository import (
    ChatbotStateRepository,
    ChatTurn as RepositoryChatTurn,
    TokenTotals as RepositoryTokenTotals,
)


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
    """Gestiona las sesiones de conversación."""

    def __init__(
        self,
        max_turns: int = 20,
        state_repository: Optional[ChatbotStateRepository] = None,
        chatwoot_client: Optional[Any] = None,
    ):
        self.sessions: Dict[str, List[ChatTurn]] = {}
        self.profiles: Dict[str, str] = {}
        self.token_totals: Dict[str, TokenTotals] = {}
        self.session_owners: Dict[str, str] = {}
        self._conversation_map: Dict[str, str] = {}
        self._reverse_conversation_map: Dict[str, str] = {}
        self.max_turns = max_turns
        self.state_repository = state_repository
        self._chatwoot = chatwoot_client
        self._lock = threading.Lock()

    def set_state_repository(
        self, state_repository: Optional[ChatbotStateRepository]
    ) -> None:
        """Configure the durable state repository used outside local memory mode."""
        with self._lock:
            self.state_repository = state_repository

    def bind_session(self, session_id: str, owner: str) -> None:
        """Bind a session to an authenticated principal."""
        if self.state_repository is not None:
            self.state_repository.bind_owner(session_id, owner)
            return
        with self._lock:
            self.session_owners[session_id] = owner

    def is_session_owner(self, session_id: str, owner: str) -> bool:
        """Return whether the session is owned by the given principal."""
        if self.state_repository is not None:
            return self.state_repository.get_owner(session_id) == owner
        with self._lock:
            return self.session_owners.get(session_id) == owner

    def has_session_owner(self, session_id: str) -> bool:
        """Return whether the backend has emitted/bound the session."""
        if self.state_repository is not None:
            return self.state_repository.get_owner(session_id) is not None
        with self._lock:
            return session_id in self.session_owners

    def add_turn(
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
        if self.state_repository is not None:
            self.state_repository.append_turn(
                session_id,
                RepositoryChatTurn(
                    question=turn.question,
                    answer=turn.answer,
                    timestamp=turn.timestamp,
                    source_documents=turn.source_documents,
                ),
            )
            return

        with self._lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = []

            self.sessions[session_id].append(turn)

            # Mantener solo los últimos max_turns turnos
            if len(self.sessions[session_id]) > self.max_turns:
                self.sessions[session_id] = self.sessions[session_id][-self.max_turns :]

    def get_history(self, session_id: str) -> List[ChatTurn]:
        """
        Obtiene el historial de una sesión.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            Lista de turnos de la sesión, ordenados cronológicamente
        """
        if self.state_repository is not None:
            state = self.state_repository.get_session(session_id)
            return [
                ChatTurn(
                    question=turn.question,
                    answer=turn.answer,
                    timestamp=turn.timestamp,
                    source_documents=turn.source_documents,
                )
                for turn in state.turns[-self.max_turns :]
            ]
        return self.sessions.get(session_id, [])

    def get_context_string(self, session_id: str) -> str:
        """
        Obtiene el historial formateado como string para incluir en el prompt.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            String con el historial formateado
        """
        history = self.get_history(session_id)
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

    def clear_session(self, session_id: str) -> None:
        """
        Elimina una sesión.

        Args:
            session_id: Identificador único de la sesión
        """
        if self.state_repository is not None:
            # DynamoDB-backed sessions expire via TTL. Keep this method non-destructive
            # for compatibility with existing local tests and callers.
            return
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
            if session_id in self.profiles:
                del self.profiles[session_id]
            if session_id in self.token_totals:
                del self.token_totals[session_id]
            if session_id in self.session_owners:
                del self.session_owners[session_id]
            conversation_id = self._conversation_map.pop(session_id, None)
            if conversation_id is not None:
                self._reverse_conversation_map.pop(conversation_id, None)

    def set_user_profile(self, session_id: str, profile: str) -> None:
        """
        Almacena el perfil de usuario para una sesión.

        Args:
            session_id: Identificador único de la sesión
            profile: Perfil de usuario (novato, intermedio, experto)
        """
        if self.state_repository is not None:
            self.state_repository.set_user_profile(session_id, profile)
            return
        with self._lock:
            self.profiles[session_id] = profile

    def get_user_profile(self, session_id: str) -> Optional[str]:
        """
        Obtiene el perfil de usuario de una sesión.

        Args:
            session_id: Identificador único de la sesión

        Returns:
            El perfil de usuario si existe, None en caso contrario
        """
        if self.state_repository is not None:
            return self.state_repository.get_session(session_id).profile
        return self.profiles.get(session_id)

    def add_token_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        """Acumula el uso de tokens para una sesión.

        Thread-safe: opera bajo el mismo ``_lock`` que el resto del gestor.

        Args:
            session_id: Identificador único de la sesión.
            input_tokens: Tokens de entrada a acumular.
            output_tokens: Tokens de salida a acumular.
            total_tokens: Total de tokens a acumular.
        """
        if self.state_repository is not None:
            self.state_repository.add_token_usage(
                session_id,
                RepositoryTokenTotals(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                ),
            )
            return
        with self._lock:
            if session_id not in self.token_totals:
                self.token_totals[session_id] = TokenTotals()
            self.token_totals[session_id].input_tokens += input_tokens
            self.token_totals[session_id].output_tokens += output_tokens
            self.token_totals[session_id].total_tokens += total_tokens

    def get_token_totals(self, session_id: str) -> TokenTotals:
        """Obtiene los totales de tokens acumulados de una sesión.

        Args:
            session_id: Identificador único de la sesión.

        Returns:
            TokenTotals con los valores acumulados, o TokenTotals() en ceros
            si la sesión no existe.
        """
        if self.state_repository is not None:
            totals = self.state_repository.get_token_totals(session_id)
            return TokenTotals(
                input_tokens=totals.input_tokens,
                output_tokens=totals.output_tokens,
                total_tokens=totals.total_tokens,
            )
        return self.token_totals.get(session_id, TokenTotals())

    def get_session_count(self) -> int:
        """
        Obtiene el número de sesiones activas.

        Returns:
            Número de sesiones activas
        """
        return len(self.sessions)

    async def get_or_create_session_for_conversation(
        self, conversation_id: str, account_id: int = 1
    ) -> str:
        """Return the session mapped to a Chatwoot conversation, creating it."""
        if self.state_repository is not None:
            existing = self.state_repository.get_chatwoot_session_id(
                conversation_id,
                account_id=account_id,
            )
            if existing is not None:
                return existing
            session_id = str(uuid.uuid4())
            self.state_repository.map_chatwoot_conversation(
                conversation_id,
                session_id,
                account_id=account_id,
            )
            return session_id

        with self._lock:
            existing = self._reverse_conversation_map.get(conversation_id)
            if existing is not None:
                return existing
            session_id = str(uuid.uuid4())
            self._conversation_map[session_id] = conversation_id
            self._reverse_conversation_map[conversation_id] = session_id
            return session_id

    async def get_conversation_for_session(
        self, session_id: str, account_id: int = 1
    ) -> Optional[str]:
        """Return the Chatwoot conversation ID for an internal session."""
        del account_id
        if self.state_repository is not None:
            return self.state_repository.get_chatwoot_conversation_id(session_id)
        with self._lock:
            return self._conversation_map.get(session_id)

    async def map_conversation(self, session_id: str, conversation_id: str) -> None:
        """Backward-compatible async mapping helper."""
        if self.state_repository is not None:
            self.state_repository.map_chatwoot_conversation(conversation_id, session_id)
            return
        with self._lock:
            self._conversation_map[session_id] = conversation_id
            self._reverse_conversation_map[conversation_id] = session_id

    async def get_conversation_id(self, session_id: str) -> Optional[str]:
        """Backward-compatible alias for get_conversation_for_session."""
        return await self.get_conversation_for_session(session_id)

    async def get_session_id(self, conversation_id: str) -> Optional[str]:
        """Return the session mapped to a Chatwoot conversation, if any."""
        if self.state_repository is not None:
            return self.state_repository.get_chatwoot_session_id(conversation_id)
        with self._lock:
            return self._reverse_conversation_map.get(conversation_id)

    async def add_turn_async(
        self,
        session_id: str,
        question: str,
        answer: str,
        source_documents: List[str],
    ) -> None:
        """Async compatibility wrapper around the repository-aware sync API."""
        self.add_turn(session_id, question, answer, source_documents)

    async def get_history_async(
        self, session_id: str, limit: int = 10
    ) -> List[ChatTurn]:
        """Return recent history and optionally hydrate from Chatwoot on misses."""
        history = self.get_history(session_id)[-limit:]
        if history or self._chatwoot is None:
            return history

        conversation_id = await self.get_conversation_for_session(session_id)
        if conversation_id is None:
            return history

        data = await self._chatwoot.fetch_messages(int(conversation_id), limit=limit * 2)
        await self.hydrate_history_from_chatwoot(session_id, data.get("payload", []))
        return self.get_history(session_id)[-limit:]

    async def hydrate_history_from_chatwoot(
        self, session_id: str, messages: List[Dict[str, Any]]
    ) -> None:
        """Transform Chatwoot messages into ChatTurn entries and persist them."""
        turns = self._parse_chatwoot_messages(messages)
        for turn in turns[-self.max_turns :]:
            await self.add_turn_async(
                session_id,
                turn.question,
                turn.answer,
                turn.source_documents,
            )

    def _parse_chatwoot_messages(self, messages: List[Dict[str, Any]]) -> List[ChatTurn]:
        """Parse Chatwoot incoming/outgoing messages into conversation turns."""
        turns: List[ChatTurn] = []
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

    def _is_incoming_message(self, message: Dict[str, Any]) -> bool:
        """Return true for Chatwoot contact/incoming messages."""
        message_type = message.get("message_type")
        sender = message.get("sender")
        sender_type = message.get("sender_type")
        if sender_type is None and isinstance(sender, dict):
            sender_type = sender.get("type")
        return message_type in ("incoming", 0) or sender_type == "contact"


# Instancia global del gestor de sesiones
session_manager = SessionManager()
