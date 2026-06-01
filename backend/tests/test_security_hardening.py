"""Security hardening tests for authenticated session and buffer access."""

from fastapi.testclient import TestClient

from backend.app.auth import api_key_principal
from backend.app.config import settings
from backend.app.message_buffer import (
    clear_pending_chat_response,
    set_pending_chat_response,
)
from backend.app.rate_limit import rate_limiter
from backend.app.session import session_manager
from backend.main import app


def _client_with_auth(monkeypatch) -> TestClient:
    monkeypatch.setenv("CHAT_API_KEY", "test-secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "120")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    settings.reset()
    rate_limiter.reset()
    app.dependency_overrides.clear()
    return TestClient(app)


def test_buffer_result_requires_api_key(monkeypatch) -> None:
    client = _client_with_auth(monkeypatch)

    response = client.get("/buffer-result/session-1")

    assert response.status_code == 401


def test_buffer_result_requires_session_owner(monkeypatch) -> None:
    client = _client_with_auth(monkeypatch)
    session_id = "session-owned"
    set_pending_chat_response(session_id, "{}")

    response = client.get(
        f"/buffer-result/{session_id}",
        headers={"X-API-Key": "test-secret"},
    )

    assert response.status_code == 403
    clear_pending_chat_response(session_id)


def test_buffer_result_returns_owned_pending_response(monkeypatch) -> None:
    client = _client_with_auth(monkeypatch)
    session_id = "session-owned-ready"
    principal = api_key_principal("test-secret")
    session_manager.bind_session(session_id, principal)
    set_pending_chat_response(session_id, '{"response":"ok"}')

    response = client.get(
        f"/buffer-result/{session_id}",
        headers={"X-API-Key": "test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["result"] == '{"response":"ok"}'


def test_chat_rejects_unknown_client_session_id(monkeypatch) -> None:
    client = _client_with_auth(monkeypatch)

    response = client.post(
        "/chat",
        json={"message": "Hola", "session_id": "client-selected"},
        headers={"X-API-Key": "test-secret"},
    )

    assert response.status_code == 403


def test_rate_limit_returns_429(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_KEY", "test-secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    settings.reset()
    rate_limiter.reset()
    app.dependency_overrides.clear()
    client = TestClient(app)

    headers = {"X-API-Key": "test-secret"}
    first_response = client.get("/buffer-result/unknown-session", headers=headers)
    second_response = client.get("/buffer-result/unknown-session", headers=headers)

    assert first_response.status_code == 403
    assert second_response.status_code == 429
    assert "Retry-After" in second_response.headers
