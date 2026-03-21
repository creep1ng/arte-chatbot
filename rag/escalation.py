"""
Escalation detection module for ARTE Chatbot.

This module provides keyword-based escalation detection for identifying
when a user query should be routed to a human agent.
"""

from dataclasses import dataclass
from typing import Final

# Spanish keywords that trigger escalation to human agent
ESCALATION_KEYWORDS: Final[list[str]] = [
    "cotización",
    "presupuesto",
    "pedido",
    "garantía",
    "reclamo",
    "queja",
]

# Default escalation message shown to users
DEFAULT_ESCALATION_MESSAGE: Final[
    str
] = "Entiendo que necesitas asistencia personalizada. Un agente de ventas te contactará pronto para ayudarte con tu consulta."


@dataclass(frozen=True)
class EscalationResult:
    """Result of escalation detection."""

    escalate: bool
    reason: str
    matched_keyword: str | None = None


class EscalationDetector:
    """
    Keyword-based escalation detector.

    Detects when a user message contains specific keywords that
    indicate the need for human agent assistance.

    This is a simple rule-based implementation (YAGNI) that will
    be replaced by ML-based classification in a future sprint.
    """

    def __init__(
        self,
        keywords: list[str] | None = None,
        case_sensitive: bool = False,
    ) -> None:
        """
        Initialize the escalation detector.

        Args:
            keywords: Custom list of escalation keywords.
                     Defaults to ESCALATION_KEYWORDS if not provided.
            case_sensitive: Whether keyword matching is case-sensitive.
        """
        self._keywords = keywords if keywords is not None else ESCALATION_KEYWORDS
        self._case_sensitive = case_sensitive

    def detect(self, message: str) -> EscalationResult:
        """
        Detect if a message should trigger escalation.

        Args:
            message: The user message to analyze.

        Returns:
            EscalationResult indicating whether escalation is needed.
        """
        if not message:
            return EscalationResult(
                escalate=False,
                reason="Empty message",
            )

        search_message = (
            message if self._case_sensitive else message.lower()
        )

        for keyword in self._keywords:
            search_keyword = (
                keyword if self._case_sensitive else keyword.lower()
            )

            if search_keyword in search_message:
                return EscalationResult(
                    escalate=True,
                    reason=f"Keyword detected: {keyword}",
                    matched_keyword=keyword,
                )

        return EscalationResult(
            escalate=False,
            reason="No escalation keywords detected",
        )

    def should_escalate(self, message: str) -> bool:
        """
        Quick check if a message should trigger escalation.

        Args:
            message: The user message to analyze.

        Returns:
            True if escalation is needed, False otherwise.
        """
        return self.detect(message).escalate


# Default instance for convenience
default_detector = EscalationDetector()
