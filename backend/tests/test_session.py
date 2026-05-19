"""Unit tests for the synchronous session management service."""

import threading
from datetime import datetime

from backend.app.session import SessionManager, TokenTotals


class TestSessionManagerInitialization:
    """Tests for SessionManager initialization."""

    def test_session_manager_initialization(self) -> None:
        sm = SessionManager()
        assert sm.max_turns == 20
        assert sm.sessions == {}
        assert sm.token_totals == {}

    def test_session_manager_custom_max_turns(self) -> None:
        sm = SessionManager(max_turns=5)
        assert sm.max_turns == 5


class TestHistory:
    """Tests for adding and retrieving conversation turns."""

    def test_add_turn_creates_new_session(self) -> None:
        sm = SessionManager()
        sm.add_turn("s1", "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])

        history = sm.get_history("s1")
        assert len(history) == 1
        assert history[0].question == "¿Qué es el solar?"
        assert history[0].answer == "Es energía del sol"
        assert history[0].source_documents == ["doc1.pdf"]
        assert isinstance(history[0].timestamp, datetime)

    def test_max_turns_limit(self) -> None:
        sm = SessionManager(max_turns=2)
        for index in range(4):
            sm.add_turn("s1", f"Pregunta {index}", f"Respuesta {index}")

        history = sm.get_history("s1")
        assert len(history) == 2
        assert history[0].question == "Pregunta 2"
        assert history[1].question == "Pregunta 3"

    def test_get_history_empty_session(self) -> None:
        assert SessionManager().get_history("missing") == []

    def test_get_context_string(self) -> None:
        sm = SessionManager()
        sm.add_turn("s1", "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])

        context = sm.get_context_string("s1")

        assert "Turno 1:" in context
        assert "Usuario: ¿Qué es el solar?" in context
        assert "Asistente: Es energía del sol" in context
        assert "Fuentes: doc1.pdf" in context

    def test_get_context_string_empty_session(self) -> None:
        assert SessionManager().get_context_string("missing") == ""

    def test_clear_session(self) -> None:
        sm = SessionManager()
        sm.add_turn("s1", "Pregunta", "Respuesta")
        sm.set_user_profile("s1", "novato")
        sm.add_token_usage("s1", 100, 50, 150)

        sm.clear_session("s1")

        assert sm.get_history("s1") == []
        assert sm.get_user_profile("s1") is None
        assert sm.get_token_totals("s1").total_tokens == 0

    def test_get_session_count(self) -> None:
        sm = SessionManager()
        assert sm.get_session_count() == 0

        sm.add_turn("s1", "Pregunta 1", "Respuesta 1")
        sm.add_turn("s2", "Pregunta 2", "Respuesta 2")
        sm.add_turn("s1", "Pregunta 3", "Respuesta 3")

        assert sm.get_session_count() == 2
        sm.clear_session("s1")
        assert sm.get_session_count() == 1


class TestTokenTotalsModel:
    """Tests for the TokenTotals Pydantic model."""

    def test_token_totals_defaults_to_zero(self) -> None:
        totals = TokenTotals()
        assert totals.input_tokens == 0
        assert totals.output_tokens == 0
        assert totals.total_tokens == 0

    def test_token_totals_with_values(self) -> None:
        totals = TokenTotals(input_tokens=100, output_tokens=50, total_tokens=150)
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.total_tokens == 150


class TestTokenUsage:
    """Tests for SessionManager token accounting."""

    def test_add_token_usage_accumulates(self) -> None:
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)
        sm.add_token_usage("s1", 200, 100, 300)

        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150
        assert totals.total_tokens == 450

    def test_add_token_usage_thread_safe(self) -> None:
        sm = SessionManager()
        errors: list[Exception] = []

        def add_tokens() -> None:
            try:
                for _ in range(100):
                    sm.add_token_usage("s1", 1, 1, 2)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_tokens) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 1000
        assert totals.output_tokens == 1000
        assert totals.total_tokens == 2000

    def test_get_token_totals_returns_zeroed_for_missing_session(self) -> None:
        assert SessionManager().get_token_totals("missing").total_tokens == 0

    def test_clear_session_removes_token_totals(self) -> None:
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)
        sm.clear_session("s1")
        assert sm.get_token_totals("s1").total_tokens == 0
