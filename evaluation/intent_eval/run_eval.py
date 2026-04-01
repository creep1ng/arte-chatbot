"""
Intent Classification Evaluation Harness for ARTE Chatbot (US-05)

Sends 15 annotated queries to the /chat endpoint and measures
intent_type classification accuracy against the expected labels.

Usage:
    python -m evaluation.intent_eval.run_eval
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
DATASET_PATH = Path(__file__).parent / "dataset.json"
OUTPUT_DIR = Path(__file__).parent / "output"

ACCURACY_THRESHOLD = 80.0


def load_dataset() -> list[dict[str, Any]]:
    """Load the intent classification test dataset."""
    if not DATASET_PATH.exists():
        print(f"Error: Dataset not found at {DATASET_PATH}")
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_single_query(
    client: httpx.Client, query_data: dict[str, Any]
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
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    try:
        start_time = datetime.utcnow()
        response = client.post(
            CHAT_ENDPOINT,
            json={"message": query},
            timeout=30.0,
        )
        end_time = datetime.utcnow()
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


def save_results(results: list[dict[str, Any]], accuracy: float, timestamp: str) -> Path:
    """Save evaluation results to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"intent_eval_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "total_queries": len(results),
                "correct": sum(1 for r in results if r["correct"]),
                "accuracy_percent": round(accuracy, 2),
                "threshold_percent": ACCURACY_THRESHOLD,
                "passed": accuracy >= ACCURACY_THRESHOLD,
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


def run_intent_eval() -> None:
    """Run the intent classification evaluation harness."""
    print("=" * 60)
    print("ARTE Chatbot - Intent Classification Evaluation (US-05)")
    print("=" * 60)
    print(f"Target endpoint: {CHAT_ENDPOINT}")
    print(f"Dataset: {DATASET_PATH}")
    print(f"Accuracy threshold: {ACCURACY_THRESHOLD}%")
    print()

    dataset = load_dataset()
    print(f"Loaded {len(dataset)} test queries")

    # Check API availability
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
    print("Running queries...")
    print("-" * 60)

    results: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for i, query_data in enumerate(dataset, 1):
            query_id = query_data["id"]
            query_preview = query_data["query"][:50]
            expected = query_data["expected_intent_type"]

            print(f"[{i}/{len(dataset)}] {query_id}: {query_preview}...")

            result = run_single_query(client, query_data)
            results.append(result)

            if result["error"]:
                print(f"    Error: {result['error']}")
            else:
                status = "PASS" if result["correct"] else "FAIL"
                print(
                    f"    {status} expected={expected} "
                    f"predicted={result['predicted_intent_type']} "
                    f"({result['latency_ms']:.0f}ms)"
                )

    print()
    print("-" * 60)

    # Calculate accuracy
    correct = sum(1 for r in results if r["correct"])
    errors = sum(1 for r in results if r["error"])
    total = len(results)
    accuracy = (correct / total * 100) if total > 0 else 0

    # Per-category breakdown
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
        cat_acc = (counts["correct"] / counts["total"] * 100) if counts["total"] > 0 else 0
        print(f"  {cat}: {counts['correct']}/{counts['total']} ({cat_acc:.0f}%)")

    print()

    if accuracy >= ACCURACY_THRESHOLD:
        print(f"PASS: Accuracy {accuracy:.1f}% >= {ACCURACY_THRESHOLD}%")
    else:
        print(f"FAIL: Accuracy {accuracy:.1f}% < {ACCURACY_THRESHOLD}%")

    # Save results
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = save_results(results, accuracy, timestamp)
    print(f"Results saved to: {output_path}")
    print("=" * 60)

    sys.exit(0 if accuracy >= ACCURACY_THRESHOLD else 1)


if __name__ == "__main__":
    run_intent_eval()
