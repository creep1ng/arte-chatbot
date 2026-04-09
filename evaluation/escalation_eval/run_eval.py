"""
Escalation Evaluation Harness for ARTE Chatbot (US-10)

Evaluates the escalation decision tree against annotated test cases,
measuring false positive and false negative rates.

Usage:
    python -m evaluation.escalation_eval.run_eval
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

FALSE_POSITIVE_THRESHOLD = 0.15
FALSE_NEGATIVE_THRESHOLD = 0.10


def load_dataset() -> list[dict[str, Any]]:
    """Load the escalation test dataset."""
    if not DATASET_PATH.exists():
        print(f"Error: Dataset not found at {DATASET_PATH}")
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_single_query(
    client: httpx.Client, query_data: dict[str, Any]
) -> dict[str, Any]:
    """Execute a single query and extract escalation decision."""
    query_id = query_data["id"]
    query = query_data["query"]
    expected_should_escalate = query_data["should_escalate"]

    result: dict[str, Any] = {
        "query_id": query_id,
        "query": query,
        "expected_should_escalate": expected_should_escalate,
        "predicted_escalate": False,
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
            result["predicted_escalate"] = data.get("escalate", False)
            result["predicted_intent_type"] = data.get("intent_type", "")
            result["correct"] = result["predicted_escalate"] == expected_should_escalate
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text}"

    except httpx.ConnectError:
        result["error"] = f"Connection error: Could not connect to {CHAT_ENDPOINT}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out after 30 seconds"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    """Calculate false positive and false negative rates.
    
    False Positive: Predicted escalate=true, but expected=false
    False Negative: Predicted escalate=false, but expected=true
    """
    total = len(results)
    false_positives = 0
    false_negatives = 0
    true_positives = 0
    true_negatives = 0
    
    for r in results:
        if r["error"]:
            continue
            
        predicted = r["predicted_escalate"]
        expected = r["expected_should_escalate"]
        
        if predicted and expected:
            true_positives += 1
        elif not predicted and not expected:
            true_negatives += 1
        elif predicted and not expected:
            false_positives += 1
        else:
            false_negatives += 1
    
    fp_rate = false_positives / total if total > 0 else 0
    fn_rate = false_negatives / total if total > 0 else 0
    
    return {
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_positives": true_positives,
        "true_negatives": true_negatives,
        "total": total,
    }


def save_results(
    results: list[dict[str, Any]], 
    metrics: dict[str, float], 
    timestamp: str
) -> Path:
    """Save evaluation results to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"escalation_eval_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "total_queries": metrics["total"],
                "false_positives": metrics["false_positives"],
                "false_negatives": metrics["false_negatives"],
                "true_positives": metrics["true_positives"],
                "true_negatives": metrics["true_negatives"],
                "false_positive_rate": round(metrics["false_positive_rate"], 4),
                "false_negative_rate": round(metrics["false_negative_rate"], 4),
                "fp_threshold": FALSE_POSITIVE_THRESHOLD,
                "fn_threshold": FALSE_NEGATIVE_THRESHOLD,
                "passed": (
                    metrics["false_positive_rate"] <= FALSE_POSITIVE_THRESHOLD
                    and metrics["false_negative_rate"] <= FALSE_NEGATIVE_THRESHOLD
                ),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


def run_escalation_eval() -> None:
    """Run the escalation evaluation harness."""
    print("=" * 60)
    print("ARTE Chatbot - Escalation Evaluation (US-10)")
    print("=" * 60)
    print(f"Target endpoint: {CHAT_ENDPOINT}")
    print(f"Dataset: {DATASET_PATH}")
    print(f"False positive threshold: {FALSE_POSITIVE_THRESHOLD * 100}%")
    print(f"False negative threshold: {FALSE_NEGATIVE_THRESHOLD * 100}%")
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
            expected = query_data["should_escalate"]

            print(f"[{i}/{len(dataset)}] {query_id}: {query_preview}...")

            result = run_single_query(client, query_data)
            results.append(result)

            if result["error"]:
                print(f"    Error: {result['error']}")
            else:
                status = "PASS" if result["correct"] else "FAIL"
                print(
                    f"    {status} expected_escalate={expected} "
                    f"predicted={result['predicted_escalate']} "
                    f"intent={result['predicted_intent_type']} "
                    f"({result['latency_ms']:.0f}ms)"
                )

    print()
    print("-" * 60)

    # Calculate metrics
    metrics = calculate_metrics(results)
    errors = sum(1 for r in results if r["error"])

    print(f"Results: {len(results) - errors}/{metrics['total']} processed")
    print(f"Errors: {errors}")
    print()
    print(f"True Positives: {metrics['true_positives']}")
    print(f"True Negatives: {metrics['true_negatives']}")
    print(f"False Positives: {metrics['false_positives']}")
    print(f"False Negatives: {metrics['false_negatives']}")
    print()
    print(f"False Positive Rate: {metrics['false_positive_rate']*100:.1f}% (threshold: {FALSE_POSITIVE_THRESHOLD*100}%)")
    print(f"False Negative Rate: {metrics['false_negative_rate']*100:.1f}% (threshold: {FALSE_NEGATIVE_THRESHOLD*100}%)")
    print()

    passed = (
        metrics["false_positive_rate"] <= FALSE_POSITIVE_THRESHOLD
        and metrics["false_negative_rate"] <= FALSE_NEGATIVE_THRESHOLD
    )

    if passed:
        print("PASS: Both thresholds met")
    else:
        failed_conditions = []
        if metrics["false_positive_rate"] > FALSE_POSITIVE_THRESHOLD:
            failed_conditions.append(f"FP rate ({metrics['false_positive_rate']*100:.1f}% > {FALSE_POSITIVE_THRESHOLD*100}%)")
        if metrics["false_negative_rate"] > FALSE_NEGATIVE_THRESHOLD:
            failed_conditions.append(f"FN rate ({metrics['false_negative_rate']*100:.1f}% > {FALSE_NEGATIVE_THRESHOLD*100}%)")
        print(f"FAIL: {', '.join(failed_conditions)}")

    # Save results
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = save_results(results, metrics, timestamp)
    print(f"Results saved to: {output_path}")
    print("=" * 60)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    run_escalation_eval()