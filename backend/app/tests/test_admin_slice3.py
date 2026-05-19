"""Tests for Slice 3: Dashboard metrics and config endpoints."""

from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.conversation_logger import ConversationLogEntry
from backend.app.session import session_manager


def _reset_settings() -> None:
    """Reset the settings proxy so next access reads fresh env."""
    settings.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with admin key configured."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-openai")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-access-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-key")
    monkeypatch.setenv("CHAT_API_KEY", "chat-secret")
    _reset_settings()

    from backend.main import app

    with TestClient(app) as tc:
        yield tc

    _reset_settings()


@pytest.fixture(autouse=True)
def reset_session_manager() -> Generator[None, None, None]:
    """Clear session metrics before and after each test."""
    session_manager.sessions.clear()
    session_manager.profiles.clear()
    session_manager.token_totals.clear()
    session_manager.intent_counts.clear()
    session_manager.escalation_count = 0
    session_manager.metric_turn_count = 0
    yield
    session_manager.sessions.clear()
    session_manager.profiles.clear()
    session_manager.token_totals.clear()
    session_manager.intent_counts.clear()
    session_manager.escalation_count = 0
    session_manager.metric_turn_count = 0


def test_dashboard_metrics(client: TestClient) -> None:
    """GET /admin/dashboard/metrics returns session and log aggregates."""
    session_manager.add_turn("sess1", "hi", "hello")
    session_manager.add_turn("sess2", "quote", "human")
    session_manager.add_token_usage("sess1", 10, 5, 15)
    session_manager.add_token_usage("sess2", 20, 8, 28)

    entry1 = ConversationLogEntry(
        session_id="sess1",
        turn_number=1,
        timestamp="2026-05-18T20:00:00Z",
        user_message="hi",
        bot_response="hello",
        intent_type="FAQ",
        escalate=False,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        response_time_ms=100.0,
        model="gpt-test",
        git_commit_hash="abc",
    )
    entry2 = ConversationLogEntry(
        session_id="sess2",
        turn_number=1,
        timestamp="2026-05-18T20:05:00Z",
        user_message="quote",
        bot_response="human",
        intent_type="escalate_quote",
        escalate=True,
        input_tokens=20,
        output_tokens=8,
        total_tokens=28,
        response_time_ms=150.0,
        model="gpt-test",
        git_commit_hash="abc",
    )

    with (
        patch("backend.app.admin_dashboard.datetime") as mock_datetime,
        patch("backend.app.admin_dashboard.s3_client") as mock_s3,
    ):
        from datetime import datetime, timezone

        mock_datetime.now.return_value = datetime(
            2026, 5, 18, 21, 0, 0, tzinfo=timezone.utc
        )
        mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
        mock_s3.list_objects = AsyncMock(
            return_value=[
                {"Key": "conversations/sess1/1_2026-05-18T20:00:00Z.json"},
                {"Key": "conversations/sess2/1_2026-05-18T20:05:00Z.json"},
            ]
        )
        mock_s3.download_pdf = MagicMock(
            side_effect=[
                entry1.model_dump_json().encode("utf-8"),
                entry2.model_dump_json().encode("utf-8"),
            ]
        )

        response = client.get(
            "/admin/dashboard/metrics",
            headers={"X-Admin-API-Key": "test-admin-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["active_sessions"] == 2
    assert data["total_input_tokens"] == 30
    assert data["total_output_tokens"] == 13
    assert data["total_tokens"] == 43
    assert data["escalation_rate"] == 0.5
    assert data["intent_distribution"] == {"FAQ": 1, "escalate_quote": 1}


def test_get_config_redacts_secrets(client: TestClient) -> None:
    """GET /admin/config never exposes configured secret values."""
    response = client.get(
        "/admin/config",
        headers={"X-Admin-API-Key": "test-admin-key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mutable"]["admin_api_key"] == "***REDACTED***"
    assert data["immutable"]["openai_api_key"] == "***REDACTED***"
    assert data["immutable"]["aws_access_key_id"] == "***REDACTED***"
    assert data["immutable"]["aws_secret_access_key"] == "***REDACTED***"
    assert data["immutable"]["chat_api_key"] == "***REDACTED***"
    serialized = str(data)
    assert "sk-secret-openai" not in serialized
    assert "aws-secret-key" not in serialized
    assert "chat-secret" not in serialized


def test_put_config_hot_reload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /admin/config updates env-backed mutable settings and reloads."""
    monkeypatch.setenv("LLM_MODEL", "gpt-before")
    settings.reload()

    response = client.put(
        "/admin/config",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={"llm_model": "gpt-after", "conversation_logging_enabled": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mutable"]["llm_model"] == "gpt-after"
    assert data["mutable"]["conversation_logging_enabled"] is True
    assert settings.llm_model == "gpt-after"
    assert settings.conversation_logging_enabled is True
