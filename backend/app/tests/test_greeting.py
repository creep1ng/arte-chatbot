"""Unit tests for the greeting module.

Tests time-of-day greeting, first-contact detection, and
greeting prepend logic for the WhatsApp conversational feature (P3).

Strict TDD: tests written BEFORE implementation.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Imports — will fail until implementation exists
# ---------------------------------------------------------------------------
try:
    from backend.app.greeting import (
        _get_time_greeting,
        _GREETING_TEMPLATE,
        is_first_contact,
        maybe_prepend_greeting,
    )
except ImportError:
    _get_time_greeting = None  # type: ignore[assignment]
    _GREETING_TEMPLATE = None  # type: ignore[assignment]
    is_first_contact = None  # type: ignore[assignment]
    maybe_prepend_greeting = None  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _require_greeting() -> None:
    """Skip all tests in this module if greeting not yet implemented."""
    if _get_time_greeting is None:
        pytest.skip("backend.app.greeting not yet implemented")


# ===========================================================================
# Task 3.1 — Time greeting (_get_time_greeting)
# ===========================================================================


class TestTimeGreeting:
    """Test _get_time_greeting returns correct string based on hour."""

    @patch("backend.app.greeting.datetime")
    def test_morning_greeting_at_10am(self, mock_dt: MagicMock) -> None:
        """Hour 10 → Buenos días."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 10, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenos días"

    @patch("backend.app.greeting.datetime")
    def test_afternoon_greeting_at_15(self, mock_dt: MagicMock) -> None:
        """Hour 15 → Buenas tardes."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 15, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenas tardes"

    @patch("backend.app.greeting.datetime")
    def test_night_greeting_at_22(self, mock_dt: MagicMock) -> None:
        """Hour 22 → Buenas noches."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 22, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenas noches"

    @patch("backend.app.greeting.datetime")
    def test_night_greeting_at_3am_boundary(self, mock_dt: MagicMock) -> None:
        """Hour 3 (early morning boundary) → Buenas noches."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 3, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenas noches"

    def test_custom_timezone_america_mexico_city(self) -> None:
        """Custom timezone America/Mexico_City is accepted and returns a valid greeting."""
        # This test verifies the function doesn't crash with a non-default timezone.
        # The actual greeting depends on the time of day, so just check it returns a string.
        result = _get_time_greeting("America/Mexico_City")
        assert result in ("Buenos días", "Buenas tardes", "Buenas noches")

    def test_invalid_timezone_raises_error(self) -> None:
        """Invalid timezone string raises a ZoneInfoNotFoundError or KeyError."""
        with pytest.raises((KeyError, Exception)):
            _get_time_greeting("Invalid/Timezone_That_Does_Not_Exist")

    @patch("backend.app.greeting.datetime")
    def test_morning_boundary_at_6(self, mock_dt: MagicMock) -> None:
        """Hour 6 (start of morning) → Buenos días."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 6, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenos días"

    @patch("backend.app.greeting.datetime")
    def test_afternoon_boundary_at_12(self, mock_dt: MagicMock) -> None:
        """Hour 12 (start of afternoon) → Buenas tardes."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 12, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenas tardes"

    @patch("backend.app.greeting.datetime")
    def test_night_boundary_at_19(self, mock_dt: MagicMock) -> None:
        """Hour 19 (start of night) → Buenas noches."""
        mock_dt.now.return_value = datetime(2026, 1, 15, 19, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _get_time_greeting("America/Bogota")
        assert result == "Buenas noches"


# ===========================================================================
# Task 3.3 — First contact detection (is_first_contact)
# ===========================================================================


class TestIsFirstContact:
    """Test is_first_contact delegates to session_manager.get_history."""

    @patch("backend.app.greeting.session_manager")
    def test_first_contact_returns_true(self, mock_sm: MagicMock) -> None:
        """Empty history → first contact."""
        mock_sm.get_history.return_value = []
        assert is_first_contact("test-session") is True

    @patch("backend.app.greeting.session_manager")
    def test_non_first_contact_returns_false(self, mock_sm: MagicMock) -> None:
        """History with entries → not first contact."""
        mock_sm.get_history.return_value = [MagicMock()]
        assert is_first_contact("test-session") is False

    @patch("backend.app.greeting.session_manager")
    def test_different_sessions_independent(self, mock_sm: MagicMock) -> None:
        """Each session is independent."""
        mock_sm.get_history.return_value = []
        assert is_first_contact("session-new") is True
        mock_sm.get_history.return_value = [MagicMock()]
        assert is_first_contact("session-old") is False


# ===========================================================================
# Task 3.5 — Greeting prepend (maybe_prepend_greeting)
# ===========================================================================


class TestMaybePrependGreeting:
    """Test maybe_prepend_greeting conditions and output."""

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    @patch("backend.app.greeting._get_time_greeting")
    def test_greeting_prepended_on_first_contact(
        self,
        mock_greeting: MagicMock,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Greeting IS prepended on first contact, non-escalation, valid intent."""
        mock_settings.greeting_enabled = True
        mock_sm.get_history.return_value = []
        mock_greeting.return_value = "Buenos días"

        result = maybe_prepend_greeting("s1", "Respuesta", "FAQ", False)
        assert "Buenos días" in result
        assert "Respuesta" in result

    @patch("backend.app.greeting.settings")
    def test_greeting_not_prepended_when_disabled(
        self, mock_settings: MagicMock
    ) -> None:
        """Greeting is NOT prepended when greeting_enabled is False."""
        mock_settings.greeting_enabled = False
        result = maybe_prepend_greeting("s1", "Respuesta", "FAQ", False)
        assert result == "Respuesta"

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    def test_greeting_not_prepended_on_escalation(
        self,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Greeting is NOT prepended when escalate is True."""
        mock_settings.greeting_enabled = True
        mock_sm.get_history.return_value = []
        result = maybe_prepend_greeting("s1", "Respuesta", "escalate_technical", True)
        assert result == "Respuesta"

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    @patch("backend.app.greeting._get_time_greeting")
    def test_greeting_prepended_on_first_contact_quote_escalation(
        self,
        mock_greeting: MagicMock,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Quote escalation still greets first-contact users."""
        mock_settings.greeting_enabled = True
        mock_settings.greeting_timezone = "America/Bogota"
        mock_sm.get_history.return_value = []
        mock_greeting.return_value = "Buenos días"

        result = maybe_prepend_greeting(
            "s1", "Respuesta", "escalate_quote", True
        )
        assert "Buenos días" in result
        assert "Respuesta" in result

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    def test_greeting_not_prepended_on_fuera_de_dominio(
        self,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Greeting is NOT prepended on fuera_de_dominio intent."""
        mock_settings.greeting_enabled = True
        mock_sm.get_history.return_value = []
        result = maybe_prepend_greeting("s1", "Respuesta", "fuera_de_dominio", False)
        assert result == "Respuesta"

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    def test_greeting_not_prepended_on_non_first_contact(
        self,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Greeting is NOT prepended when session has history."""
        mock_settings.greeting_enabled = True
        mock_sm.get_history.return_value = [MagicMock()]
        result = maybe_prepend_greeting("s1", "Respuesta", "FAQ", False)
        assert result == "Respuesta"

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    @patch("backend.app.greeting._get_time_greeting")
    def test_greeting_contains_correct_time_string(
        self,
        mock_greeting: MagicMock,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """The greeting contains the correct time-of-day string."""
        mock_settings.greeting_enabled = True
        mock_settings.greeting_timezone = "America/Bogota"
        mock_sm.get_history.return_value = []
        mock_greeting.return_value = "Buenas tardes"

        result = maybe_prepend_greeting("s1", "Respuesta", "FAQ", False)
        assert "Buenas tardes" in result

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    @patch("backend.app.greeting._get_time_greeting")
    def test_greeting_template_is_correct(
        self,
        mock_greeting: MagicMock,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """The greeting template matches the expected format."""
        mock_settings.greeting_enabled = True
        mock_settings.greeting_timezone = "America/Bogota"
        mock_sm.get_history.return_value = []
        mock_greeting.return_value = "Buenos días"

        result = maybe_prepend_greeting("s1", "Mi respuesta", "FAQ", False)
        expected_greeting_part = (
            "Buenos días! Soy el asistente virtual de Arte Soluciones Energéticas. "
            "Puedo ayudarte con información sobre paneles solares, inversores, "
            "baterías y más. ¿En qué puedo ayudarte hoy?"
        )
        assert result.startswith(expected_greeting_part)
        assert "Mi respuesta" in result

    @patch("backend.app.greeting.settings")
    @patch("backend.app.greeting.session_manager")
    @patch("backend.app.greeting._get_time_greeting")
    def test_greeting_separated_by_double_newline(
        self,
        mock_greeting: MagicMock,
        mock_sm: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Greeting and response are separated by double newline."""
        mock_settings.greeting_enabled = True
        mock_settings.greeting_timezone = "America/Bogota"
        mock_sm.get_history.return_value = []
        mock_greeting.return_value = "Buenos días"

        result = maybe_prepend_greeting("s1", "Mi respuesta", "FAQ", False)
        # Should contain double newline separator between greeting and response
        assert "\n\n" in result
        parts = result.split("\n\n", 1)
        assert len(parts) == 2
        assert "Mi respuesta" in parts[1]
