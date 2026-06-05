"""Tests for admin S3 explorer endpoints used by Slice 5 frontend."""

from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.s3_client import S3DownloadError, S3ObjectNotFoundError


def _reset_settings() -> None:
    """Reset settings proxy so each test reads patched environment values."""
    settings.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with admin key configured."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    _reset_settings()

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client

    _reset_settings()


def test_s3_tree_builds_hierarchy(client: TestClient) -> None:
    """GET /admin/s3/tree returns hierarchical nodes from S3 objects."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.list_objects = AsyncMock(
            return_value=[
                {
                    "Key": "raw/",
                    "Size": 0,
                    "LastModified": datetime(2026, 5, 18, tzinfo=timezone.utc),
                },
                {
                    "Key": "raw/paneles/panel-a.pdf",
                    "Size": 1024,
                    "LastModified": datetime(2026, 5, 18, tzinfo=timezone.utc),
                },
                {
                    "Key": "raw/inversores/inversor-a.pdf",
                    "Size": 2048,
                    "LastModified": datetime(2026, 5, 18, tzinfo=timezone.utc),
                },
            ]
        )

        response = client.get(
            "/admin/s3/tree?prefix=raw/",
            headers={"X-Admin-API-Key": "test-admin-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "raw"
    assert data[0]["type"] == "folder"
    child_names = {child["name"] for child in data[0]["children"]}
    assert child_names == {"paneles", "inversores"}


def test_s3_tree_rejects_unsafe_prefix(client: TestClient) -> None:
    """GET /admin/s3/tree rejects traversal-like prefixes."""
    response = client.get(
        "/admin/s3/tree?prefix=../secrets/",
        headers={"X-Admin-API-Key": "test-admin-key"},
    )

    assert response.status_code == 422


def test_presigned_upload_success(client: TestClient) -> None:
    """POST /admin/s3/presigned-upload returns URL and fields."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(side_effect=S3ObjectNotFoundError("not found"))
        mock_s3.generate_presigned_post = AsyncMock(
            return_value={
                "url": "https://bucket.s3.amazonaws.com/",
                "fields": {"key": "raw/paneles/a.pdf"},
            }
        )

        response = client.post(
            "/admin/s3/presigned-upload",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/a.pdf", "content_type": "application/pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://bucket.s3.amazonaws.com/"
    assert data["key"] == "raw/paneles/a.pdf"


def test_presigned_upload_accepts_real_s3_product_key(client: TestClient) -> None:
    """POST /admin/s3/presigned-upload accepts valid S3 keys with spaces."""
    key = "raw/paneles/Jinko Tiger Pro 460W (Ficha Técnica).pdf"
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(side_effect=S3ObjectNotFoundError("not found"))
        mock_s3.generate_presigned_post = AsyncMock(
            return_value={
                "url": "https://bucket.s3.amazonaws.com/",
                "fields": {"key": key},
            }
        )

        response = client.post(
            "/admin/s3/presigned-upload",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": key, "content_type": "application/pdf"},
        )

    assert response.status_code == 200
    assert response.json()["key"] == key


def test_presigned_upload_conflict(client: TestClient) -> None:
    """POST /admin/s3/presigned-upload returns 409 when object exists."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(return_value={"ETag": '"abc"'})

        response = client.post(
            "/admin/s3/presigned-upload",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/a.pdf", "content_type": "application/pdf"},
        )

    assert response.status_code == 409


def test_presigned_upload_head_error_returns_500(client: TestClient) -> None:
    """POST /admin/s3/presigned-upload does not hide non-404 S3 failures."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(side_effect=S3DownloadError("S3 down"))

        response = client.post(
            "/admin/s3/presigned-upload",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/a.pdf", "content_type": "application/pdf"},
        )

    assert response.status_code == 500
    assert "S3 down" in response.json()["detail"]


def test_presigned_download_success(client: TestClient) -> None:
    """POST /admin/s3/presigned-download returns a short-lived read URL."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(return_value={"ETag": '"abc"'})
        mock_s3.generate_presigned_get_url = AsyncMock(
            return_value="https://bucket.s3.amazonaws.com/raw/paneles/a.pdf?sig=1"
        )

        response = client.post(
            "/admin/s3/presigned-download",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/a.pdf", "disposition": "inline"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "url": "https://bucket.s3.amazonaws.com/raw/paneles/a.pdf?sig=1",
        "key": "raw/paneles/a.pdf",
        "expires_in": 300,
    }
    mock_s3.head_object.assert_awaited_once_with("raw/paneles/a.pdf")
    mock_s3.generate_presigned_get_url.assert_awaited_once_with(
        key="raw/paneles/a.pdf",
        response_content_disposition='inline; filename="a.pdf"',
        expires=300,
    )


def test_presigned_download_rejects_invalid_key(client: TestClient) -> None:
    """POST /admin/s3/presigned-download rejects unsafe paths."""
    response = client.post(
        "/admin/s3/presigned-download",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={"key": "../secrets.pdf", "disposition": "inline"},
    )

    assert response.status_code == 422


def test_presigned_download_returns_404_for_missing_object(
    client: TestClient,
) -> None:
    """POST /admin/s3/presigned-download returns 404 when the file is missing."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(side_effect=S3ObjectNotFoundError("not found"))

        response = client.post(
            "/admin/s3/presigned-download",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/missing.pdf", "disposition": "inline"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "S3 object not found"


def test_presigned_download_head_error_returns_500(client: TestClient) -> None:
    """POST /admin/s3/presigned-download does not hide S3 failures."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.head_object = AsyncMock(side_effect=S3DownloadError("S3 down"))

        response = client.post(
            "/admin/s3/presigned-download",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"key": "raw/paneles/a.pdf", "disposition": "attachment"},
        )

    assert response.status_code == 500
    assert "S3 down" in response.json()["detail"]


def test_delete_s3_objects(client: TestClient) -> None:
    """DELETE /admin/s3/objects deletes validated keys."""
    with patch("backend.app.admin_s3.s3_client") as mock_s3:
        mock_s3.delete_objects = AsyncMock(return_value=None)

        response = client.request(
            "DELETE",
            "/admin/s3/objects",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"keys": ["raw/paneles/a.pdf", "guides/cotizacion.md"]},
        )

    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    mock_s3.delete_objects.assert_awaited_once_with(
        ["raw/paneles/a.pdf", "guides/cotizacion.md"]
    )
