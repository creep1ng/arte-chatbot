"""Tests for Slice 2: Backend Domain — Catalog + Guides + Logs.

Covers:
- Catalog CRUD with optimistic locking (ETag)
- Guides CRUD with intent sanitization
- Conversation logs listing, filtering, and detail retrieval
"""

import json
from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.conversation_logger import ConversationLogEntry


def _reset_settings() -> None:
    """Reset the settings proxy so next access reads fresh env."""
    settings.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with admin key configured."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    _reset_settings()

    from backend.main import app

    with TestClient(app) as tc:
        yield tc

    _reset_settings()


@pytest.fixture(autouse=True)
def reset_catalog() -> Generator[None, None, None]:
    """Reset the catalog singleton between tests."""
    from backend.app import catalog as catalog_module

    catalog_module._catalog_instance = None
    yield
    catalog_module._catalog_instance = None


class TestCatalog:
    """Tests for GET /admin/catalog and PUT /admin/catalog."""

    def test_get_catalog(self, client: TestClient) -> None:
        """GET /admin/catalog returns parsed catalog index."""
        catalog_data = {
            "productos": [
                {
                    "nombre_comercial": "Panel X",
                    "fabricante": "TestCo",
                    "categoria": "paneles",
                    "ruta_s3": "raw/paneles/x.pdf",
                    "variantes": [{"modelo": "X-100", "parametros_clave": {}}],
                }
            ]
        }
        with patch("backend.app.catalog.s3_client") as mock_s3:
            mock_s3.download_pdf = MagicMock(
                return_value=json.dumps(catalog_data).encode("utf-8")
            )
            response = client.get(
                "/admin/catalog",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["products"]) == 1
            assert data["products"][0]["nombre_comercial"] == "Panel X"

    def test_put_catalog_optimistic_lock(self, client: TestClient) -> None:
        """PUT /admin/catalog with matching ETag succeeds and reloads cache."""
        catalog_data = {
            "products": [
                {
                    "nombre_comercial": "Panel Y",
                    "fabricante": "TestCo",
                    "categoria": "inversores",
                    "ruta_s3": "raw/inv/y.pdf",
                    "variantes": [],
                }
            ]
        }
        with (
            patch("backend.app.catalog.s3_client") as mock_cat_s3,
            patch("backend.app.admin_catalog.s3_client") as mock_adm_s3,
        ):
            mock_cat_s3.download_pdf = MagicMock(
                return_value=json.dumps(catalog_data).encode("utf-8")
            )
            mock_cat_s3.put_object = MagicMock(return_value=None)
            mock_adm_s3.head_object = AsyncMock(return_value={"ETag": '"abc123"'})

            response = client.put(
                "/admin/catalog",
                headers={
                    "X-Admin-API-Key": "test-admin-key",
                    "If-Match": '"abc123"',
                },
                json=catalog_data,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["products"][0]["nombre_comercial"] == "Panel Y"
            mock_adm_s3.head_object.assert_awaited_once()
            mock_cat_s3.put_object.assert_called_once()

    def test_put_catalog_etag_mismatch(self, client: TestClient) -> None:
        """PUT /admin/catalog with mismatched ETag returns 409 Conflict."""
        with patch("backend.app.admin_catalog.s3_client") as mock_s3:
            mock_s3.head_object = AsyncMock(return_value={"ETag": '"different"'})
            response = client.put(
                "/admin/catalog",
                headers={
                    "X-Admin-API-Key": "test-admin-key",
                    "If-Match": '"abc123"',
                },
                json={"products": []},
            )
            assert response.status_code == 409
            assert "modified by another user" in response.json()["detail"]

    def test_put_catalog_validation_error(self, client: TestClient) -> None:
        """PUT /admin/catalog with invalid body returns 422."""
        response = client.put(
            "/admin/catalog",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"products": [{"nombre_comercial": "X"}]},
        )
        assert response.status_code == 422


class TestGuides:
    """Tests for guides CRUD endpoints."""

    def test_list_guides(self, client: TestClient) -> None:
        """GET /admin/guides lists markdown files under guides/."""
        with patch("backend.app.admin_guides.s3_client") as mock_s3:
            mock_s3.list_objects = AsyncMock(
                return_value=[
                    {
                        "Key": "guides/faq.md",
                        "LastModified": datetime(2026, 5, 1, 10, 0, 0),
                    },
                    {
                        "Key": "guides/pricing.md",
                        "LastModified": datetime(2026, 5, 2, 10, 0, 0),
                    },
                    {"Key": "guides/other.txt"},
                ]
            )
            response = client.get(
                "/admin/guides",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            intents = {g["intent"] for g in data}
            assert intents == {"faq", "pricing"}

    def test_get_guide(self, client: TestClient) -> None:
        """GET /admin/guides/{intent} returns markdown content."""
        with patch("backend.app.admin_guides.s3_client") as mock_s3:
            mock_s3.download_pdf = MagicMock(return_value=b"# FAQ\n\nThis is the FAQ.")
            response = client.get(
                "/admin/guides/faq",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["intent"] == "faq"
            assert "# FAQ" in data["content"]

    def test_update_guide(self, client: TestClient) -> None:
        """PUT /admin/guides/{intent} uploads markdown to S3."""
        with patch("backend.app.admin_guides.s3_client") as mock_s3:
            mock_s3.put_object = MagicMock(return_value=None)
            response = client.put(
                "/admin/guides/faq",
                headers={"X-Admin-API-Key": "test-admin-key"},
                json={"intent": "faq", "content": "# Updated FAQ"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "# Updated FAQ"
            mock_s3.put_object.assert_called_once()

    def test_delete_guide(self, client: TestClient) -> None:
        """DELETE /admin/guides/{intent} removes the file from S3."""
        with patch("backend.app.admin_guides.s3_client") as mock_s3:
            mock_s3.head_object = AsyncMock(return_value={"ETag": '"x"'})
            mock_s3.delete_object = AsyncMock(return_value=None)
            response = client.delete(
                "/admin/guides/faq",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            assert response.json() == {"deleted": True}
            mock_s3.head_object.assert_awaited_once()
            mock_s3.delete_object.assert_awaited_once()

    def test_delete_guide_not_found(self, client: TestClient) -> None:
        """DELETE /admin/guides/{intent} returns 404 when guide missing."""
        from backend.app.s3_client import S3DownloadError

        with patch("backend.app.admin_guides.s3_client") as mock_s3:
            mock_s3.head_object = AsyncMock(side_effect=S3DownloadError("NoSuchKey"))
            response = client.delete(
                "/admin/guides/faq",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 404
            assert "Guide not found" in response.json()["detail"]


class TestLogs:
    """Tests for conversation logs endpoints."""

    def test_list_logs_filtered(self, client: TestClient) -> None:
        """GET /admin/logs with filters returns correct summaries."""
        entry1 = ConversationLogEntry(
            session_id="sess1",
            turn_number=1,
            timestamp="2026-05-01T10:00:00Z",
            user_message="hi",
            bot_response="hello",
            intent_type="FAQ",
            escalate=False,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            response_time_ms=100.0,
            model="gpt-4",
            git_commit_hash="abc",
        )
        entry2 = ConversationLogEntry(
            session_id="sess1",
            turn_number=2,
            timestamp="2026-05-01T10:05:00Z",
            user_message="bye",
            bot_response="goodbye",
            intent_type="FAQ",
            escalate=True,
            input_tokens=5,
            output_tokens=5,
            total_tokens=10,
            response_time_ms=50.0,
            model="gpt-4",
            git_commit_hash="abc",
        )
        entry3 = ConversationLogEntry(
            session_id="sess2",
            turn_number=1,
            timestamp="2026-05-02T10:00:00Z",
            user_message="hello",
            bot_response="hi",
            intent_type="product_info",
            escalate=False,
            input_tokens=8,
            output_tokens=4,
            total_tokens=12,
            response_time_ms=80.0,
            model="gpt-4",
            git_commit_hash="abc",
        )

        with patch("backend.app.conversation_logger._log_reader_s3") as mock_s3:
            mock_s3.list_objects = AsyncMock(
                return_value=[
                    {"Key": "conversations/sess1/1_2026-05-01T10:00:00Z.json"},
                    {"Key": "conversations/sess1/2_2026-05-01T10:05:00Z.json"},
                    {"Key": "conversations/sess2/1_2026-05-02T10:00:00Z.json"},
                ]
            )

            def mock_download(key: str) -> bytes:
                if "sess1/1_" in key:
                    return entry1.model_dump_json().encode("utf-8")
                elif "sess1/2_" in key:
                    return entry2.model_dump_json().encode("utf-8")
                elif "sess2/1_" in key:
                    return entry3.model_dump_json().encode("utf-8")
                return b"{}"

            mock_s3.download_pdf = MagicMock(side_effect=mock_download)

            response = client.get(
                "/admin/logs?escalated=true",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["session_id"] == "sess1"
            assert data["items"][0]["escalated"] is True

    def test_get_log_detail(self, client: TestClient) -> None:
        """GET /admin/logs/{session_id} returns sorted transcript."""
        entry1 = ConversationLogEntry(
            session_id="sess1",
            turn_number=1,
            timestamp="2026-05-01T10:00:00Z",
            user_message="hi",
            bot_response="hello",
            intent_type="FAQ",
            escalate=False,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            response_time_ms=100.0,
            model="gpt-4",
            git_commit_hash="abc",
        )
        entry2 = ConversationLogEntry(
            session_id="sess1",
            turn_number=2,
            timestamp="2026-05-01T10:05:00Z",
            user_message="bye",
            bot_response="goodbye",
            intent_type="FAQ",
            escalate=False,
            input_tokens=5,
            output_tokens=5,
            total_tokens=10,
            response_time_ms=50.0,
            model="gpt-4",
            git_commit_hash="abc",
        )

        with patch("backend.app.conversation_logger._log_reader_s3") as mock_s3:
            mock_s3.list_objects = AsyncMock(
                return_value=[
                    {"Key": "conversations/sess1/2_2026-05-01T10:05:00Z.json"},
                    {"Key": "conversations/sess1/1_2026-05-01T10:00:00Z.json"},
                ]
            )

            def mock_download(key: str) -> bytes:
                if "1_" in key:
                    return entry1.model_dump_json().encode("utf-8")
                return entry2.model_dump_json().encode("utf-8")

            mock_s3.download_pdf = MagicMock(side_effect=mock_download)

            response = client.get(
                "/admin/logs/sess1",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["turn_number"] == 1
            assert data[1]["turn_number"] == 2
