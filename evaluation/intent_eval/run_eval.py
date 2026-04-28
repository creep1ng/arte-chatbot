"""
Intent Classification Evaluation Harness for ARTE Chatbot (US-05)

Sends annotated queries to the /chat endpoint and measures
intent_type classification accuracy against the expected labels.

Usage:
    python -m evaluation.intent_eval.run_eval
    python -m evaluation.intent_eval.run_eval --no-upload
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from evaluation.storage import get_commit_hash, save_results, upload_to_s3

from evaluation.harness.config import harness_settings

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
DATASET_PATH = Path(__file__).parent / "dataset.json"
OUTPUT_DIR = Path(__file__).parent / "output"
CHAT_API_KEY = harness_settings.chat_api_key

ACCURACY_THRESHOLD = 80.0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Intent Classification Evaluation Harness for ARTE Chatbot"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip S3 upload, save results locally only",
    )
    return parser.parse_args()


def load_dataset() -> list[dict[str, Any]]:
    """Load the intent classification test dataset."""
    if not DATASET_PATH.exists():
        print(f"Error: Dataset not found at {DATASET_PATH}")
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


async def run_single_query(
    client: httpx.AsyncClient, query_data: dict[str, Any]
) -> dict[str, Any]:
    """Execute a single query and extract intent_type classification."""
    query_id = query_data["id"]
    query = query_data["query"]
    expected_intent_type = query_data["expected_intent_type"]

    result: dict[str, Any] = {
        "query_id": query_id,
        "query": query,
        "expected_intent_type": expected_intent_type,
        "predicted_intent_type": "",
        "correct": False,
        "error": "",
        "latency_ms": 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        start_time = datetime.now(timezone.utc)
        headers = {}
        if CHAT_API_KEY:
            headers["X-API-Key"] = CHAT_API_KEY
        response = await client.post(
            CHAT_ENDPOINT,
            json={"message": query},
            headers=headers,
            timeout=30.0,
        )
        end_time = datetime.now(timezone.utc)
        result["latency_ms"] = (end_time - start_time).total_seconds() * 1000

        if response.status_code == 200:
            data = response.json()
            predicted = data.get("intent_type", "")
            result["predicted_intent_type"] = predicted
            result["correct"] = predicted == expected_intent_type
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text}"

    except httpx.ConnectError:
        result["error"] = f"Connection error: Could not connect to {CHAT_ENDPOINT}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out after 30 seconds"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


async def run_intent_eval(args: argparse.Namespace) -> None:
    """Run the intent classification evaluation harness."""
    print("=" * 60)
    print("ARTE Chatbot - Intent Classification Evaluation (US-05)")
    print("=" * 60)
    print(f"Target endpoint: {CHAT_ENDPOINT}")
    print(f"Dataset: {DATASET_PATH}")
    print(f"Accuracy threshold: {ACCURACY_THRESHOLD}%")
    print()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    dataset = load_dataset()
    print(f"Loaded {len(dataset)} test queries")

    try:
        with httpx.Client() as client:
            health_response = client.get(f"{API_BASE_URL}/health", timeout=5.0)
            if health_response.status_code == 200:
                print("API is healthy")
            else:
                print(f"API returned status {health_response.status_code}")
    except httpx.ConnectError:
        print(f"Error: Cannot connect to API at {API_BASE_URL}")
        print("Make sure the backend is running (docker compose up)")
        sys.exit(1)

    print()
    print("Running queries asynchronously...")
    print("-" * 60)

    semaphore = asyncio.Semaphore(10)

    async def run_with_semaphore(
        client: httpx.AsyncClient, query_data: dict[str, Any], index: int
    ) -> dict[str, Any]:
        async with semaphore:
            query_id = query_data["id"]
            query_preview = query_data["query"][:50]
            expected = query_data["expected_intent_type"]
            print(f"[{index}/{len(dataset)}] {query_id}: {query_preview}...")
            result = await run_single_query(client, query_data)
            if result["error"]:
                print(f"    Error: {result['error']}")
            else:
                status = "PASS" if result["correct"] else "FAIL"
                print(
                    f"    {status} expected={expected} "
                    f"predicted={result['predicted_intent_type']} "
                    f"({result['latency_ms']:.0f}ms)"
                )
            return result

    async with httpx.AsyncClient() as client:
        tasks = [
            run_with_semaphore(client, query_data, i)
            for i, query_data in enumerate(dataset, 1)
        ]
        results = await asyncio.gather(*tasks)

    results = list(results)

    print()
    print("-" * 60)

    correct = sum(1 for r in results if r["correct"])
    errors = sum(1 for r in results if r["error"])
    total = len(results)
    accuracy = (correct / total * 100) if total > 0 else 0

    categories: dict[str, dict[str, int]] = {}
    for r in results:
        if r["error"]:
            continue
        expected = r["expected_intent_type"]
        if expected not in categories:
            categories[expected] = {"correct": 0, "total": 0}
        categories[expected]["total"] += 1
        if r["correct"]:
            categories[expected]["correct"] += 1

    print(f"Results: {correct}/{total} correct")
    print(f"Errors: {errors}")
    print(f"Accuracy: {accuracy:.1f}% (threshold: {ACCURACY_THRESHOLD}%)")
    print()

    print("Per-category breakdown:")
    for cat, counts in sorted(categories.items()):
        cat_acc = (
            (counts["correct"] / counts["total"] * 100) if counts["total"] > 0 else 0
        )
        print(f"  {cat}: {counts['correct']}/{counts['total']} ({cat_acc:.0f}%)")

    print()

    passed = accuracy >= ACCURACY_THRESHOLD
    if passed:
        print(f"PASS: Accuracy {accuracy:.1f}% >= {ACCURACY_THRESHOLD}%")
    else:
        print(f"FAIL: Accuracy {accuracy:.1f}% < {ACCURACY_THRESHOLD}%")

    commit_hash = get_commit_hash()

    payload = {
        "total_queries": total,
        "correct": correct,
        "accuracy_percent": round(accuracy, 2),
        "threshold_percent": ACCURACY_THRESHOLD,
        "passed": passed,
        "results": results,
    }

    output_path, s3_key = save_results(OUTPUT_DIR, "intent", payload, commit_hash, timestamp)
    print(f"Results saved to: {output_path}")

    if not args.no_upload:
        upload_to_s3(output_path, s3_key)

    print("=" * 60)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_intent_eval(args))
