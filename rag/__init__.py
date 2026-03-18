"""
ARTE Chatbot RAG Package

Core module for Retrieval-Augmented Generation including
escalation detection and RAG pipeline components.
"""

from rag.escalation import (
    DEFAULT_ESCALATION_MESSAGE,
    ESCALATION_KEYWORDS,
    EscalationDetector,
    EscalationResult,
    default_detector,
)

__all__ = [
    "DEFAULT_ESCALATION_MESSAGE",
    "ESCALATION_KEYWORDS",
    "EscalationDetector",
    "EscalationResult",
    "default_detector",
]
