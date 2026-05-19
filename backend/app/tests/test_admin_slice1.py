"""Tests for Slice 1: Backend Foundation — Auth + S3 + Config.

Covers:
- Admin health endpoint authentication (200, 401, 403)
- S3Client extensions (list_objects, presigned_post, delete_objects)
- Settings reload atomicity
"""

import asyncio
import os
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import before any settings access so monkeypatch works reliably
from backend.app.config import settings


def _reset_settings() -> None:
    """Reset the settings proxy so next access reads fresh env."""
    settings.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with admin key configured.

    Yields a TestClient after resetting settings and setting ADMIN_API_KEY.
    """
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    _reset_settings()

    # We must import main AFTER patching env so module-level settings reads
    # the correct value.
    from backend.main import app

    with TestClient(app) as tc:
        yield tc

    _reset_settings()


class TestAdminHealth:
    """Authentication and health checks for the admin router."""

    def test_admin_health_authenticated(
        self, client: TestClient
    ) -> None:
        """GET /admin/health with valid key returns 200 and correct payload."""
        response = client.get(
            "/admin/health",
            headers={"X-Admin-API-Key": "test-admin-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "arte-chatbot-admin"

    def test_admin_health_missing_key(
        self, client: TestClient
    ) -> None:
        """GET /admin/health without key returns 401."""
        response = client.get("/admin/health")
        assert response.status_code == 401
        assert "Missing admin API key" in response.json()["detail"]

    def test_admin_health_invalid_key(
        self, client: TestClient
    ) -> None:
        """GET /admin/health with wrong key returns 403."""
        response = client.get(
            "/admin/health",
            headers={"X-Admin-API-Key": "bad-key"},
        )
        assert response.status_code == 403
        assert "Invalid admin API key" in response.json()["detail"]

    def test_admin_health_not_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /admin/health when ADMIN_API_KEY is unset returns 503."""
        # Use an explicit empty env var so the test is isolated even when the
        # developer's local .env file contains ADMIN_API_KEY.
        monkeypatch.setenv("ADMIN_API_KEY", "")
        _reset_settings()

        from backend.main import app

        with TestClient(app) as client:
            response = client.get(
                "/admin/health",
                headers={"X-Admin-API-Key": "some-key"},
            )
            assert response.status_code == 503
            assert "ADMIN_API_KEY not configured" in response.json()["detail"]

        _reset_settings()


class TestS3Extensions:
    """Unit tests for S3Client extension methods with mocked boto3."""

    @pytest.fixture
    def s3_client(self) -> Any:
        """Return an S3Client with a mocked boto3 client."""
        from backend.app.s3_client import S3Client

        client = S3Client(bucket_name="test-bucket")
        client._client = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_s3_list_objects_mock(self, s3_client: Any) -> None:
        """list_objects uses paginator and returns Contents."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "a.pdf", "Size": 123}]},
            {"Contents": [{"Key": "b.pdf", "Size": 456}]},
        ]
        s3_client.client.get_paginator.return_value = mock_paginator

        result = await s3_client.list_objects(prefix="raw/")

        assert len(result) == 2
        assert result[0]["Key"] == "a.pdf"
        assert result[1]["Key"] == "b.pdf"
        mock_paginator.paginate.assert_called_once_with(
            Bucket="test-bucket", Prefix="raw/"
        )

    @pytest.mark.asyncio
    async def test_s3_list_objects_empty(self, s3_client: Any) -> None:
        """list_objects returns empty list when no contents."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{}, {"Contents": []}]
        s3_client.client.get_paginator.return_value = mock_paginator

        result = await s3_client.list_objects(prefix="empty/")
        assert result == []

    @pytest.mark.asyncio
    async def test_s3_presigned_post_mock(self, s3_client: Any) -> None:
        """generate_presigned_post returns url and fields."""
        s3_client.client.generate_presigned_post.return_value = {
            "url": "https://test-bucket.s3.amazonaws.com/",
            "fields": {
                "key": "raw/paneles/x.pdf",
                "AWSAccessKeyId": "AKIA...",
            },
        }

        result = await s3_client.generate_presigned_post(
            key="raw/paneles/x.pdf",
            content_type="application/pdf",
            expires=3600,
        )

        assert result["url"] == "https://test-bucket.s3.amazonaws.com/"
        assert result["fields"]["key"] == "raw/paneles/x.pdf"
        call_kwargs = s3_client.client.generate_presigned_post.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "raw/paneles/x.pdf"
        assert call_kwargs["ExpiresIn"] == 3600
        conditions = call_kwargs["Conditions"]
        assert ["content-length-range", 1024, 104_857_600] in conditions

    @pytest.mark.asyncio
    async def test_s3_delete_objects_mock(self, s3_client: Any) -> None:
        """delete_objects calls delete_objects batch API."""
        s3_client.client.delete_objects.return_value = {}

        await s3_client.delete_objects(keys=["raw/a.pdf", "raw/b.pdf"])

        call_kwargs = s3_client.client.delete_objects.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        delete_arg = call_kwargs["Delete"]
        assert delete_arg["Quiet"] is True
        assert {obj["Key"] for obj in delete_arg["Objects"]} == {
            "raw/a.pdf",
            "raw/b.pdf",
        }

    @pytest.mark.asyncio
    async def test_s3_delete_object_mock(self, s3_client: Any) -> None:
        """delete_object calls delete_object for a single key."""
        s3_client.client.delete_object.return_value = {}

        await s3_client.delete_object(key="raw/a.pdf")

        call_kwargs = s3_client.client.delete_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "raw/a.pdf"

    @pytest.mark.asyncio
    async def test_s3_head_object_mock(self, s3_client: Any) -> None:
        """head_object returns metadata dict."""
        s3_client.client.head_object.return_value = {
            "ETag": '"abc123"',
            "ContentLength": 1024,
        }

        result = await s3_client.head_object(key="index/catalog_index.json")

        assert result["ETag"] == '"abc123"'
        assert result["ContentLength"] == 1024

    @pytest.mark.asyncio
    async def test_s3_list_objects_no_bucket(self) -> None:
        """list_objects raises S3DownloadError when bucket is not configured."""
        from backend.app.s3_client import S3Client, S3DownloadError

        client = S3Client(bucket_name="")
        with pytest.raises(S3DownloadError, match="S3 bucket name not configured"):
            await client.list_objects()

    @pytest.mark.asyncio
    async def test_s3_presigned_post_no_bucket(self) -> None:
        """generate_presigned_post raises S3UploadError when bucket missing."""
        from backend.app.s3_client import S3Client, S3UploadError

        client = S3Client(bucket_name="")
        with pytest.raises(S3UploadError, match="S3 bucket name not configured"):
            await client.generate_presigned_post(key="raw/x.pdf")


class TestSettingsReload:
    """Atomicity and correctness of settings.reload()."""

    def test_settings_reload_atomic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """reload() swaps the _instance so new reads pick up changed env."""
        monkeypatch.setenv("LLM_MODEL", "gpt-test-reload")
        _reset_settings()

        # Before reload, the old cached instance may still have the old value.
        # We force instantiation first.
        old_model = settings.llm_model

        monkeypatch.setenv("LLM_MODEL", "gpt-reloaded-value")
        settings.reload()

        # After reload, the new instance should see the updated env.
        assert settings.llm_model == "gpt-reloaded-value"

        _reset_settings()

    def test_settings_reload_concurrent_reads(self) -> None:
        """Concurrent reads during reload do not crash.

        Spins up multiple threads that read settings attributes while
        reload() is called repeatedly.
        """
        import threading
        import time

        _reset_settings()

        errors: list[Exception] = []
        stop_event = threading.Event()

        def reader() -> None:
            while not stop_event.is_set():
                try:
                    _ = settings.llm_model
                    _ = settings.aws_region
                    _ = settings.admin_api_key
                except Exception as exc:
                    errors.append(exc)

        def reloader() -> None:
            for _ in range(50):
                settings.reload()

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()

        reloader()

        stop_event.set()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent read errors: {errors}"

        _reset_settings()
