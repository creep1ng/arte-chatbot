"""
Hybrid unit and integration tests for the /chat endpoint.

Tests are organized into:
1. Health/root endpoints
2. Unit tests (with AsyncMock for MessageQueue)
3. Integration tests (with real MessageQueue but mocked LLM/S3)
4. Escalation tests
5. Error handling tests
"""

import asyncio
import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.auth import verify_api_key
from backend.app.llm_client import LLMServiceError
from backend.app.queue import ChatMessage, MessageQueue
from backend.app.s3_client import S3DownloadError
from backend.app.file_inputs import FileUploadError
from backend.main import app


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    return AsyncMock()


@pytest.fixture
def mock_s3_client():
    """Create mock S3 client."""
    return AsyncMock()


@pytest.fixture
def mock_file_inputs_client():
    """Create mock FileInputsClient."""
    return AsyncMock()


@pytest.fixture
def mock_session_manager():
    """Create mock SessionManager."""
    manager = AsyncMock()
    manager.get_context_string.return_value = ""
    manager.add_turn.return_value = None
    return manager


@pytest.fixture
def mock_queue_manager(mock_llm_client, mock_s3_client, mock_file_inputs_client, mock_session_manager):
    """Create mock MessageQueue with all dependencies."""
    queue = AsyncMock(spec=MessageQueue)
    queue.enqueue = AsyncMock()
    queue.start = AsyncMock()
    queue.stop = AsyncMock()
    return queue


# ============================================================================
# Unit Tests - Health & Root Endpoints
# ============================================================================


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    async def test_health_check_returns_200(self, async_client_with_queue, api_key_override):
        """Test health check returns healthy status."""
        response = await async_client_with_queue.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "arte-chatbot-backend"

    async def test_root_endpoint(self, async_client_with_queue, api_key_override):
        """Test root endpoint returns API info."""
        response = await async_client_with_queue.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "docs" in data


# ============================================================================
# Unit Tests - Chat Endpoint (with AsyncMock MessageQueue)
# ============================================================================


class TestChatEndpointUnit:
    """Unit tests for /chat endpoint using AsyncClient with mocked queue."""

    async def test_chat_requires_message(self, async_client_with_queue, api_key_override):
        """Test that message field is required (validation error)."""
        response = await async_client_with_queue.post("/chat", json={})
        assert response.status_code == 422

    async def test_chat_rejects_empty_message(self, async_client_with_queue, api_key_override):
        """Test that empty message is rejected (validation error)."""
        response = await async_client_with_queue.post("/chat", json={"message": ""})
        assert response.status_code == 422

    async def test_chat_returns_escalate_for_cotizacion(self, async_client_with_queue, api_key_override):
        """Test escalation flag for 'cotización' keyword."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización de paneles"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert "reason" in data
        assert data["session_id"] is not None

    async def test_chat_returns_escalate_for_pedido(self, async_client_with_queue, api_key_override):
        """Test escalation flag for 'pedido' keyword."""
        response = await async_client_with_queue.post("/chat", json={"message": "Quiero hacer un pedido"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert data["reason"] is not None

    async def test_chat_returns_escalate_for_garantia(self, async_client_with_queue, api_key_override):
        """Test escalation flag for 'garantía' keyword."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Tengo un problema con la garantía"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    async def test_chat_normal_message_with_mocked_queue(self, async_client_with_queue, api_key_override):
        """Test normal message routing through queue (unit test with mock)."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            # Setup mock to immediately resolve the future
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test response", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response = await async_client_with_queue.post(
                "/chat", json={"message": "¿Cuánta potencia tiene el panel?"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "Test response"
            assert data["escalate"] is False
            assert data["session_id"] is not None
        finally:
            # Restore original queue manager
            pass

    async def test_chat_returns_session_id(self, async_client_with_queue, api_key_override):
        """Test that session_id is returned in response."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response = await async_client_with_queue.post("/chat", json={"message": "Hola"})
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert isinstance(data["session_id"], str)
        finally:
            pass

    async def test_chat_accepts_custom_session_id(self, async_client_with_queue, api_key_override):
        """Test that custom session_id can be provided."""
        custom_session = "my-session-123"
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Hola", "session_id": custom_session}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == custom_session
        finally:
            pass

    async def test_chat_timeout_returns_504(self, async_client_with_queue, api_key_override):
        """Test that timeout returns 504 status code."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            # Simulate timeout by not resolving the future
            async def enqueue_no_resolve(msg):
                await asyncio.sleep(61)  # Longer than timeout

            mock_queue.enqueue = enqueue_no_resolve

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test message"}, timeout=70.0
            )
            # The endpoint has 60s timeout, so we expect 504
            assert response.status_code == 504
        finally:
            pass

    async def test_chat_llm_service_error_returns_503(self, async_client_with_queue, api_key_override):
        """Test that LLM service errors return 503 status code."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_with_error(msg):
                msg.future.set_exception(LLMServiceError("Service unavailable"))

            mock_queue.enqueue = enqueue_with_error

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test message"}
            )
            assert response.status_code == 503
            data = response.json()
            assert "detail" in data
        finally:
            pass

    async def test_chat_s3_error_returns_graceful_response(self, async_client_with_queue, api_key_override):
        """Test that S3 errors return graceful response."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_with_error(msg):
                msg.future.set_exception(S3DownloadError("File not found"))

            mock_queue.enqueue = enqueue_with_error

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test message"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert "no pude acceder" in data["response"].lower()
        finally:
            pass

    async def test_chat_file_upload_error_returns_graceful_response(self, async_client_with_queue, api_key_override):
        """Test that file upload errors return graceful response."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_with_error(msg):
                msg.future.set_exception(FileUploadError("Invalid file"))

            mock_queue.enqueue = enqueue_with_error

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test message"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert "problemas" in data["response"].lower()
        finally:
            pass


# ============================================================================
# Integration Tests - MessageQueue Processing
# ============================================================================


class TestChatEndpointIntegration:
    """Integration tests with real MessageQueue (but mocked clients)."""

    async def test_chat_simple_message_no_tool_call(self, async_client_with_queue, api_key_override):
        """Test simple message without tool calls through real queue."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # Mock LLM to return simple response (no tool calls)
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={
                    "output_text": "El panel Jinko Tiger Pro tiene 460W de potencia.",
                    "tool_calls": None,
                }
            )
            mock_session.get_context_string.return_value = ""
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat", json={"message": "¿Cuánta potencia tiene el panel Jinko?"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "El panel Jinko Tiger Pro tiene 460W de potencia."
            assert data["escalate"] is False
            assert data["session_id"] is not None

    async def test_chat_with_tool_call_to_datasheet(self, async_client_with_queue, api_key_override):
        """Test message that requires tool call to read technical datasheet."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # First LLM call returns tool call
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={
                    "output_text": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "leer_ficha_tecnica",
                                "arguments": '{"ruta_s3": "paneles/jinko-tiger-pro-460w.pdf", "categoria": "paneles", "fabricante": "Jinko", "modelo": "Tiger Pro 460W"}',
                            },
                        }
                    ],
                }
            )

            # Mock S3 download
            mock_s3.download_pdf = AsyncMock(return_value=b"%PDF-1.4 test content")

            # Mock file upload
            mock_fi.upload_pdf = AsyncMock(return_value="file-id-123")
            mock_fi.delete_file = AsyncMock()

            # Second LLM call with file
            mock_llm.get_llm_response_with_file = AsyncMock(
                return_value="El panel Jinko Tiger Pro 460W tiene: Potencia: 460W, Voltaje: 48V, Eficiencia: 22.5%"
            )

            mock_session.get_context_string.return_value = ""
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat",
                json={"message": "Cuéntame las especificaciones técnicas del panel Jinko Tiger Pro 460W"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "460W" in data["response"]
            assert data["escalate"] is False

            # Verify tool call workflow
            mock_llm.get_llm_response_with_tools.assert_called_once()
            mock_s3.download_pdf.assert_called_once()
            mock_fi.upload_pdf.assert_called_once()
            mock_llm.get_llm_response_with_file.assert_called_once()
            mock_fi.delete_file.assert_called_once()

    async def test_chat_tool_call_handles_s3_error(self, async_client_with_queue, api_key_override):
        """Test error handling when S3 download fails during tool call."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # First LLM call returns tool call
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={
                    "output_text": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "leer_ficha_tecnica",
                                "arguments": '{"ruta_s3": "paneles/nonexistent.pdf"}',
                            },
                        }
                    ],
                }
            )

            # S3 download fails
            mock_s3.download_pdf = AsyncMock(
                side_effect=S3DownloadError("File not found in S3")
            )

            mock_session.get_context_string.return_value = ""
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Quiero ver el panel no existente"}
            )

            assert response.status_code == 200
            data = response.json()
            # Should return graceful error message
            assert "no pude acceder" in data["response"].lower()

    async def test_chat_tool_call_handles_file_upload_error(self, async_client_with_queue, api_key_override):
        """Test error handling when file upload fails during tool call."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # First LLM call returns tool call
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={
                    "output_text": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "leer_ficha_tecnica",
                                "arguments": '{"ruta_s3": "paneles/test.pdf"}',
                            },
                        }
                    ],
                }
            )

            # S3 download succeeds
            mock_s3.download_pdf = AsyncMock(return_value=b"%PDF-1.4 content")

            # File upload fails
            mock_fi.upload_pdf = AsyncMock(
                side_effect=FileUploadError("Invalid file format")
            )

            mock_session.get_context_string.return_value = ""
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Ver especificaciones"}
            )

            assert response.status_code == 200
            data = response.json()
            # Should return graceful error message
            assert "problemas" in data["response"].lower()

    async def test_chat_tool_call_cleanup_on_success(self, async_client_with_queue, api_key_override):
        """Test that uploaded files are cleaned up after successful tool call."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # Setup mocks
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={
                    "output_text": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "leer_ficha_tecnica",
                                "arguments": '{"ruta_s3": "paneles/test.pdf"}',
                            },
                        }
                    ],
                }
            )

            mock_s3.download_pdf = AsyncMock(return_value=b"%PDF-1.4 content")
            mock_fi.upload_pdf = AsyncMock(return_value="file-id-xyz")
            mock_fi.delete_file = AsyncMock()
            mock_llm.get_llm_response_with_file = AsyncMock(return_value="Panel specs")
            mock_session.get_context_string.return_value = ""
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Especificaciones"}
            )

            assert response.status_code == 200
            # Verify cleanup was called
            mock_fi.delete_file.assert_called_once_with("file-id-xyz")

    async def test_chat_session_context_is_used(self, async_client_with_queue, api_key_override):
        """Test that session context is retrieved and passed to LLM."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            # Setup context
            context = "Turno anterior:\nUsuario: ¿Cuánta potencia?\nAsistente: 460W"
            mock_session.get_context_string.return_value = context

            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={"output_text": "Response", "tool_calls": None}
            )
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat",
                json={"message": "¿Y el precio?", "session_id": "test-session"},
            )

            assert response.status_code == 200

            # Verify context was passed to LLM
            call_kwargs = mock_llm.get_llm_response_with_tools.call_args.kwargs
            assert call_kwargs["context"] == context
            assert call_kwargs["session_id"] == "test-session"

    async def test_chat_stores_turn_in_session(self, async_client_with_queue, api_key_override):
        """Test that conversation turn is stored in session history."""
        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            mock_session.get_context_string.return_value = ""
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={"output_text": "LLM Response", "tool_calls": None}
            )
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat",
                json={"message": "User question", "session_id": "sess-123"},
            )

            assert response.status_code == 200

            # Verify turn was stored
            mock_session.add_turn.assert_called_once()
            call_kwargs = mock_session.add_turn.call_args.kwargs
            assert call_kwargs["session_id"] == "sess-123"
            assert call_kwargs["question"] == "User question"
            assert call_kwargs["answer"] == "LLM Response"


# ============================================================================
# Escalation Tests
# ============================================================================


class TestChatEndpointEscalation:
    """Tests for escalation detection."""

    async def test_escalate_cotizacion(self, async_client_with_queue, api_key_override):
        """Test escalation for cotización requests."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert data["reason"] is not None

    async def test_escalate_pedido(self, async_client_with_queue, api_key_override):
        """Test escalation for order requests."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Quiero hacer un pedido ahora"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    async def test_escalate_garantia(self, async_client_with_queue, api_key_override):
        """Test escalation for warranty issues."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Tengo un problema con la garantía"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    async def test_escalate_returns_default_message(self, async_client_with_queue, api_key_override):
        """Test that escalation returns the default escalation message."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert len(data["response"]) > 0
        # Response should indicate escalation to human agent
        assert data["response"] is not None

    async def test_escalate_stores_turn_in_session(self, async_client_with_queue, api_key_override):
        """Test that escalation stores the turn in session history."""
        with patch("backend.main.session_manager") as mock_session:
            mock_session.add_turn = AsyncMock()

            response = await async_client_with_queue.post(
                "/chat",
                json={
                    "message": "Necesito una cotización",
                    "session_id": "esc-session-123",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["escalate"] is True

            # Verify turn was stored
            mock_session.add_turn.assert_called_once()
            call_kwargs = mock_session.add_turn.call_args.kwargs
            assert call_kwargs["session_id"] == "esc-session-123"


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestChatEndpointErrorHandling:
    """Tests for error handling in /chat endpoint."""

    async def test_missing_message_field_422(self, async_client_with_queue, api_key_override):
        """Test missing message field returns 422."""
        response = await async_client_with_queue.post("/chat", json={})
        assert response.status_code == 422

    async def test_empty_message_string_422(self, async_client_with_queue, api_key_override):
        """Test empty message string returns 422."""
        response = await async_client_with_queue.post("/chat", json={"message": ""})
        assert response.status_code == 422

    async def test_missing_api_key_401(self, async_client_with_queue):
        """Test missing API key returns 401."""
        # Remove the override to test actual auth
        app.dependency_overrides.clear()

        response = await async_client_with_queue.post(
            "/chat", json={"message": "Test"},
            headers={"X-API-Key": "invalid-key"}
        )
        # Should get 403 (Forbidden) for wrong key or 401 depending on auth impl
        assert response.status_code in (401, 403)

        # Restore override for other tests
        app.dependency_overrides[verify_api_key] = lambda: "test_key"

    async def test_queue_runtime_error_returns_500(self, async_client_with_queue, api_key_override):
        """Test unexpected errors return 500."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_with_error(msg):
                raise RuntimeError("Unexpected queue error")

            mock_queue.enqueue = enqueue_with_error

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test"}
            )
            assert response.status_code == 500
        finally:
            pass

    async def test_response_has_required_fields(self, async_client_with_queue, api_key_override):
        """Test that successful response has all required fields."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response = await async_client_with_queue.post(
                "/chat", json={"message": "Test"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert "escalate" in data
            assert "session_id" in data
            # reason is optional but included for escalations
            if data["escalate"]:
                assert "reason" in data
        finally:
            pass


# ============================================================================
# Response Schema Tests
# ============================================================================


class TestChatResponseSchema:
    """Tests for response schema and structure."""

    async def test_response_is_valid_json(self, async_client_with_queue, api_key_override):
        """Test that response is valid JSON."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización"}
        )
        assert response.status_code == 200
        # Should not raise exception
        data = response.json()
        assert isinstance(data, dict)

    async def test_response_escalate_is_boolean(self, async_client_with_queue, api_key_override):
        """Test that escalate field is a boolean."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response = await async_client_with_queue.post(
                "/chat", json={"message": "¿Cuánta potencia?"}
            )

            data = response.json()
            assert isinstance(data["escalate"], bool)
        finally:
            pass

    async def test_response_session_id_is_string(self, async_client_with_queue, api_key_override):
        """Test that session_id is a string."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización"}
        )

        data = response.json()
        assert isinstance(data["session_id"], str)

    async def test_response_reason_included_on_escalation(self, async_client_with_queue, api_key_override):
        """Test that reason is included when escalate is True."""
        response = await async_client_with_queue.post(
            "/chat", json={"message": "Necesito una cotización"}
        )

        data = response.json()
        if data["escalate"]:
            assert "reason" in data
            assert isinstance(data["reason"], str)


# ============================================================================
# Request/Response Round-trip Tests
# ============================================================================


class TestChatRoundtrip:
    """Tests for full request/response round-trips."""

    async def test_multiple_messages_same_session(self, async_client_with_queue, api_key_override):
        """Test multiple messages in same session preserve session_id."""
        session_id = str(uuid.uuid4())

        with patch("backend.main.llm_client") as mock_llm, \
             patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_fi, \
             patch("backend.main.session_manager") as mock_session:

            mock_session.get_context_string.return_value = ""
            mock_llm.get_llm_response_with_tools = AsyncMock(
                return_value={"output_text": "Response", "tool_calls": None}
            )
            mock_session.add_turn = AsyncMock()

            # First message
            response1 = await async_client_with_queue.post(
                "/chat",
                json={"message": "First question", "session_id": session_id},
            )
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["session_id"] == session_id

            # Second message
            response2 = await async_client_with_queue.post(
                "/chat",
                json={"message": "Follow-up question", "session_id": session_id},
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["session_id"] == session_id

    async def test_auto_generated_session_id_is_unique(self, async_client_with_queue, api_key_override):
        """Test that auto-generated session IDs are unique."""
        # Replace queue_manager with mock for this test
        mock_queue = AsyncMock()
        app.state.queue_manager = mock_queue
        try:
            async def enqueue_and_resolve(msg):
                msg.future.set_result({"response": "Test", "escalate": False})

            mock_queue.enqueue = enqueue_and_resolve

            response1 = await async_client_with_queue.post(
                "/chat", json={"message": "Message 1"}
            )
            response2 = await async_client_with_queue.post(
                "/chat", json={"message": "Message 2"}
            )

            data1 = response1.json()
            data2 = response2.json()

            assert data1["session_id"] != data2["session_id"]
        finally:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
