"""
Session manager for tracking conversation turns.
"""

from typing import Any


class SessionManager:
    """Manages conversation history per session."""

    def __init__(self):
        """Initialize session storage."""
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Add a turn to the session history.

        Args:
            session_id: Unique session identifier.
            role: Role of the speaker ('user' or 'assistant').
            content: Content of the message.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        self._sessions[session_id].append({"role": role, "content": content})

    def get_context_string(self, session_id: str) -> str:
        """Get the full context as a formatted string for LLM context.

        Args:
            session_id: Unique session identifier.

        Returns:
            Formatted string of conversation history or empty string if no history.
        """
        if session_id not in self._sessions:
            return ""

        messages = self._sessions[session_id]
        if not messages:
            return ""

        context_parts = []
        for turn in messages:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            context_parts.append(f"{role.upper()}: {content}")

        return "\n\n".join(context_parts)

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get raw message list for a session.

        Args:
            session_id: Unique session identifier.

        Returns:
            List of message dicts for the session, or empty list if not found.
        """
        return self._sessions.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        """Clear all history for a session.

        Args:
            session_id: Unique session identifier.
        """
        if session_id in self._sessions:
            self._sessions[session_id] = []
