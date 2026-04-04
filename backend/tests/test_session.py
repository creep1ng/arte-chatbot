"""
Unit tests for the session management service.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from backend.app.session import SessionManager, ChatTurn


@pytest.mark.asyncio
async def test_session_manager_initialization():
    """Test that SessionManager initializes with correct default values."""
    sm = SessionManager()
    assert sm.max_turns == 3
    assert sm.sessions == {}


@pytest.mark.asyncio
async def test_session_manager_custom_max_turns():
    """Test that SessionManager accepts custom max_turns."""
    sm = SessionManager(max_turns=5)
    assert sm.max_turns == 5


@pytest.mark.asyncio
async def test_add_turn_creates_new_session():
    """Test that adding a turn creates a new session."""
    sm = SessionManager()
    session_id = "test-session-1"
    
    await sm.add_turn(session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])
    
    assert session_id in sm.sessions
    assert len(sm.sessions[session_id]) == 1
    
    turn = sm.sessions[session_id][0]
    assert turn.question == "¿Qué es el solar?"
    assert turn.answer == "Es energía del sol"
    assert turn.source_documents == ["doc1.pdf"]
    assert isinstance(turn.timestamp, datetime)


@pytest.mark.asyncio
async def test_add_multiple_turns():
    """Test adding multiple turns to the same session."""
    sm = SessionManager()
    session_id = "test-session-2"
    
    await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    await sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")
    
    assert len(sm.sessions[session_id]) == 3
    assert sm.sessions[session_id][0].question == "Pregunta 1"
    assert sm.sessions[session_id][1].question == "Pregunta 2"
    assert sm.sessions[session_id][2].question == "Pregunta 3"


@pytest.mark.asyncio
async def test_max_turns_limit():
    """Test that only the last max_turns are kept."""
    sm = SessionManager(max_turns=2)
    session_id = "test-session-3"
    
    # Añadir 4 turnos
    await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    await sm.add_turn(session_id, "Pregunta 3", "Respuesta 3")
    await sm.add_turn(session_id, "Pregunta 4", "Respuesta 4")
    
    # Solo deberían quedar los últimos 2
    assert len(sm.sessions[session_id]) == 2
    assert sm.sessions[session_id][0].question == "Pregunta 3"
    assert sm.sessions[session_id][1].question == "Pregunta 4"


@pytest.mark.asyncio
async def test_get_history():
    """Test getting history for a session."""
    sm = SessionManager()
    session_id = "test-session-4"
    
    await sm.add_turn(session_id, "Pregunta 1", "Respuesta 1")
    await sm.add_turn(session_id, "Pregunta 2", "Respuesta 2")
    
    history = sm.get_history(session_id)
    assert len(history) == 2
    assert history[0].question == "Pregunta 1"
    assert history[1].question == "Pregunta 2"


@pytest.mark.asyncio
async def test_get_history_empty_session():
    """Test getting history for a non-existent session."""
    sm = SessionManager()
    history = sm.get_history("non-existent-session")
    assert history == []


@pytest.mark.asyncio
async def test_get_context_string():
    """Test getting formatted context string."""
    sm = SessionManager()
    session_id = "test-session-5"
    
    await sm.add_turn(session_id, "¿Qué es el solar?", "Es energía del sol", ["doc1.pdf"])
    await sm.add_turn(session_id, "¿Y el eólico?", "Es energía del viento", ["doc2.pdf"])
    
    context = sm.get_context_string(session_id)
    assert "Turno 1:" in context
    assert "Usuario: ¿Qué es el solar?" in context
    assert "Asistente: Es energía del sol" in context
    assert "Fuentes: doc1.pdf" in context
    assert "Turno 2:" in context
    assert "Usuario: ¿Y el eólico?" in context
    assert "Asistente: Es energía del viento" in context
    assert "Fuentes: doc2.pdf" in context


@pytest.mark.asyncio
async def test_get_context_string_empty_session():
    """Test getting context string for empty session."""
    sm = SessionManager()
    context = sm.get_context_string("empty-session")
    assert context == ""


@pytest.mark.asyncio
async def test_clear_session():
    """Test clearing a session."""
    sm = SessionManager()
    session_id = "test-session-6"
    
    await sm.add_turn(session_id, "Pregunta", "Respuesta")
    assert session_id in sm.sessions
    assert len(sm.sessions[session_id]) == 1
    
    await sm.clear_session(session_id)
    assert session_id not in sm.sessions


@pytest.mark.asyncio
async def test_clear_nonexistent_session():
    """Test clearing a non-existent session (should not raise error)."""
    sm = SessionManager()
    # No debería lanzar excepción
    await sm.clear_session("non-existent-session")


@pytest.mark.asyncio
async def test_get_session_count():
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


@pytest.mark.asyncio
async def test_add_turn_concurrency():
    """Test that concurrent add_turn calls are serialized by lock."""
    sm = SessionManager(max_turns=10)  # Increase max_turns to allow 9 concurrent turns
    session_id = "concurrent-session"
    
    async def add_turns(count):
        for i in range(count):
            await sm.add_turn(session_id, f"Q{i}", f"A{i}")
    
    # Run 3 concurrent tasks, each adding 3 turns
    await asyncio.gather(
        add_turns(3),
        add_turns(3),
        add_turns(3),
    )
    
    # Should have 9 turns total, not less
    history = sm.get_history(session_id)
    assert len(history) == 9  # 3 tasks × 3 turns each = 9 turns total
