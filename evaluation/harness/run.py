"""
Evaluation Harness for ARTE Chatbot

This module provides the main script to run automated evaluation tests
against the /chat endpoint and record the results.

Usage:
    python -m evaluation.harness.run
    python -m evaluation.harness.run --no-upload
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from evaluation.harness.config import harness_settings
from evaluation.storage import get_commit_hash, save_results, upload_to_s3

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE_URL = harness_settings.api_base_url
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
DATASET_PATH = harness_settings.dataset_path
OUTPUT_DIR = harness_settings.output_dir


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Evaluation Harness for ARTE Chatbot")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip S3 upload, save results locally only",
    )
    return parser.parse_args()


def load_dataset() -> list[dict[str, Any]]:
    """Load the test dataset from JSON file."""
    if not DATASET_PATH.exists():
        logger.error("Dataset not found at %s", DATASET_PATH)
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


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
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


def run_harness(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Run the complete evaluation harness."""
    print("=" * 60)
    print("ARTE Chatbot Evaluation Harness")
    print("=" * 60)
    print(f"Target endpoint: {CHAT_ENDPOINT}")
    print(f"Dataset: {DATASET_PATH}")
    print(f"Sprint: {sprint}")
    print()

    git_commit = get_git_commit()
    git_branch = get_git_branch()
    print(f"Git commit: {git_commit}")
    print(f"Git branch: {git_branch}")
    print()

    dataset = load_dataset()
    logger.info("Loaded %d test queries", len(dataset))
    print(f"Loaded {len(dataset)} test queries")
    print()

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

    successful = sum(1 for r in results if not r["error"])
    failed = sum(1 for r in results if r["error"])
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0

    # Calculate escalation rate
    expected_escalations = sum(1 for r in results if r.get("should_escalate", False))
    actual_escalations = sum(1 for r in results if r.get("escalated", False))
    correct_escalations = sum(
        1
        for r in results
        if r.get("should_escalate", False) == r.get("escalated", False)
    )
    escalation_accuracy = (correct_escalations / len(results) * 100) if results else 0
    escalation_rate = (actual_escalations / len(results) * 100) if results else 0

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
    print(f"Escalation rate: {escalation_rate:.1f}%")
    print(f"Escalation accuracy: {escalation_accuracy:.1f}%")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    csv_path = save_results_csv(results, timestamp)
    print()
    print("CSV saved to:", csv_path)

    commit_hash = get_commit_hash()

    payload = {
        "total_queries": len(results),
        "successful": successful,
        "failed": failed,
        "avg_latency_ms": round(avg_latency, 2),
        "min_latency_ms": round(min_latency, 2),
        "max_latency_ms": round(max_latency, 2),
        "results": results,
    }

    json_path, s3_key = save_results(
        OUTPUT_DIR, "harness", payload, commit_hash, timestamp
    )
    print(f"JSON saved to: {json_path}")

    if not args.no_upload:
        upload_to_s3(json_path, s3_key)

    print()

    # Upload to S3 if requested
    if upload_s3:
        print("Uploading results to S3...")
        try:
            s3_client = S3ReportsClient()
            s3_key = s3_client.build_s3_key(sprint, "harness", timestamp)

            with open(json_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)

            if s3_client.upload_json(report_data, s3_key):
                print(f"✓ Uploaded to s3://{s3_client.BUCKET_NAME}/{s3_key}")
            else:
                print("✗ Failed to upload to S3")
        except ValueError as e:
            print(f"✗ S3 upload skipped: {e}")

    print()
    print("=" * 60)

    return results


if __name__ == "__main__":
    args = parse_args()
    run_harness(args)
