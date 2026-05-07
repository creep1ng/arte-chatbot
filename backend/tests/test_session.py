"""
Unit tests for the session management service.
"""
import pytest
import threading
from datetime import datetime, timedelta
from backend.app.session import SessionManager, ChatTurn


def test_session_manager_initialization():
    """Test that SessionManager initializes with correct default values."""
    sm = SessionManager()
    assert sm.max_turns == 20
    assert sm.sessions == {}
    assert sm.token_totals == {}


def test_session_manager_custom_max_turns():
    """Test that SessionManager accepts custom max_turns."""
    sm = SessionManager(max_turns=5)
    assert sm.max_turns == 5


def test_add_turn_creates_new_session():
    """Test that adding a turn creates a new session."""
    sm = SessionManager()
    session_id = "test-session-1"
    
    sm.add_turn(session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])
    
    assert session_id in sm.sessions
    assert len(sm.sessions[session_id]) == 1
    
    turn = sm.sessions[session_id][0]
    assert turn.question == "¿Qué es el solar?"
    assert turn.answer == "Es energía del sol"
    assert turn.source_documents == ["doc1.pdf"]
    assert isinstance(turn.timestamp, datetime)


def test_add_multiple_turns():
    """Test adding multiple turns to the same session."""
    sm = SessionManager()
    session_id = "test-session-2"
    
    sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")
    
    assert len(sm.sessions[session_id]) == 3
    assert sm.sessions[session_id][0].question == "Pregunta 1"
    assert sm.sessions[session_id][1].question == "Pregunta 2"
    assert sm.sessions[session_id][2].question == "Pregunta 3"


def test_max_turns_limit():
    """Test that only the last max_turns are kept."""
    sm = SessionManager(max_turns=2)
    session_id = "test-session-3"
    
    # Añadir 4 turnos
    sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")
    sm.add_turn(session_id, "Pregunta 4", "Respuesta 4")
    
    # Solo deberían quedar los últimos 2
    assert len(sm.sessions[session_id]) == 2
    assert sm.sessions[session_id][0].question == "Pregunta 3"
    assert sm.sessions[session_id][1].question == "Pregunta 4"


def test_get_history():
    """Test getting history for a session."""
    sm = SessionManager()
    session_id = "test-session-4"
    
    sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    
    history = sm.get_history(session_id)
    assert len(history) == 2
    assert history[0].question == "Pregunta 1"
    assert history[1].question == "Pregunta 2"


def test_get_history_empty_session():
    """Test getting history for a non-existent session."""
    sm = SessionManager()
    history = sm.get_history("non-existent-session")
    assert history == []


def test_get_context_string():
    """Test getting formatted context string."""
    sm = SessionManager()
    session_id = "test-session-5"
    
    sm.add_turn(session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])
    sm.add_turn(session_id, "¿Y el eólico?", "Es energía del viento", ["doc2.pdf"])
    
    context = sm.get_context_string(session_id)
    assert "Turno 1:" in context
    assert "Usuario: ¿Qué es el solar?" in context
    assert "Asistente: Es energía del sol" in context
    assert "Fuentes: doc1.pdf" in context
    assert "Turno 2:" in context
    assert "Usuario: ¿Y el eólico?" in context
    assert "Asistente: Es energía del viento" in context
    assert "Fuentes: doc2.pdf" in context


def test_get_context_string_empty_session():
    """Test getting context string for empty session."""
    sm = SessionManager()
    context = sm.get_context_string("empty-session")
    assert context == ""


def test_clear_session():
    """Test clearing a session clears turns, profiles, and token totals."""
    sm = SessionManager()
    session_id = "test-session-6"

    sm.add_turn(session_id, "Pregunta", "Respuesta")
    sm.set_user_profile(session_id, "novato")
    sm.add_token_usage(session_id, 100, 50, 150)
    assert session_id in sm.sessions
    assert len(sm.sessions[session_id]) == 1
    assert sm.token_totals[session_id].total_tokens == 150

    sm.clear_session(session_id)
    assert session_id not in sm.sessions
    assert session_id not in sm.token_totals


def test_clear_nonexistent_session():
    """Test clearing a non-existent session (should not raise error)."""
    sm = SessionManager()
    # No debería lanzar excepción
    sm.clear_session("non-existent-session")


def test_get_session_count():
    """Test getting the number of active sessions."""
    sm = SessionManager()
    assert sm.get_session_count() == 0
    
    sm.add_turn("session-1", "Pregunta 1", "Respuesta 1")
    assert sm.get_session_count() == 1
    
    sm.add_turn("session-2", "Pregunta 2", "Respuesta 2")
    assert sm.get_session_count() == 2
    
    sm.add_turn("session-1", "Pregunta 3", "Respuesta 3")  # Misma sesión
    assert sm.get_session_count() == 2  # Aún 2 sesiones
    
    sm.clear_session("session-1")
    assert sm.get_session_count() == 1


# --- TokenTotals Tests ---


class TestTokenTotalsModel:
    """Tests for the TokenTotals Pydantic model."""

    def test_token_totals_defaults_to_zero(self) -> None:
        """Test that TokenTotals defaults all fields to 0."""
        from backend.app.session import TokenTotals

        totals = TokenTotals()
        assert totals.input_tokens == 0
        assert totals.output_tokens == 0
        assert totals.total_tokens == 0

    def test_token_totals_with_values(self) -> None:
        """Test that TokenTotals accepts explicit values."""
        from backend.app.session import TokenTotals

        totals = TokenTotals(input_tokens=100, output_tokens=50, total_tokens=150)
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.total_tokens == 150


class TestAddTokenUsage:
    """Tests for SessionManager.add_token_usage()."""

    def test_add_token_usage_creates_entry(self) -> None:
        """Test that add_token_usage creates an entry for a new session."""
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)

        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.total_tokens == 150

    def test_add_token_usage_accumulates(self) -> None:
        """Test that repeated calls accumulate token counts."""
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)
        sm.add_token_usage("s1", 200, 100, 300)

        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150
        assert totals.total_tokens == 450

    def test_add_token_usage_thread_safe(self) -> None:
        """Test that concurrent add_token_usage calls are thread-safe."""
        sm = SessionManager()
        errors: list[Exception] = []

        def add_tokens(n: int) -> None:
            try:
                for _ in range(n):
                    sm.add_token_usage("s1", 1, 1, 2)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_tokens, args=(100,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 1000
        assert totals.output_tokens == 1000
        assert totals.total_tokens == 2000


class TestGetTokenTotals:
    """Tests for SessionManager.get_token_totals()."""

    def test_get_token_totals_returns_zeroed_for_missing_session(self) -> None:
        """Test that get_token_totals returns zeroed totals for unknown session."""
        sm = SessionManager()
        totals = sm.get_token_totals("non-existent")
        assert totals.input_tokens == 0
        assert totals.output_tokens == 0
        assert totals.total_tokens == 0

    def test_get_token_totals_returns_actual_totals(self) -> None:
        """Test that get_token_totals returns accumulated totals."""
        sm = SessionManager()
        sm.add_token_usage("s1", 50, 25, 75)
        sm.add_token_usage("s1", 30, 10, 40)

        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 80
        assert totals.output_tokens == 35
        assert totals.total_tokens == 115


class TestClearSessionTokenTotals:
    """Tests verifying clear_session() also clears token_totals."""

    def test_clear_session_removes_token_totals(self) -> None:
        """Test that clearing a session removes its token totals."""
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)
        assert "s1" in sm.token_totals

        sm.clear_session("s1")
        assert "s1" not in sm.token_totals

    def test_clear_session_token_totals_returns_zero_after_clear(self) -> None:
        """Test that get_token_totals returns zero after clearing."""
        sm = SessionManager()
        sm.add_token_usage("s1", 100, 50, 150)
        sm.clear_session("s1")

        totals = sm.get_token_totals("s1")
        assert totals.input_tokens == 0
        assert totals.total_tokens == 0