"""
Servicio de gestión de sesiones para el chatbot.
Almacena el historial de conversaciones por session_id.
"""

from datetime import datetime
import threading
from typing import Dict, List, Optional

from pydantic import BaseModel


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

    def __init__(self, max_turns: int = 20):
        self.sessions: Dict[str, List[ChatTurn]] = {}
        self.profiles: Dict[str, str] = {}
        self.token_totals: Dict[str, TokenTotals] = {}
        self.intent_counts: Dict[str, int] = {}
        self.escalation_count = 0
        self.metric_turn_count = 0
        self.session_owners: Dict[str, str] = {}
        self.max_turns = max_turns
        self._lock = threading.Lock()

    def bind_session(self, session_id: str, owner: str) -> None:
        """Bind a session to an authenticated principal."""
        with self._lock:
            self.session_owners[session_id] = owner

    def is_session_owner(self, session_id: str, owner: str) -> bool:
        """Return whether the session is owned by the given principal."""
        with self._lock:
            return self.session_owners.get(session_id) == owner

    def has_session_owner(self, session_id: str) -> bool:
        """Return whether the backend has emitted/bound the session."""
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
        with self._lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = []

            turn = ChatTurn(
                question=question,
                answer=answer,
                timestamp=datetime.now(),
                source_documents=source_documents or [],
            )

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
        return self.profiles.get(session_id)

    def add_token_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        intent_type: Optional[str] = None,
        escalate: Optional[bool] = None,
    ) -> None:
        """Acumula el uso de tokens para una sesión.

        Thread-safe: opera bajo el mismo ``_lock`` que el resto del gestor.

        Args:
            session_id: Identificador único de la sesión.
            input_tokens: Tokens de entrada a acumular.
            output_tokens: Tokens de salida a acumular.
            total_tokens: Total de tokens a acumular.
            intent_type: Intent opcional del turno para métricas en memoria.
            escalate: Estado opcional de escalamiento para métricas en memoria.
        """
        with self._lock:
            if session_id not in self.token_totals:
                self.token_totals[session_id] = TokenTotals()
            self.token_totals[session_id].input_tokens += input_tokens
            self.token_totals[session_id].output_tokens += output_tokens
            self.token_totals[session_id].total_tokens += total_tokens
            if intent_type is not None:
                self.intent_counts[intent_type] = (
                    self.intent_counts.get(intent_type, 0) + 1
                )
            if escalate is not None:
                self.metric_turn_count += 1
                if escalate:
                    self.escalation_count += 1

    def get_token_totals(self, session_id: str) -> TokenTotals:
        """Obtiene los totales de tokens acumulados de una sesión.

        Args:
            session_id: Identificador único de la sesión.

        Returns:
            TokenTotals con los valores acumulados, o TokenTotals() en ceros
            si la sesión no existe.
        """
        return self.token_totals.get(session_id, TokenTotals())

    def get_session_count(self) -> int:
        """
        Obtiene el número de sesiones activas.

        Returns:
            Número de sesiones activas
        """
        return len(self.sessions)

    def get_all_token_totals(self) -> TokenTotals:
        """Obtiene los totales de tokens agregados de todas las sesiones.

        Returns:
            TokenTotals con la suma de consumo de todas las sesiones activas.
        """
        with self._lock:
            return TokenTotals(
                input_tokens=sum(t.input_tokens for t in self.token_totals.values()),
                output_tokens=sum(t.output_tokens for t in self.token_totals.values()),
                total_tokens=sum(t.total_tokens for t in self.token_totals.values()),
            )

    def get_intent_distribution(self) -> Dict[str, int]:
        """Obtiene la distribución de intents acumulada en memoria.

        Returns:
            Copia del contador de intents por tipo.
        """
        with self._lock:
            return dict(self.intent_counts)

    def get_escalation_rate(self) -> float:
        """Calcula la tasa de escalamiento acumulada en memoria.

        Returns:
            Proporción de turnos escalados entre 0.0 y 1.0.
        """
        with self._lock:
            if self.metric_turn_count == 0:
                return 0.0
            return self.escalation_count / self.metric_turn_count


# Instancia global del gestor de sesiones
session_manager = SessionManager()
