"""
Unit and Integration tests for the /chat endpoint.
"""
import os
import uuid
import pytest
import requests
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.auth import verify_api_key

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
        response = client.post("/chat", json={"message": "Necesito una cotización de paneles"})
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
        assert "cotización" in data["reason"].lower() or "pedido" in data["reason"].lower()

    def test_chat_returns_escalate_for_garantia(self) -> None:
        """Test escalation flag for 'garantía' keyword."""
        response = client.post("/chat", json={"message": "Tengo un problema con la garantía"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    @patch("backend.main.llm_client.get_llm_response")
    def test_chat_no_escalate_for_normal_message(self, mock_llm) -> None:
        """Test no escalation for normal messages."""
        mock_llm.return_value = "Mocked LLM Response"
        response = client.post("/chat", json={"message": "¿Cuánta potencia tiene el panel de 400W?"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is False
        assert data["reason"] is None
        assert data["response"] == "Mocked LLM Response"

    @patch("backend.main.llm_client.get_llm_response")
    def test_chat_returns_session_id(self, mock_llm) -> None:
        """Test that session_id is returned in response."""
        mock_llm.return_value = "Mocked LLM Response"
        response = client.post("/chat", json={"message": "Hola"})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)

    @patch("backend.main.llm_client.get_llm_response")
    def test_chat_accepts_custom_session_id(self, mock_llm) -> None:
        """Test that custom session_id can be provided."""
        mock_llm.return_value = "Mocked LLM Response"
        response = client.post("/chat", json={"message": "Hola", "session_id": "my-session-123"})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "my-session-123"

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
        response = requests.post(API_URL, json=payload, headers={"X-API-Key": chat_api_key})
        assert response.status_code == 200
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend is not running locally on port 8000")


@pytest.mark.integration
def test_chat_response_not_empty(api_key, chat_api_key):
    """Verify the response body is non-empty when the API key is available."""
    payload = {"message": "Test", "session_id": str(uuid.uuid4())}
    try:
        response = requests.post(API_URL, json=payload, headers={"X-API-Key": chat_api_key})
        assert response.json().get("response"), "Response should not be empty"
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend is not running locally on port 8000")


@pytest.mark.integration
def test_session_id_uuid_format(api_key, chat_api_key):
    """Verify the returned session_id is a valid UUID."""
    session_id = str(uuid.uuid4())
    payload = {"message": "UUID check", "session_id": session_id}
    try:
        response = requests.post(API_URL, json=payload, headers={"X-API-Key": chat_api_key})
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
    assert os.getenv("OPENAI_API_KEY") is not None, "OPENAI_API_KEY must be loaded from environment"
