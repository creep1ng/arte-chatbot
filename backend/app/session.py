"""Servicio de gestión de sesiones para el chatbot.

Almacena el historial de conversaciones por session_id.
"""

from datetime import datetime
import threading
from typing import Dict, List, Optional

from pydantic import BaseModel

from backend.app.config import settings
from backend.app.context_budget import SelectedContext, select_history
from backend.app.context_budget_config import ContextBudgetConfig
from backend.app.state_repository import (
    ChatbotStateRepository,
    ChatTurn as RepositoryChatTurn,
    TokenTotals as RepositoryTokenTotals,
)
from backend.app.token_counter import TokenCounter


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
    ):
        if max_turns < 1:
            raise ValueError("max_turns must be greater than zero")

        self.sessions: Dict[str, List[ChatTurn]] = {}
        self.profiles: Dict[str, str] = {}
        self.token_totals: Dict[str, TokenTotals] = {}
        self.session_owners: Dict[str, str] = {}
        self.max_turns = max_turns
        self.state_repository = state_repository
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
            state = self.state_repository.get_session(
                session_id, max_turns=self.max_turns
            )
            return [
                ChatTurn(
                    question=turn.question,
                    answer=turn.answer,
                    timestamp=turn.timestamp,
                    source_documents=turn.source_documents,
                )
                for turn in state.turns
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

    def get_budgeted_context(
        self,
        *,
        session_id: str,
        model: str,
        config: ContextBudgetConfig,
        system_prompt: str,
        tools: list[dict[str, object]],
        current_message: str,
        token_counter: Optional[TokenCounter] = None,
    ) -> SelectedContext:
        """Return the newest complete history turns that fit the token budget."""
        return select_history(
            turns=self.get_context_candidates(session_id),
            model=model,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
            current_message=current_message,
            token_counter=token_counter,
        )

    def get_context_candidates(self, session_id: str) -> List[ChatTurn]:
        """Return chronological candidates bounded by the configured turn ceiling."""
        return self.get_history(session_id)[-self.max_turns :]

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


# Instancia global del gestor de sesiones
session_manager = SessionManager(max_turns=settings.context_max_turns)
