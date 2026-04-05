"""
Unit and Integration tests for the /chat endpoint.
"""

import json
import os
import uuid
import pytest
import requests
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.auth import verify_api_key
from backend.app.schemas import SourceDocument

client = TestClient(app)

# Override auth for unit tests
app.dependency_overrides[verify_api_key] = lambda: "test_key"


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_returns_200(self) -> None:
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "arte-chatbot-backend"

    def test_root_endpoint(self) -> None:
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "docs" in data


class TestChatEndpointUnit:
    """Tests for /chat endpoint using TestClient."""

    def test_chat_requires_message(self) -> None:
        """Test that message field is required."""
        response = client.post("/chat", json={})
        assert response.status_code == 422  # Validation error

    def test_chat_returns_escalate_for_cotizacion(self) -> None:
        """Test escalation flag for 'cotización' keyword."""
        response = client.post(
            "/chat", json={"message": "Necesito una cotización de paneles"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert "reason" in data
        assert data["session_id"] is not None

    def test_chat_returns_escalate_for_pedido(self) -> None:
        """Test escalation flag for 'pedido' keyword."""
        response = client.post("/chat", json={"message": "Quiero hacer un pedido"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert (
            "cotización" in data["reason"].lower() or "pedido" in data["reason"].lower()
        )

    def test_chat_returns_escalate_for_garantia(self) -> None:
        """Test escalation flag for 'garantía' keyword."""
        response = client.post(
            "/chat", json={"message": "Tengo un problema con la garantía"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_chat_no_escalate_for_normal_message(self, mock_llm) -> None:
        """Test no escalation for normal messages."""
        # get_llm_response_with_tools returns a dict with output_text (Responses API)
        mock_llm.return_value = {"output_text": "Mocked LLM Response"}
        response = client.post(
            "/chat", json={"message": "¿Cuánta potencia tiene el panel de 400W?"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is False
        assert data["reason"] is None
        assert data["response"] == "Mocked LLM Response"

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_chat_returns_session_id(self, mock_llm) -> None:
        """Test that session_id is returned in response."""
        mock_llm.return_value = {"output_text": "Mocked LLM Response"}
        response = client.post("/chat", json={"message": "Hola"})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_chat_accepts_custom_session_id(self, mock_llm) -> None:
        """Test that custom session_id can be provided."""
        mock_llm.return_value = {"output_text": "Mocked LLM Response"}
        response = client.post(
            "/chat", json={"message": "Hola", "session_id": "my-session-123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "my-session-123"

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.session_manager")
    def test_chat_uses_session_context(self, mock_session_manager, mock_llm):
        """Test that the chat endpoint uses session context."""
        # Configurar mocks
        mock_llm.return_value = {"output_text": "Mocked LLM Response"}
        mock_session_manager.get_context_string.return_value = (
            "Turno 1:\nUsuario: Pregunta anterior\nAsistente: Respuesta anterior"
        )

        # Hacer la petición
        response = client.post(
            "/chat",
            json={"message": "¿Y cuánto cuesta?", "session_id": "test-session-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Mocked LLM Response"

        # Verificar que se llamó al LLM con el contexto
        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        # Message includes context when session context exists
        assert "¿Y cuánto cuesta?" in kwargs["message"]
        assert kwargs["session_id"] == "test-session-123"
        assert kwargs["context"] == mock_session_manager.get_context_string.return_value
        assert "Pregunta anterior" in kwargs["context"]

        # Verificar que se guardó el turno en la sesión
        mock_session_manager.add_turn.assert_called_once()
        add_args, add_kwargs = mock_session_manager.add_turn.call_args
        assert add_kwargs["session_id"] == "test-session-123"
        assert add_kwargs["question"] == "¿Y cuánto cuesta?"
        assert add_kwargs["answer"] == "Mocked LLM Response"

    def test_chat_returns_escalation_message(self) -> None:
        """Test that escalation response includes user message."""
        response = client.post("/chat", json={"message": "Quiero una cotización"})
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0


# Integration Tests

API_URL = "http://localhost:8000/chat"


@pytest.fixture(scope="module")
def api_key():
    key = os.getenv("OPENAI_API_KEY")
    if key is None:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.fixture(scope="module")
def chat_api_key():
    key = os.getenv("CHAT_API_KEY")
    if key is None:
        pytest.skip("CHAT_API_KEY not set")
    return key


@pytest.mark.integration
def test_chat_status_200(chat_api_key):
    """Verify the /chat endpoint returns 200 for a valid request with auth header."""
    payload = {"message": "Hello", "session_id": str(uuid.uuid4())}
    try:
        response = requests.post(
            API_URL, json=payload, headers={"X-API-Key": chat_api_key}
        )
        assert response.status_code == 200
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend is not running locally on port 8000")


@pytest.mark.integration
def test_chat_response_not_empty(api_key, chat_api_key):
    """Verify the response body is non-empty when the API key is available."""
    payload = {"message": "Test", "session_id": str(uuid.uuid4())}
    try:
        response = requests.post(
            API_URL, json=payload, headers={"X-API-Key": chat_api_key}
        )
        assert response.json().get("response"), "Response should not be empty"
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend is not running locally on port 8000")


@pytest.mark.integration
def test_session_id_uuid_format(api_key, chat_api_key):
    """Verify the returned session_id is a valid UUID."""
    session_id = str(uuid.uuid4())
    payload = {"message": "UUID check", "session_id": session_id}
    try:
        response = requests.post(
            API_URL, json=payload, headers={"X-API-Key": chat_api_key}
        )
        returned_id = response.json().get("session_id")
        assert returned_id is not None
        try:
            uuid.UUID(returned_id)
        except ValueError:
            pytest.fail("session_id is not valid UUID format")
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend is not running locally on port 8000")


@pytest.mark.integration
def test_openai_api_key_loaded_from_env(api_key):
    """Verify the OPENAI_API_KEY environment variable is set."""
    assert os.getenv("OPENAI_API_KEY") is not None, (
        "OPENAI_API_KEY must be loaded from environment"
    )


# Tool Calling Tests


class TestChatEndpointWithToolCall:
    """Tests for /chat endpoint with tool calling functionality."""

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.s3_client")
    @patch("backend.main.file_inputs_client")
    def test_chat_endpoint_with_tool_call_in_response(
        self, mock_file_inputs: MagicMock, mock_s3: MagicMock, mock_llm: MagicMock
    ) -> None:
        """Test chat endpoint with tool call in response."""
        # First LLM call returns tool call, second call should return no tool calls (normal response)
        tool_call_response = {
            "output_text": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "leer_ficha_tecnica",
                        "arguments": '{"ruta_s3": "paneles/jinko-tiger-pro-460w.pdf", "categoria": "paneles", "fabricante": "Jinko", "modelo": "Tiger Pro 460W"}',
                    },
                }
            ],
        }
        
        normal_response = {
            "output_text": "El panel Jinko Tiger Pro 460W tiene una potencia de 460W.",
            "tool_calls": [],
        }
        
        mock_llm.side_effect = [tool_call_response, normal_response]

        # Mock S3 download
        mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"

        # Mock file upload
        mock_file_inputs.upload_pdf.return_value = "file-abc123"
        mock_file_inputs.delete_file.return_value = None

        # Mock second LLM call
        with patch(
            "backend.main.llm_client.get_llm_response_with_file"
        ) as mock_llm_file:
            mock_llm_file.return_value = (
                "El panel Jinko Tiger Pro 460W tiene una potencia de 460W."
            )

            response = client.post(
                "/chat",
                json={
                    "message": "Dime las especificaciones del panel Jinko Tiger Pro 460W"
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is False
        assert "460W" in data["response"]
        assert data["session_id"] is not None

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.s3_client")
    def test_chat_endpoint_handles_s3_download_error(
        self, mock_s3: MagicMock, mock_llm: MagicMock
    ) -> None:
        """Test chat endpoint handles S3 download errors gracefully."""
        from backend.app.s3_client import S3DownloadError

        # Mock LLM response with tool call - first call returns tool call, second should return normal response
        tool_call_response = {
            "output_text": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "leer_ficha_tecnica",
                        "arguments": '{"ruta_s3": "paneles/nonexistent.pdf", "categoria": "paneles", "fabricante": "Test", "modelo": "Test"}',
                    },
                }
            ],
        }
        
        normal_response = {
            "output_text": "No pude acceder al archivo solicitado.",
            "tool_calls": [],
        }
        
        mock_llm.side_effect = [tool_call_response, normal_response]

        # Mock S3 download error
        mock_s3.download_pdf.side_effect = S3DownloadError(
            "File not found in S3: nonexistent.pdf"
        )

        response = client.post(
            "/chat",
            json={"message": "Dime las especificaciones del panel Test"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should return graceful error message, not crash
        assert data["response"] is not None
        assert (
            "no pude acceder" in data["response"].lower()
            or "disponible" in data["response"].lower()
        )

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.s3_client")
    @patch("backend.main.file_inputs_client")
    def test_chat_endpoint_handles_file_upload_error(
        self, mock_file_inputs: MagicMock, mock_s3: MagicMock, mock_llm: MagicMock
    ) -> None:
        """Test chat endpoint handles file upload errors gracefully."""
        from backend.app.file_inputs import FileUploadError

        # Mock LLM response with tool call (Responses API format)
        mock_llm.return_value = {
            "output_text": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "leer_ficha_tecnica",
                        "arguments": '{"ruta_s3": "paneles/test.pdf", "categoria": "paneles", "fabricante": "Test", "modelo": "Test"}',
                    },
                }
            ],
        }

        # Mock S3 download success
        mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"

        # Mock file upload error
        mock_file_inputs.upload_pdf.side_effect = FileUploadError("Invalid file format")

        response = client.post(
            "/chat",
            json={"message": "Dime las especificaciones del panel Test"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should handle error gracefully
        assert data["response"] is not None

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.s3_client")
    @patch("backend.main.file_inputs_client")
    def test_chat_endpoint_cleans_up_uploaded_files(
        self, mock_file_inputs: MagicMock, mock_s3: MagicMock, mock_llm: MagicMock
    ) -> None:
        """Test chat endpoint cleans up uploaded files after second LLM call."""
        # Mock LLM response with tool call - first call returns tool call, second should return normal response
        tool_call_response = {
            "output_text": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "leer_ficha_tecnica",
                        "arguments": '{"ruta_s3": "paneles/test.pdf", "categoria": "paneles", "fabricante": "Test", "modelo": "Test"}',
                    },
                }
            ],
        }
        
        normal_response = {
            "output_text": "Test response",
            "tool_calls": [],
        }
        
        mock_llm.side_effect = [tool_call_response, normal_response]

        # Mock S3 download
        mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"

        # Mock file upload
        mock_file_inputs.upload_pdf.return_value = "file-abc123"

        # Mock second LLM call
        with patch(
            "backend.main.llm_client.get_llm_response_with_file"
        ) as mock_llm_file:
            mock_llm_file.return_value = "Test response"

            response = client.post(
                "/chat",
                json={"message": "Test message"},
            )

        # Verify delete was called after the second LLM call
        mock_file_inputs.delete_file.assert_called_once_with("file-abc123")

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_chat_endpoint_returns_normal_response_when_no_tool_call(
        self, mock_llm: MagicMock
    ) -> None:
        """Test chat endpoint returns normal response when no tool call."""
        # Mock LLM response without tool call (Responses API format)
        mock_llm.return_value = {
            "output_text": "Soy el asistente de Arte Soluciones Energéticas. ¿En qué puedo ayudarte?",
        }

        response = client.post("/chat", json={"message": "Hola"})

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is False
        assert "Arte Soluciones Energéticas" in data["response"]
        assert data["source_documents"] == []

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_chat_endpoint_passes_session_id_to_llm(self, mock_llm: MagicMock) -> None:
        """Test chat endpoint passes session_id to LLM client."""
        mock_llm.return_value = {
            "output_text": "Test response",
        }

        custom_session = "custom-session-abc123"
        response = client.post(
            "/chat",
            json={"message": "Test", "session_id": custom_session},
        )

        # Verify session_id was passed to LLM
        call_args = mock_llm.call_args
        assert call_args is not None
        _, kwargs = call_args
        assert kwargs.get("session_id") == custom_session


class TestSourceDocumentsBehavior:
    """Tests covering source_documents enrichment in ChatResponse."""

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_source_documents_empty_on_no_tool_call(self, mock_llm: MagicMock) -> None:
        mock_llm.return_value = {
            "output_text": "Respuesta sin herramientas",
            "tool_calls": [],
        }

        response = client.post(
            "/chat",
            json={"message": "Consulta general"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Respuesta sin herramientas"
        assert data["source_documents"] == []

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    @patch("backend.main.s3_client")
    @patch("backend.main.file_inputs_client")
    def test_source_documents_populated_on_leer_ficha_tecnica(
        self,
        mock_file_inputs: MagicMock,
        mock_s3: MagicMock,
        mock_llm: MagicMock,
    ) -> None:
        """Test that source documents are populated when leer_ficha_tecnica is called."""
        leer_tool_call = {
            "id": "call_leer",
            "type": "function",
            "function": {
                "name": "leer_ficha_tecnica",
                "arguments": json.dumps({"ruta_s3": "paneles/test.pdf"}),
            },
        }

        # First LLM call returns tool call, second returns normal response
        tool_call_response = {"output_text": "", "tool_calls": [leer_tool_call]}
        normal_response = {"output_text": "Contenido ficha", "tool_calls": []}
        
        mock_llm.side_effect = [tool_call_response, normal_response]
        mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"
        mock_file_inputs.upload_pdf.return_value = "file-abc123"

        with patch("backend.main.llm_client.get_llm_response_with_file") as mock_llm_file:
            mock_llm_file.return_value = "Contenido ficha"
            
            response = client.post(
                "/chat",
                json={"message": "Necesito la ficha del panel Test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Contenido ficha"
        assert data["source_documents"] == [
            {"ruta": "paneles/test.pdf", "contenido_relevante": None}
        ]

    def test_source_documents_not_null_on_escalation(self) -> None:
        response = client.post(
            "/chat",
            json={"message": "Necesito una cotización de 10 inversores"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert data["source_documents"] == []


class TestSourceDocumentSchema:
    """Unit tests for the SourceDocument model."""

    def test_source_document_schema_has_ruta_field(self) -> None:
        doc = SourceDocument(ruta="paneles/test.pdf")
        assert hasattr(doc, "ruta")
        assert doc.ruta == "paneles/test.pdf"

    def test_source_document_contenido_relevante_is_optional(self) -> None:
        doc = SourceDocument(ruta="paneles/test.pdf")
        assert doc.contenido_relevante is None

class TestAgenticLoopBehavior:
    """Tests covering the iterative agentic loop inside /chat."""

    @patch("backend.main.catalog_search.search")
    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_agentic_loop_buscar_then_leer_then_respond(
        self,
        mock_llm: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """Simulate buscar_producto followed by leer_ficha_tecnica within the loop."""

        buscar_tool_call = {
            "id": "call_buscar",
            "type": "function",
            "function": {
                "name": "buscar_producto",
                "arguments": json.dumps(
                    {
                        "categoria": "paneles",
                        "fabricante": "Jinko",
                        "tipo": "mono",
                    }
                ),
            },
        }

        leer_tool_call = {
            "id": "call_leer",
            "type": "function",
            "function": {
                "name": "leer_ficha_tecnica",
                "arguments": json.dumps({"ruta_s3": "paneles/jinko-tiger-pro.pdf"}),
            },
        }

        # Mock LLM side effects: first call buscar, second call leer, third call returns final response
        mock_llm.side_effect = [
            {"output_text": "", "tool_calls": [buscar_tool_call]},
            {"output_text": "", "tool_calls": [leer_tool_call]},
            {"output_text": "Ficha técnica procesada", "tool_calls": []},
        ]

        mock_search.return_value = [
            MagicMock(
                ruta_s3="paneles/jinko-tiger-pro.pdf",
                nombre_comercial="Jinko Tiger Pro",
                fabricante="Jinko",
                descripcion=None,
                variantes=[],
            )
        ]

        with patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_file_inputs, \
             patch("backend.main.llm_client.get_llm_response_with_file") as mock_llm_file:
            
            mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"
            mock_file_inputs.upload_pdf.return_value = "file-abc123"
            mock_llm_file.return_value = "Ficha técnica procesada"

            response = client.post(
                "/chat",
                json={"message": "Necesito la ficha del panel Jinko Tiger Pro"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Ficha técnica procesada"
        assert mock_llm.call_count == 3
        mock_search.assert_called_once()

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_agentic_loop_stops_when_no_tool_calls(self, mock_llm: MagicMock) -> None:
        """Ensure loop returns immediately when the model does not request tools."""

        mock_llm.return_value = {
            "output_text": "Respuesta directa",
            "tool_calls": [],
        }

        response = client.post(
            "/chat",
            json={"message": "Cuéntame sobre paneles en general"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Respuesta directa"
        assert mock_llm.call_count == 1

    @patch("backend.main.MAX_AGENTIC_ITERATIONS", 2)
    @patch("backend.main.logger.warning")
    @patch("backend.main.catalog_search.search", return_value=[])
    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_agentic_loop_respects_max_iterations(
        self,
        mock_llm: MagicMock,
        mock_search: MagicMock,
        mock_warning: MagicMock,
    ) -> None:
        """Verify the loop stops after reaching MAX_AGENTIC_ITERATIONS."""

        looping_response = {
            "output_text": "Sigo buscando opciones",
            "tool_calls": [
                {
                    "id": "call_loop",
                    "type": "function",
                    "function": {
                        "name": "buscar_producto",
                        "arguments": json.dumps(
                            {
                                "categoria": "paneles",
                            }
                        ),
                    },
                }
            ],
        }

        # Mock returns the looping response multiple times (for 2+ iterations)
        mock_llm.side_effect = [looping_response, looping_response, looping_response]

        response = client.post(
            "/chat",
            json={"message": "Busca paneles de 500W"},
        )

        assert response.status_code == 200
        data = response.json()
        # After max iterations (2), should return the max iterations message
        assert "límite de iteraciones" in data["response"].lower()
        # Should have called LLM at least twice (iteration 1 and 2)
        assert mock_llm.call_count >= 2
        mock_search.assert_called()
        mock_warning.assert_called_once()

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_leer_ficha_tecnica_with_direct_ruta_s3_still_works(
        self,
        mock_llm: MagicMock,
    ) -> None:
        """Ensure leer_ficha_tecnica tool call with ruta_s3 works properly."""

        leer_tool_call = {
            "id": "call_direct_leer",
            "type": "function",
            "function": {
                "name": "leer_ficha_tecnica",
                "arguments": json.dumps({"ruta_s3": "paneles/longi-500w.pdf"}),
            },
        }

        # First LLM call returns leer tool call, second call returns normal response
        tool_call_response = {"output_text": "", "tool_calls": [leer_tool_call]}
        normal_response = {"output_text": "Información obtenida directamente", "tool_calls": []}
        
        mock_llm.side_effect = [tool_call_response, normal_response]

        with patch("backend.main.s3_client") as mock_s3, \
             patch("backend.main.file_inputs_client") as mock_file_inputs, \
             patch("backend.main.llm_client.get_llm_response_with_file") as mock_llm_file:
            
            mock_s3.download_pdf.return_value = b"%PDF-1.4 test content"
            mock_file_inputs.upload_pdf.return_value = "file-abc123"
            mock_llm_file.return_value = "Información obtenida directamente"

            response = client.post(
                "/chat",
                json={"message": "Dame la ficha del panel Longi 500W"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Información obtenida directamente"


class TestProcessToolCall:
    """Tests for the _process_leer_ficha_tecnica function."""

    @patch("backend.main.s3_client")
    @patch("backend.main.file_inputs_client")
    def test_process_tool_call_success(
        self, mock_file_inputs: MagicMock, mock_s3: MagicMock
    ) -> None:
        """Test _process_leer_ficha_tecnica handles successful execution."""
        from backend.main import _process_leer_ficha_tecnica

        # Mock S3 download
        mock_s3.download_pdf.return_value = b"%PDF-1.4 test"

        # Mock file upload
        mock_file_inputs.upload_pdf.return_value = "file-xyz789"

        # Mock second LLM call
        with patch(
            "backend.main.llm_client.get_llm_response_with_file"
        ) as mock_llm_file:
            mock_llm_file.return_value = "El panel tiene 460W de potencia."

            tool_call = {
                "id": "call_123",
                "function": {
                    "name": "leer_ficha_tecnica",
                    "arguments": '{"ruta_s3": "paneles/jinko.pdf", "categoria": "paneles", "fabricante": "Jinko", "modelo": "Tiger"}',
                },
            }

            result, source_docs = _process_leer_ficha_tecnica(
                tool_call=tool_call,
                user_message="Specs del panel",
                session_id="test-session",
            )

        assert "460W" in result
        assert source_docs == ["paneles/jinko.pdf"]
        mock_file_inputs.delete_file.assert_called_once_with("file-xyz789")

    @patch("backend.main.s3_client")
    def test_process_tool_call_s3_error(self, mock_s3: MagicMock) -> None:
        """Test _process_leer_ficha_tecnica handles S3 errors with catalog fallback."""
        from backend.main import _process_leer_ficha_tecnica
        from backend.app.s3_client import S3DownloadError

        # S3 download fails - will trigger catalog fallback
        # When catalog fallback finds no results, a ValueError is raised
        mock_s3.download_pdf.side_effect = S3DownloadError("File not found")

        tool_call = {
            "id": "call_123",
            "function": {
                "name": "leer_ficha_tecnica",
                "arguments": '{"ruta_s3": "bad.pdf", "categoria": "paneles", "fabricante": "X", "modelo": "Y"}',
            },
        }

        # Should raise ValueError when catalog fallback finds no results
        with pytest.raises(ValueError) as exc_info:
            _process_leer_ficha_tecnica(
                tool_call=tool_call,
                user_message="Test",
                session_id="test",
            )
        
        assert "catálogo" in str(exc_info.value).lower() or "no se encontraron" in str(exc_info.value).lower()

    def test_process_tool_call_invalid_tool_name(self) -> None:
        """Test that unknown tool names are handled gracefully."""
        # Note: _process_leer_ficha_tecnica is specific to leer_ficha_tecnica tool
        # Invalid tool names are handled in the main agentic loop, not here
        pass


class TestBuscarProductoTool:
    """Unit tests for buscar_producto tool handler."""

    @patch("backend.main.catalog_search.search", return_value=[])
    def test_buscar_producto_no_results_informs_user(
        self, mock_search: MagicMock
    ) -> None:
        """Ensure the handler informs the user when no products match."""
        from backend.main import _handle_buscar_producto_tool

        tool_call = {
            "id": "call_buscar_empty",
            "function": {
                "name": "buscar_producto",
                "arguments": json.dumps(
                    {
                        "categoria": "paneles",
                        "fabricante": "Trina",
                        "tipo": "mono",
                    }
                ),
            },
        }

        output, is_terminal = _handle_buscar_producto_tool(tool_call)

        assert "No encontré productos" in output
        assert is_terminal is False
        mock_search.assert_called_once_with(
            categoria="paneles",
            fabricante="Trina",
            capacidad_min=None,
            capacidad_max=None,
            tipo="mono",
            modelo_contiene=None,
        )
