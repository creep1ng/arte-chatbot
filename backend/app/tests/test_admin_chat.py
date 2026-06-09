"""Tests for admin-authenticated chat proxy endpoints."""

import json
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.message_buffer import set_pending_chat_response, set_processing
from backend.tests.conftest import make_llm_response


def _reset_settings() -> None:
    """Reset settings proxy so each test reads patched environment values."""
    settings.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with only admin auth configured."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("CHAT_API_KEY", "")
    monkeypatch.setenv("GREETING_ENABLED", "false")
    monkeypatch.setenv("MULTI_MESSAGE_BUFFER_ENABLED", "false")
    _reset_settings()

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client

    _reset_settings()


def _admin_headers() -> dict[str, str]:
    """Return valid admin auth headers for tests."""
    return {"X-Admin-API-Key": "test-admin-key"}


class TestAdminChatAuth:
    """Admin chat access requires admin authentication only."""

    def test_admin_chat_requires_admin_key(self, client: TestClient) -> None:
        """POST /admin/chat without admin key returns 401."""
        response = client.post("/admin/chat", json={"message": "Hola"})

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing admin API key"

    def test_admin_chat_rejects_invalid_admin_key(self, client: TestClient) -> None:
        """POST /admin/chat with wrong admin key returns 403."""
        response = client.post(
            "/admin/chat",
            headers={"X-Admin-API-Key": "wrong"},
            json={"message": "Hola"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid admin API key"

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_admin_chat_does_not_require_chat_api_key(
        self,
        mock_llm: AsyncMock,
        client: TestClient,
    ) -> None:
        """Admin-authenticated chat succeeds when CHAT_API_KEY is not configured."""
        mock_llm.return_value = make_llm_response(text="[INTENT: FAQ] Hola admin")

        response = client.post(
            "/admin/chat",
            headers=_admin_headers(),
            json={"message": "Hola", "session_id": "admin-chat-no-chat-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Hola admin"
        assert data["session_id"] == "admin-chat-no-chat-key"


class TestAdminChatContract:
    """Admin chat proxy preserves existing chat response contracts."""

    @patch("backend.main.process_split_messages")
    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_admin_chat_preserves_split_fields(
        self,
        mock_llm: AsyncMock,
        mock_split_messages: AsyncMock,
        client: TestClient,
    ) -> None:
        """Split assistant fields are returned unchanged through admin proxy."""
        mock_llm.return_value = make_llm_response(
            text="[INTENT: FAQ] Primera parte\n---\nSegunda parte",
            input_tokens=11,
            output_tokens=7,
            total_tokens=18,
        )
        mock_split_messages.return_value = (
            ["Primera parte", "Segunda parte"],
            [1200],
        )

        response = client.post(
            "/admin/chat",
            headers=_admin_headers(),
            json={"message": "Separá", "session_id": "admin-chat-split"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == ["Primera parte", "Segunda parte"]
        assert data["delays_ms"] == [1200]
        assert data["input_tokens"] == 11
        assert data["output_tokens"] == 7
        assert data["total_tokens"] == 18

    def test_admin_buffer_result_returns_ready_chat_response(
        self,
        client: TestClient,
    ) -> None:
        """Admin buffer polling returns the same ready JSON payload contract."""
        session_id = "admin-buffer-ready"
        chat_response = {
            "response": "Respuesta lista",
            "escalate": False,
            "intent_type": "FAQ",
            "confidence": None,
            "reason": None,
            "session_id": session_id,
            "source_documents": [],
            "num_sources": 0,
            "user_profile": "intermedio",
            "messages": ["Respuesta lista"],
            "delays_ms": [1200],
            "input_tokens": 3,
            "output_tokens": 4,
            "total_tokens": 7,
        }
        set_pending_chat_response(session_id, json.dumps(chat_response))

        response = client.get(
            f"/admin/chat/buffer-result/{session_id}",
            headers=_admin_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["session_id"] == session_id
        assert json.loads(data["result"]) == chat_response

    def test_admin_buffer_result_pending_while_processing(
        self,
        client: TestClient,
    ) -> None:
        """Admin buffer polling reports pending while background processing runs."""
        session_id = "admin-buffer-pending"
        set_processing(session_id)

        response = client.get(
            f"/admin/chat/buffer-result/{session_id}",
            headers=_admin_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "pending",
            "session_id": session_id,
            "result": None,
        }
