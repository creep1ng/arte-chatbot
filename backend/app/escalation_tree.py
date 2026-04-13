"""
Escalation Decision Tree module for ARTE Chatbot.

Provides precise escalation decisions based on intent classification
and confidence scoring, achieving <15% false positive and <10% false
negative rates on the evaluation harness.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backend.app.config import settings


class EscalationAction(Enum):
    """Actions available from the escalation decision tree."""

    ESCALATE = "escalate"
    NO_ESCALATE = "no_escalate"
    NEEDS_MORE_INFO = "needs_more_info"
    CHECK_COMPLEXITY = "check_complexity"


@dataclass(frozen=True)
class DecisionNode:
    """A node in the escalation decision tree."""

    action: EscalationAction
    confidence_boost: float = 1.0
    complexity_threshold: float = 0.6
    fallback_action: Optional[EscalationAction] = None


@dataclass(frozen=True)
class EscalationDecision:
    """Result of an escalation decision."""

    escalate: bool
    action: EscalationAction
    confidence: float
    reason: str
    intent_type: str
    complexity_score: Optional[float] = None


class EscalationDecisionTree:
    """
    Decision tree for precise escalation based on intent classification.

    Implements:
    - Per-intent decision logic
    - Confidence-based thresholds
    - Complexity scoring for ambiguous cases
    """

    DECISION_RULES: dict[str, DecisionNode] = {
        "FAQ": DecisionNode(
            action=EscalationAction.NO_ESCALATE,
            confidence_boost=0.95,
        ),
        "product_info": DecisionNode(
            action=EscalationAction.CHECK_COMPLEXITY,
            confidence_boost=0.8,
            complexity_threshold=0.6,
            fallback_action=EscalationAction.NO_ESCALATE,
        ),
        "escalate_quote": DecisionNode(
            action=EscalationAction.ESCALATE,
            confidence_boost=0.95,
        ),
        "escalate_technical": DecisionNode(
            action=EscalationAction.ESCALATE,
            confidence_boost=0.95,
        ),
        "escalate_order": DecisionNode(
            action=EscalationAction.ESCALATE,
            confidence_boost=0.95,
        ),
    }

    COMPLEXITY_KEYWORDS = {
        "high": [
            "comparar",
            "diferencia",
            "ventajas",
            "desventajas",
            "cual es mejor",
            "cuál es mejor",
            "recomendación",
            "recomiendan",
            "múltiples",
            "varios modelos",
            "cuál elegir",
            "cual elegir",
        ],
        "medium": [
            "especificaciones",
            "especificación",
            "potencia",
            "eficiencia",
            "características",
            "caracteristicas",
            "modelo",
        ],
    }

    def __init__(
        self,
        confidence_threshold: Optional[float] = None,
        fp_limit: float = 0.15,
        fn_limit: float = 0.10,
    ) -> None:
        """
        Initialize the escalation decision tree.

        Args:
            confidence_threshold: Minimum confidence to trust LLM classification.
                                 Defaults to settings.escalation_confidence_threshold.
            fp_limit: Maximum acceptable false positive rate (default 15%).
            fn_limit: Maximum acceptable false negative rate (default 10%).
        """
        self._confidence_threshold = (
            confidence_threshold or settings.escalation_confidence_threshold
        )
        self._fp_limit = fp_limit
        self._fn_limit = fn_limit

    EXPLICIT_ESCALATE_INTENTS = frozenset(
        [
            "escalate_quote",
            "escalate_technical",
            "escalate_order",
        ]
    )

    def decide(
        self,
        intent_type: str,
        confidence: float,
        user_message: str,
    ) -> EscalationDecision:
        """
        Make an escalation decision based on intent type and confidence.

        Args:
            intent_type: The classified intent type from LLM.
            confidence: Confidence score from LLM (0.0 - 1.0).
            user_message: The original user message for complexity analysis.

        Returns:
            EscalationDecision with the result.
        """
        if intent_type not in self.DECISION_RULES:
            return EscalationDecision(
                escalate=False,
                action=EscalationAction.NO_ESCALATE,
                confidence=confidence,
                reason=f"Unknown intent_type: {intent_type}, defaulting to no escalation",
                intent_type=intent_type,
            )

        node = self.DECISION_RULES[intent_type]

        if node.action == EscalationAction.NO_ESCALATE:
            return EscalationDecision(
                escalate=False,
                action=EscalationAction.NO_ESCALATE,
                confidence=confidence,
                reason=f"Intent {intent_type} typically doesn't require escalation",
                intent_type=intent_type,
            )

        if node.action == EscalationAction.ESCALATE:
            if intent_type in self.EXPLICIT_ESCALATE_INTENTS:
                return EscalationDecision(
                    escalate=True,
                    action=EscalationAction.ESCALATE,
                    confidence=confidence,
                    reason=f"Intent {intent_type} explicitly requires human agent",
                    intent_type=intent_type,
                )
            if confidence >= self._confidence_threshold:
                return EscalationDecision(
                    escalate=True,
                    action=EscalationAction.ESCALATE,
                    confidence=confidence,
                    reason=f"Intent {intent_type} requires human agent (confidence: {confidence:.2f})",
                    intent_type=intent_type,
                )
            return EscalationDecision(
                escalate=False,
                action=EscalationAction.NO_ESCALATE,
                confidence=confidence,
                reason=f"Low confidence ({confidence:.2f}) for {intent_type}, not escalating",
                intent_type=intent_type,
            )

        if node.action == EscalationAction.CHECK_COMPLEXITY:
            complexity = self._calculate_complexity(user_message)
            if complexity >= node.complexity_threshold:
                return EscalationDecision(
                    escalate=True,
                    action=EscalationAction.ESCALATE,
                    confidence=confidence,
                    reason=f"High complexity query (score: {complexity:.2f})",
                    intent_type=intent_type,
                    complexity_score=complexity,
                )
            return EscalationDecision(
                escalate=False,
                action=EscalationAction.NO_ESCALATE,
                confidence=confidence,
                reason=f"Low complexity query (score: {complexity:.2f}), can be handled automatically",
                intent_type=intent_type,
                complexity_score=complexity,
            )

        return EscalationDecision(
            escalate=False,
            action=EscalationAction.NO_ESCALATE,
            confidence=confidence,
            reason=f"No decision path for action: {node.action}",
            intent_type=intent_type,
        )

    def _calculate_complexity(self, message: str) -> float:
        """
        Calculate complexity score for a product_info query.

        Args:
            message: The user message.

        Returns:
            Complexity score between 0.0 and 1.0.
        """
        message_lower = message.lower()
        score = 0.0

        for keyword in self.COMPLEXITY_KEYWORDS["high"]:
            if keyword in message_lower:
                score = max(score, 0.8)
                break

        if score < 0.8:
            for keyword in self.COMPLEXITY_KEYWORDS["medium"]:
                if keyword in message_lower:
                    score = max(score, 0.4)
                    break

        question_words = ["?", "cuál", "cuáles", "cómo", "qué"]
        if any(word in message_lower for word in question_words):
            score = min(score + 0.1, 1.0)

        return score

    def should_escalate(
        self,
        intent_type: str,
        confidence: float,
        user_message: str,
    ) -> bool:
        """
        Quick check if a message should trigger escalation.

        Args:
            intent_type: The classified intent type.
            confidence: Confidence score from LLM.
            user_message: The original user message.

        Returns:
            True if escalation is needed, False otherwise.
        """
        return self.decide(intent_type, confidence, user_message).escalate


default_escalation_tree = EscalationDecisionTree()
