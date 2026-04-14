"""
Servicio de gestión de sesiones para el chatbot.
Almacena el historial de conversaciones por session_id.
"""

from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
import threading


class ChatTurn(BaseModel):
    """Representa un turno en la conversación."""

    question: str
    answer: str
    timestamp: datetime
    source_documents: List[str] = []


class SessionManager:
    """Gestiona las sesiones de conversación."""

    def __init__(self, max_turns: int = 20):
        self.sessions: Dict[str, List[ChatTurn]] = {}
        self.max_turns = max_turns
        self._lock = threading.Lock()

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

    def get_session_count(self) -> int:
        """
        Obtiene el número de sesiones activas.

        Returns:
            Número de sesiones activas
        """
        return len(self.sessions)


# Instancia global del gestor de sesiones
session_manager = SessionManager()
