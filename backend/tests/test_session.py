"""
Unit tests for the session management service.
"""

import asyncio
import pytest
from datetime import datetime
from backend.app.session import SessionManager


class TestSessionManagerInitialization:
    """Tests for SessionManager initialization."""

    def test_session_manager_initialization(self):
        """Test that SessionManager initializes with correct default values."""
        sm = SessionManager()
        assert sm.max_turns == 20

    def test_session_manager_custom_max_turns(self):
        """Test that SessionManager accepts custom max_turns."""
        sm = SessionManager(max_turns=5)
        assert sm.max_turns == 5


class TestAddTurn:
    """Tests for adding conversation turns."""

    @pytest.mark.asyncio
    async def test_add_turn_creates_new_session(self):
        """Test that adding a turn creates a new session."""
        sm = SessionManager()
        session_id = "test-session-1"

        await sm.add_turn(
            session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"]
        )

        history = await sm.get_history(session_id)
        assert len(history) == 1

        turn = history[0]
        assert turn.question == "¿Qué es el solar?"
        assert turn.answer == "Es energía del sol"
        assert turn.source_documents == ["doc1.pdf"]
        assert isinstance(turn.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_add_multiple_turns(self):
        """Test adding multiple turns to the same session."""
        sm = SessionManager()
        session_id = "test-session-2"

        await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
        await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
        await sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")

        history = await sm.get_history(session_id)
        assert len(history) == 3
        assert history[0].question == "Pregunta 1"
        assert history[1].question == "Pregunta 2"
        assert history[2].question == "Pregunta 3"

    @pytest.mark.asyncio
    async def test_max_turns_limit(self):
        """Test that only the last max_turns are kept."""
        sm = SessionManager(max_turns=2)
        session_id = "test-session-3"

        # Añadir 4 turnos
        await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
        await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
        await sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")
        await sm.add_turn(session_id, "Pregunta 4", "Respuesta 4")

        # Solo deberían quedar los últimos 2
        history = await sm.get_history(session_id)
        assert len(history) == 2
        assert history[0].question == "Pregunta 3"
        assert history[1].question == "Pregunta 4"


class TestGetHistory:
    """Tests for retrieving session history."""

    @pytest.mark.asyncio
    async def test_get_history(self):
        """Test getting history for a session."""
        sm = SessionManager()
        session_id = "test-session-4"

        await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
        await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")

        history = await sm.get_history(session_id)
        assert len(history) == 2
        assert history[0].question == "Pregunta 1"
        assert history[1].question == "Pregunta 2"

    @pytest.mark.asyncio
    async def test_get_history_empty_session(self):
        """Test getting history for a non-existent session."""
        sm = SessionManager()
        history = await sm.get_history("non-existent-session")
        assert history == []


class TestGetContextString:
    """Tests for formatted context string."""

    @pytest.mark.asyncio
    async def test_get_context_string(self):
        """Test getting formatted context string."""
        sm = SessionManager()
        session_id = "test-session-5"

        await sm.add_turn(
            session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"]
        )
        await sm.add_turn(
            session_id, "¿Y el eólico?", "Es energía del viento", ["doc2.pdf"]
        )

        context = await sm.get_context_string(session_id)
        assert "Turno 1:" in context
        assert "Usuario: ¿Qué es el solar?" in context
        assert "Asistente: Es energía del sol" in context
        assert "Fuentes: doc1.pdf" in context
        assert "Turno 2:" in context
        assert "Usuario: ¿Y el eólico?" in context
        assert "Asistente: Es energía del viento" in context
        assert "Fuentes: doc2.pdf" in context

    @pytest.mark.asyncio
    async def test_get_context_string_empty_session(self):
        """Test getting context string for empty session."""
        sm = SessionManager()
        context = await sm.get_context_string("empty-session")
        assert context == ""


class TestClearSession:
    """Tests for clearing session data."""

    @pytest.mark.asyncio
    async def test_clear_session(self):
        """Test clearing a session clears turns, profiles, and token totals."""
        sm = SessionManager()
        session_id = "test-session-6"

        await sm.add_turn(session_id, "Pregunta", "Respuesta")
        await sm.set_user_profile(session_id, "novato")
        await sm.add_token_usage(session_id, 100, 50, 150)
        history = await sm.get_history(session_id)
        assert len(history) == 1
        totals = await sm.get_token_totals(session_id)
        assert totals.total_tokens == 150

        await sm.clear_session(session_id)
        assert await sm.get_history(session_id) == []
        assert await sm.get_user_profile(session_id) is None
        totals = await sm.get_token_totals(session_id)
        assert totals.total_tokens == 0

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session(self):
        """Test clearing a non-existent session (should not raise error)."""
        sm = SessionManager()
        # No debería lanzar excepción
        await sm.clear_session("non-existent-session")

    @pytest.mark.asyncio
    async def test_get_session_count(self):
        """Test getting the number of active sessions."""
        sm = SessionManager()
        assert sm.get_session_count() == 0

        await sm.add_turn("session-1", "Pregunta 1", "Respuesta 1")
        assert sm.get_session_count() == 1

        await sm.add_turn("session-2", "Pregunta 2", "Respuesta 2")
        assert sm.get_session_count() == 2

        await sm.add_turn("session-1", "Pregunta 3", "Respuesta 3")  # Misma sesión
        assert sm.get_session_count() == 2  # Aún 2 sesiones

        await sm.clear_session("session-1")
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

    @pytest.mark.asyncio
    async def test_add_token_usage_creates_entry(self) -> None:
        """Test that add_token_usage creates an entry for a new session."""
        sm = SessionManager()
        await sm.add_token_usage("s1", 100, 50, 150)

        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.total_tokens == 150

    @pytest.mark.asyncio
    async def test_add_token_usage_accumulates(self) -> None:
        """Test that repeated calls accumulate token counts."""
        sm = SessionManager()
        await sm.add_token_usage("s1", 100, 50, 150)
        await sm.add_token_usage("s1", 200, 100, 300)

        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150
        assert totals.total_tokens == 450

    @pytest.mark.asyncio
    async def test_add_token_usage_concurrent(self) -> None:
        """Test that concurrent add_token_usage calls accumulate correctly (asyncio)."""
        sm = SessionManager()

        async def add_tokens(n: int) -> None:
            for _ in range(n):
                await sm.add_token_usage("s1", 1, 1, 2)

        await asyncio.gather(*[add_tokens(100) for _ in range(10)])

        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 1000
        assert totals.output_tokens == 1000
        assert totals.total_tokens == 2000


class TestGetTokenTotals:
    """Tests for SessionManager.get_token_totals()."""

    @pytest.mark.asyncio
    async def test_get_token_totals_returns_zeroed_for_missing_session(self) -> None:
        """Test that get_token_totals returns zeroed totals for unknown session."""
        sm = SessionManager()
        totals = await sm.get_token_totals("non-existent")
        assert totals.input_tokens == 0
        assert totals.output_tokens == 0
        assert totals.total_tokens == 0

    @pytest.mark.asyncio
    async def test_get_token_totals_returns_actual_totals(self) -> None:
        """Test that get_token_totals returns accumulated totals."""
        sm = SessionManager()
        await sm.add_token_usage("s1", 50, 25, 75)
        await sm.add_token_usage("s1", 30, 10, 40)

        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 80
        assert totals.output_tokens == 35
        assert totals.total_tokens == 115


class TestClearSessionTokenTotals:
    """Tests verifying clear_session() also clears token_totals."""

    @pytest.mark.asyncio
    async def test_clear_session_removes_token_totals(self) -> None:
        """Test that clearing a session removes its token totals."""
        sm = SessionManager()
        await sm.add_token_usage("s1", 100, 50, 150)
        totals = await sm.get_token_totals("s1")
        assert totals.total_tokens == 150

        await sm.clear_session("s1")
        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 0
        assert totals.total_tokens == 0

    @pytest.mark.asyncio
    async def test_clear_session_token_totals_returns_zero_after_clear(self) -> None:
        """Test that get_token_totals returns zero after clearing."""
        sm = SessionManager()
        await sm.add_token_usage("s1", 100, 50, 150)
        await sm.clear_session("s1")

        totals = await sm.get_token_totals("s1")
        assert totals.input_tokens == 0
        assert totals.total_tokens == 0
