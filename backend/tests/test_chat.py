"""
Unit tests for the /chat endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


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


class TestChatEndpoint:
    """Tests for /chat endpoint."""

    def test_chat_requires_message(self) -> None:
        """Test that message field is required."""
        response = client.post("/chat", json={})

        assert response.status_code == 422  # Validation error

    def test_chat_returns_escalate_for_cotizacion(self) -> None:
        """Test escalation flag for 'cotización' keyword."""
        response = client.post(
            "/chat",
            json={"message": "Necesito una cotización de paneles"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert "reason" in data
        assert data["session_id"] is not None

    def test_chat_returns_escalate_for_pedido(self) -> None:
        """Test escalation flag for 'pedido' keyword."""
        response = client.post(
            "/chat",
            json={"message": "Quiero hacer un pedido"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True
        assert "cotización" in data["reason"].lower() or "pedido" in data["reason"].lower()

    def test_chat_returns_escalate_for_garantia(self) -> None:
        """Test escalation flag for 'garantía' keyword."""
        response = client.post(
            "/chat",
            json={"message": "Tengo un problema con la garantía"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is True

    def test_chat_no_escalate_for_normal_message(self) -> None:
        """Test no escalation for normal messages."""
        response = client.post(
            "/chat",
            json={"message": "¿Cuánta potencia tiene el panel de 400W?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["escalate"] is False
        assert data["reason"] is None

    def test_chat_returns_session_id(self) -> None:
        """Test that session_id is returned in response."""
        response = client.post(
            "/chat",
            json={"message": "Hola"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)

    def test_chat_accepts_custom_session_id(self) -> None:
        """Test that custom session_id can be provided."""
        response = client.post(
            "/chat",
            json={"message": "Hola", "session_id": "my-session-123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "my-session-123"

    def test_chat_returns_escalation_message(self) -> None:
        """Test that escalation response includes user message."""
        response = client.post(
            "/chat",
            json={"message": "Quiero una cotización"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0
