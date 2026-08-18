import csv
import json

import httpx
import pytest

from evaluation.harness.run import run_single_query, save_results_csv


@pytest.mark.asyncio
async def test_run_single_query_maps_backend_escalate_field() -> None:
    """The backend returns `escalate`; the harness reports `escalated`."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "Escalation response",
                "session_id": "session-1",
                "escalate": True,
                "source_documents": [],
                "num_sources": 0,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_single_query(
            client,
            {
                "id": "q001",
                "query": "Necesito una cotización",
                "should_escalate": True,
            },
        )

    assert result["error"] == ""
    assert result["escalated"] is True


@pytest.mark.asyncio
async def test_run_single_query_uses_measured_latency_when_api_omits_it() -> None:
    """CI results should not report zero latency when the backend omits latency_ms."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "OK",
                "session_id": "session-1",
                "escalate": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_single_query(
            client,
            {
                "id": "q001",
                "query": "Hola",
            },
        )

    assert result["error"] == ""
    assert result["latency_ms"] > 0


@pytest.mark.asyncio
async def test_run_single_query_preserves_explicit_api_latency() -> None:
    """If an API starts returning latency_ms, preserve that value."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "OK",
                "session_id": "session-1",
                "latency_ms": 123.45,
                "escalated": True,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_single_query(
            client,
            {
                "id": "q001",
                "query": "Hola",
            },
        )

    assert result["latency_ms"] == 123.45
    assert result["escalated"] is True


def test_save_results_csv_normalizes_source_document_objects(tmp_path) -> None:
    """Structured source metadata is serialized instead of joined as strings."""
    output_path = save_results_csv(
        [
            {
                "query_id": "q001",
                "source_documents": [
                    {"ruta": "raw/paneles/test.pdf", "contenido_relevante": None}
                ],
            }
        ],
        "fixture",
        tmp_path,
    )

    with output_path.open(encoding="utf-8") as csv_file:
        row = next(csv.DictReader(csv_file))

    assert json.loads(row["source_documents"]) == [
        {"contenido_relevante": None, "ruta": "raw/paneles/test.pdf"}
    ]
