"""
Unit tests for the EscalationDecisionTree module.
"""

import pytest

from backend.app.escalation_tree import (
    EscalationAction,
    EscalationDecision,
    EscalationDecisionTree,
    default_escalation_tree,
)


class TestEscalationDecisionTree:
    """Tests for EscalationDecisionTree class."""

    def test_faq_intent_no_escalation(self) -> None:
        """Test that FAQ intent never escalates."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="FAQ",
            confidence=0.9,
            user_message="¿Qué es un panel solar?",
        )

        assert decision.escalate is False
        assert decision.action == EscalationAction.NO_ESCALATE

    def test_escalate_quote_intent_escalates(self) -> None:
        """Test that escalate_quote escalates with high confidence."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="escalate_quote",
            confidence=0.9,
            user_message="Necesito una cotización",
        )

        assert decision.escalate is True
        assert decision.action == EscalationAction.ESCALATE

    def test_escalate_technical_intent_escalates(self) -> None:
        """Test that escalate_technical escalates."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="escalate_technical",
            confidence=0.9,
            user_message="Mi inversor tiene un problema",
        )

        assert decision.escalate is True

    def test_escalate_order_intent_escalates(self) -> None:
        """Test that escalate_order escalates."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="escalate_order",
            confidence=0.9,
            user_message="Quiero comprar paneles",
        )

        assert decision.escalate is True

    def test_low_confidence_prevents_escalation(self) -> None:
        """Test that low confidence prevents escalation for escalate_ intents."""
        tree = EscalationDecisionTree(confidence_threshold=0.7)
        decision = tree.decide(
            intent_type="escalate_quote",
            confidence=0.3,
            user_message="¿Cuánto cuesta?",
        )

        assert decision.escalate is False

    def test_product_info_simple_query_no_escalation(self) -> None:
        """Test that simple product_info queries don't escalate."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="product_info",
            confidence=0.8,
            user_message="¿Qué potencia tiene el panel?",
        )

        assert decision.escalate is False

    def test_product_info_comparison_escalates(self) -> None:
        """Test that product comparison queries escalate."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="product_info",
            confidence=0.8,
            user_message="¿Cuál es mejor, el panel A o el B?",
        )

        assert decision.escalate is True

    def test_product_info_recommendation_escalates(self) -> None:
        """Test that recommendation queries escalate."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="product_info",
            confidence=0.8,
            user_message="¿Cuál me recomiendan para mi techo?",
        )

        assert decision.escalate is True

    def test_unknown_intent_no_escalation(self) -> None:
        """Test that unknown intents default to no escalation."""
        tree = EscalationDecisionTree()
        decision = tree.decide(
            intent_type="unknown_type",
            confidence=0.5,
            user_message="Some message",
        )

        assert decision.escalate is False

    def test_complexity_score_calculation(self) -> None:
        """Test complexity score calculation."""
        tree = EscalationDecisionTree()

        # High complexity
        result_high = tree._calculate_complexity(
            "¿Cuál es mejor, el inversor Fronius o el Huawei?"
        )
        assert result_high >= 0.6

        # Low complexity
        result_low = tree._calculate_complexity("¿Qué potencia tiene?")
        assert result_low < 0.6

    def test_should_escalate_method(self) -> None:
        """Test the convenience should_escalate method."""
        tree = EscalationDecisionTree()

        assert tree.should_escalate("FAQ", 0.9, "Pregunta general") is False
        assert tree.should_escalate("escalate_quote", 0.9, "Quiero cotización") is True

    def test_default_instance_exists(self) -> None:
        """Test that default_escalation_tree instance exists."""
        assert default_escalation_tree is not None
        assert isinstance(default_escalation_tree, EscalationDecisionTree)


class TestEscalationDecision:
    """Tests for EscalationDecision dataclass."""

    def test_decision_fields(self) -> None:
        """Test EscalationDecision fields."""
        decision = EscalationDecision(
            escalate=True,
            action=EscalationAction.ESCALATE,
            confidence=0.95,
            reason="Test reason",
            intent_type="escalate_quote",
        )

        assert decision.escalate is True
        assert decision.confidence == 0.95
        assert decision.reason == "Test reason"
        assert decision.intent_type == "escalate_quote"

    def test_decision_with_complexity(self) -> None:
        """Test EscalationDecision with complexity score."""
        decision = EscalationDecision(
            escalate=False,
            action=EscalationAction.NO_ESCALATE,
            confidence=0.8,
            reason="Low complexity",
            intent_type="product_info",
            complexity_score=0.3,
        )

        assert decision.complexity_score == 0.3


class TestEscalationAction:
    """Tests for EscalationAction enum."""

    def test_enum_values(self) -> None:
        """Test EscalationAction enum values."""
        assert EscalationAction.ESCALATE.value == "escalate"
        assert EscalationAction.NO_ESCALATE.value == "no_escalate"
        assert EscalationAction.NEEDS_MORE_INFO.value == "needs_more_info"
        assert EscalationAction.CHECK_COMPLEXITY.value == "check_complexity"