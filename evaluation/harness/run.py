"""
Evaluation Harness for ARTE Chatbot

This module provides the main script to run automated evaluation tests
against the /chat endpoint and record the results.
"""

import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from evaluation.harness.config import harness_settings

logger = logging.getLogger(__name__)

# Configuration from centralized settings
API_BASE_URL = harness_settings.api_base_url
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
DATASET_PATH = harness_settings.dataset_path
OUTPUT_DIR = harness_settings.output_dir


def load_dataset() -> list[dict[str, Any]]:
    """Load the test dataset from JSON file."""
    if not DATASET_PATH.exists():
        logger.error("Dataset not found at %s", DATASET_PATH)
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_results_json(results: list[dict[str, Any]], timestamp: str) -> Path:
    """Save results to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"results_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "total_queries": len(results),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


def save_results_csv(results: list[dict[str, Any]], timestamp: str) -> Path:
    """Save results to CSV file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"results_{timestamp}.csv"

    if not results:
        return output_path

    fieldnames = [
        "query_id",
        "query",
        "expected_intent",
        "should_escalate",
        "response",
        "session_id",
        "latency_ms",
        "escalated",
        "error",
        "timestamp",
        "num_sources",
        "source_documents",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            source_docs = result.get("source_documents", [])
            row: dict[str, Any] = {
                "query_id": result.get("query_id", ""),
                "query": result.get("query", ""),
                "expected_intent": result.get("expected_intent", ""),
                "should_escalate": result.get("should_escalate", ""),
                "response": result.get("response", ""),
                "session_id": result.get("session_id", ""),
                "latency_ms": result.get("latency_ms", ""),
                "escalated": result.get("escalated", ""),
                "error": result.get("error", ""),
                "timestamp": result.get("timestamp", ""),
                "num_sources": result.get("num_sources", 0),
                "source_documents": "; ".join(source_docs)
                if isinstance(source_docs, list)
                else source_docs,
            }
            writer.writerow(row)

    return output_path


def run_single_query(
    client: httpx.Client, query_data: dict[str, Any]
) -> dict[str, Any]:
    """Execute a single query against the /chat endpoint."""
    query_id = query_data.get("id", "unknown")
    query = query_data.get("query", "")

    result: dict[str, Any] = {
        "query_id": query_id,
        "query": query,
        "expected_intent": query_data.get("expected_intent", ""),
        "should_escalate": query_data.get("should_escalate", False),
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
        response = client.post(
            CHAT_ENDPOINT,
            json={"message": query},
            timeout=30.0,
        )
        end_time = datetime.now(timezone.utc)

        if response.status_code == 200:
            data = response.json()
            result["response"] = data.get("response", "")
            result["session_id"] = data.get("session_id", "")
            result["latency_ms"] = data.get("latency_ms", 0.0)
            result["escalated"] = data.get("escalated", False)
            result["source_documents"] = data.get("source_documents", [])
            result["num_sources"] = data.get("num_sources", 0)
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text}"

    except httpx.ConnectError:
        result["error"] = f"Connection error: Could not connect to {CHAT_ENDPOINT}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out after 30 seconds"
    except Exception as e:  # pylint: disable=broad-except
        result["error"] = f"Unexpected error: {str(e)}"

    return result


def run_harness() -> list[dict[str, Any]]:
    """Run the complete evaluation harness."""
    print("=" * 60)
    print("ARTE Chatbot Evaluation Harness")
    print("=" * 60)
    print(f"Target endpoint: {CHAT_ENDPOINT}")
    print(f"Dataset: {DATASET_PATH}")
    print()

    # Load dataset
    dataset = load_dataset()
    logger.info("Loaded %d test queries", len(dataset))
    print(f"Loaded {len(dataset)} test queries")
    print()

    # Check API availability
    try:
        with httpx.Client() as client:
            health_response = client.get(f"{API_BASE_URL}/health", timeout=5.0)
            if health_response.status_code == 200:
                logger.info("API health check passed")
                print("✓ API is healthy")
            else:
                logger.warning(
                    "API health check returned status %d",
                    health_response.status_code,
                )
                print(f"⚠ API returned status {health_response.status_code}")
    except httpx.ConnectError:
        logger.error("Cannot connect to API at %s", API_BASE_URL)
        print(f"✗ Error: Cannot connect to API at {API_BASE_URL}")
        print("  Make sure the backend is running (docker compose up)")
        sys.exit(1)

    print()
    print("Running queries...")
    print("-" * 60)

    results: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for i, query_data in enumerate(dataset, 1):
            query_id = query_data.get("id", f"q{i:03d}")
            query_preview = query_data.get("query", "")[:50]

            logger.debug("Running query %d/%d: %s", i, len(dataset), query_id)
            print(f"[{i}/{len(dataset)}] {query_id}: {query_preview}...")

            result = run_single_query(client, query_data)
            results.append(result)

            if result["error"]:
                logger.error("Query %s failed: %s", query_id, result["error"])
                print(f"    ✗ Error: {result['error']}")
            else:
                logger.debug(
                    "Query %s completed: %.2fms",
                    query_id,
                    result["latency_ms"],
                )
                print(f"    ✓ Latency: {result['latency_ms']:.2f}ms")

    print()
    print("-" * 60)
    print(f"Completed {len(results)} queries")

    # Calculate statistics
    successful = sum(1 for r in results if not r["error"])
    failed = sum(1 for r in results if r["error"])
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0

    logger.info(
        "Evaluation complete: successful=%d, failed=%d, avg_latency=%.2fms",
        successful,
        failed,
        avg_latency,
    )

    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Avg latency: {avg_latency:.2f}ms")
    print(f"Min latency: {min_latency:.2f}ms")
    print(f"Max latency: {max_latency:.2f}ms")

    # Save results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = save_results_json(results, timestamp)
    csv_path = save_results_csv(results, timestamp)

    print()
    print("Results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")
    print()
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_harness()
