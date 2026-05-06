"""Query executor module for the evaluation orchestrator.

Handles execution of queries against the /chat endpoint with
concurrency control and error handling.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from evaluation.orchestrator.settings import orchestrator_settings

logger = logging.getLogger(__name__)

API_BASE_URL = orchestrator_settings.api_base_url
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
CHAT_API_KEY = orchestrator_settings.chat_api_key
MAX_CONCURRENT = orchestrator_settings.max_concurrent_requests
REQUEST_TIMEOUT = orchestrator_settings.request_timeout


async def execute_single_query(
    client: httpx.AsyncClient,
    query_data: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single query against the /chat endpoint.

    Args:
        client: httpx.AsyncClient instance.
        query_data: Dictionary containing query data with 'id', 'query', etc.

    Returns:
        Dictionary with query data plus response fields (response, session_id,
        latency_ms, escalated, source_documents, error).
    """
    query_id = query_data.get("id", "unknown")
    query = query_data.get("query", "")

    result: dict[str, Any] = {
        "query_id": query_id,
        "query": query,
        "expected_intent": query_data.get("expected_intent", ""),
        "expected_intent_type": query_data.get("expected_intent_type", ""),
        "should_escalate": query_data.get("should_escalate", False),
        "complexity": query_data.get("complexity", ""),
        "response": "",
        "session_id": "",
        "latency_ms": 0.0,
        "escalated": False,
        "error": "",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "num_sources": 0,
        "source_documents": [],
    }

    try:
        start_time = datetime.now(timezone.utc)
        headers = {}
        if CHAT_API_KEY:
            headers["X-API-Key"] = CHAT_API_KEY

        api_response = await client.post(
            CHAT_ENDPOINT,
            json={"message": query},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        end_time = datetime.now(timezone.utc)

        if api_response.status_code == 200:
            data = api_response.json()
            result["response"] = data.get("response", "")
            result["session_id"] = data.get("session_id", "")
            result["latency_ms"] = data.get("latency_ms", 0.0)
            result["escalated"] = data.get("escalated", False)
            result["source_documents"] = data.get("source_documents", [])
            result["num_sources"] = data.get("num_sources", 0)
        else:
            result["error"] = f"HTTP {api_response.status_code}: {api_response.text}"

    except httpx.ConnectError:
        result["error"] = f"Connection error: Could not connect to {CHAT_ENDPOINT}"
    except httpx.TimeoutException:
        result["error"] = f"Request timed out after {REQUEST_TIMEOUT} seconds"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


async def execute_batch(
    dataset: list[dict[str, Any]],
    progress_callback: callable | None = None,
) -> list[dict[str, Any]]:
    """Execute a batch of queries against the /chat endpoint.

    Args:
        dataset: List of query dictionaries.
        progress_callback: Optional callback function(current, total, result)
            called after each query completes.

    Returns:
        List of result dictionaries with response data.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_with_semaphore(
        client: httpx.AsyncClient,
        query_data: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        async with semaphore:
            result = await execute_single_query(client, query_data)
            if progress_callback:
                progress_callback(index, len(dataset), result)
            return result

    async with httpx.AsyncClient() as client:
        tasks = [
            run_with_semaphore(client, query_data, i)
            for i, query_data in enumerate(dataset, 1)
        ]
        results = await asyncio.gather(*tasks)

    return list(results)


async def check_api_health() -> bool:
    """Check if the API is healthy and reachable.

    Returns:
        True if the API responds with status 200, False otherwise.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_BASE_URL}/health",
                timeout=5.0,
            )
            return response.status_code == 200
    except Exception as e:
        logger.error("API health check failed: %s", e)
        return False