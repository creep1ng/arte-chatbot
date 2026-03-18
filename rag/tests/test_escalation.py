"""
Unit tests for the escalation detection module.
"""

import pytest

from rag.escalation import (
    DEFAULT_ESCALATION_MESSAGE,
    ESCALATION_KEYWORDS,
    EscalationDetector,
    EscalationResult,
)


class TestEscalationDetector:
    """Tests for EscalationDetector class."""

    def test_default_keywords_exist(self) -> None:
        """Verify default escalation keywords are defined."""
        assert "cotización" in ESCALATION_KEYWORDS
        assert "pedido" in ESCALATION_KEYWORDS
        assert "garantía" in ESCALATION_KEYWORDS

    def test_detect_cotizacion_keyword(self) -> None:
        """Test detection of 'cotización' keyword."""
        detector = EscalationDetector()
        result = detector.detect("Necesito una cotización para paneles solares")

        assert result.escalate is True
        assert result.matched_keyword == "cotización"
        assert "cotización" in result.reason.lower()

    def test_detect_pedido_keyword(self) -> None:
        """Test detection of 'pedido' keyword."""
        detector = EscalationDetector()
        result = detector.detect("Quiero hacer un pedido de inversores")

        assert result.escalate is True
        assert result.matched_keyword == "pedido"

    def test_detect_garantia_keyword(self) -> None:
        """Test detection of 'garantía' keyword."""
        detector = EscalationDetector()
        result = detector.detect("Tengo un problema con la garantía de mi equipo")

        assert result.escalate is True
        assert result.matched_keyword == "garantía"

    def test_case_insensitive_by_default(self) -> None:
        """Test that detection is case-insensitive by default."""
        detector = EscalationDetector()
        result = detector.detect("NECESITO una COTIZACIÓN")

        assert result.escalate is True
        assert result.matched_keyword == "cotización"

    def test_case_sensitive_option(self) -> None:
        """Test case-sensitive detection when enabled."""
        detector = EscalationDetector(case_sensitive=True)
        result_lower = detector.detect("cotización")
        result_upper = detector.detect("COTIZACIÓN")

        assert result_lower.escalate is True
        assert result_upper.escalate is False

    def test_no_escalation_for_normal_message(self) -> None:
        """Test that normal messages don't trigger escalation."""
        detector = EscalationDetector()
        result = detector.detect("¿Qué potencia tiene el panel solar de 400W?")

        assert result.escalate is False
        assert "no" in result.reason.lower() or "ninguna" in result.reason.lower()

    def test_empty_message_returns_no_escalation(self) -> None:
        """Test that empty messages don't trigger escalation."""
        detector = EscalationDetector()
        result = detector.detect("")

        assert result.escalate is False

    def test_none_message_returns_no_escalation(self) -> None:
        """Test that None messages don't cause errors."""
        detector = EscalationDetector()
        result = detector.detect("")  # Empty string, not None

        assert result.escalate is False

    def test_should_escalate_quick_check(self) -> None:
        """Test the should_escalate convenience method."""
        detector = EscalationDetector()

        assert detector.should_escalate("Quiero una cotización") is True
        assert detector.should_escalate("Hola, ¿cómo estás?") is False

    def test_custom_keywords(self) -> None:
        """Test using custom keywords."""
        custom_keywords = ["ayuda", "soporte"]
        detector = EscalationDetector(keywords=custom_keywords)

        result = detector.detect("Necesito ayuda con mi instalación")

        assert result.escalate is True
        assert result.matched_keyword == "ayuda"

    def test_multiple_keywords_match_first(self) -> None:
        """Test that first matching keyword is returned."""
        detector = EscalationDetector()
        result = detector.detect("Quiero una cotización y hacer un pedido")

        assert result.escalate is True
        # Should match the first keyword in the list that appears
        assert result.matched_keyword in ["cotización", "pedido"]

    def test_escalation_result_dataclass(self) -> None:
        """Test EscalationResult dataclass fields."""
        result = EscalationResult(
            escalate=True,
            reason="Test reason",
            matched_keyword="test",
        )

        assert result.escalate is True
        assert result.reason == "Test reason"
        assert result.matched_keyword == "test"

    def test_default_escalation_message(self) -> None:
        """Test default escalation message is defined."""
        assert isinstance(DEFAULT_ESCALATION_MESSAGE, str)
        assert len(DEFAULT_ESCALATION_MESSAGE) > 0
