"""
Evaluation Harness for ARTE Chatbot

This module provides the main script to run automated evaluation tests
against the /chat endpoint and record the results.

Usage:
    python -m evaluation.harness.run
    python -m evaluation.harness.run --sprint sprint_5 --no-upload
    python -m evaluation.harness.run --no-upload
"""

import argparse
import asyncio
import csv
import getpass
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from evaluation.harness.config import harness_settings
from evaluation.harness.quality import (
    INFRASTRUCTURE_FAILURE,
    QualityConfigurationError,
    build_quality_gate,
    load_policy,
    normalize_source_documents,
    quality_exit_code,
)
from evaluation.harness.s3_upload import (
    build_prefix,
    upload_results_with_metadata,
)
from evaluation.s3_client import get_git_commit, get_git_branch
from evaluation.storage import get_commit_hash, save_results

load_dotenv()

EVAL_S3_UPLOAD_ENABLED = os.getenv("EVAL_S3_UPLOAD_ENABLED", "true").lower() != "false"
EVAL_S3_PREFIX = os.getenv("EVAL_S3_PREFIX", "")

logger = logging.getLogger(__name__)

API_BASE_URL = harness_settings.api_base_url
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
DATASET_PATH = harness_settings.dataset_path
OUTPUT_DIR = harness_settings.output_dir
CHAT_API_KEY = harness_settings.chat_api_key
DEFAULT_QUALITY_POLICY = Path(__file__).parent / "policies" / "quality-v1.json"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Evaluation Harness for ARTE Chatbot")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip S3 upload, save results locally only",
    )
    parser.add_argument(
        "--sprint",
        type=str,
        default="sprint_5",
        help="Sprint identifier for the evaluation run (default: sprint_5)",
    )
    parser.add_argument(
        "--quality-policy",
        type=Path,
        default=DEFAULT_QUALITY_POLICY,
        help=f"Quality policy JSON (default: {DEFAULT_QUALITY_POLICY})",
    )
    parser.add_argument(
        "--from-report",
        type=Path,
        help="Re-evaluate raw results from a JSON report without calling the API",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Report output directory (default: {OUTPUT_DIR})",
    )
    return parser.parse_args()


def load_dataset() -> list[dict[str, Any]]:
    """Load the test dataset from JSON file."""
    if not DATASET_PATH.exists():
        raise QualityConfigurationError(f"Dataset not found at {DATASET_PATH}")

    try:
        with open(DATASET_PATH, encoding="utf-8") as dataset_file:
            dataset = json.load(dataset_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityConfigurationError(
            f"Cannot load dataset {DATASET_PATH}: {exc}"
        ) from exc
    if not isinstance(dataset, list) or not all(
        isinstance(query, dict) for query in dataset
    ):
        raise QualityConfigurationError("Dataset must contain a JSON object array")
    return dataset


def save_results_csv(
    results: list[dict[str, Any]], timestamp: str, output_dir: Path = OUTPUT_DIR
) -> Path:
    """Save results to CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"results_{timestamp}.csv"

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
                "source_documents": normalize_source_documents(source_docs),
            }
            writer.writerow(row)

    return output_path


async def run_single_query(
    client: httpx.AsyncClient, query_data: dict[str, Any]
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
        start_time = time.perf_counter()
        headers = {}
        if CHAT_API_KEY:
            headers["X-API-Key"] = CHAT_API_KEY
        response = await client.post(
            CHAT_ENDPOINT,
            json={"message": query},
            headers=headers,
            timeout=30.0,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            result["response"] = data.get("response", "")
            result["session_id"] = data.get("session_id", "")
            result["latency_ms"] = data.get("latency_ms") or elapsed_ms
            result["escalated"] = data.get("escalated", data.get("escalate", False))
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


async def run_harness(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Run the complete evaluation harness."""
    sprint = args.sprint
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
    except httpx.HTTPError as exc:
        logger.error("Cannot connect to API at %s", API_BASE_URL)
        print(f"✗ Error: Cannot connect to API at {API_BASE_URL}")
        print("  Make sure the backend is running (docker compose up)")
        raise RuntimeError(f"Cannot connect to API at {API_BASE_URL}: {exc}") from exc

    print()
    print("Running queries asynchronously...")
    print("-" * 60)

    semaphore = asyncio.Semaphore(10)

    async def run_with_semaphore(
        client: httpx.AsyncClient, query_data: dict[str, Any], index: int
    ) -> dict[str, Any]:
        async with semaphore:
            query_id = query_data.get("id", f"q{index:03d}")
            query_preview = query_data.get("query", "")[:50]
            print(f"[{index}/{len(dataset)}] {query_id}: {query_preview}...")
            result = await run_single_query(client, query_data)
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
    print(f"Completed {len(results)} queries")

    successful = sum(1 for r in results if not r["error"])
    failed = sum(1 for r in results if r["error"])
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0

    # Calculate escalation rate
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

    return results


def load_report_results(report_path: Path) -> list[dict[str, Any]]:
    """Load raw result rows from an existing report, ignoring its aggregates."""
    try:
        with report_path.open(encoding="utf-8") as report_file:
            report = json.load(report_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityConfigurationError(
            f"Cannot load raw report {report_path}: {exc}"
        ) from exc

    results = report.get("results") if isinstance(report, dict) else None
    if not isinstance(results, list) or not all(
        isinstance(result, dict) for result in results
    ):
        raise QualityConfigurationError(
            f"Raw report {report_path} must contain a results object array"
        )
    return results


def build_report(
    results: list[dict[str, Any]],
    policy: dict[str, Any],
    infrastructure_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a backward-compatible report plus metrics and gate details."""
    successful_results = [result for result in results if not result.get("error")]
    latencies = [
        float(result["latency_ms"])
        for result in successful_results
        if isinstance(result.get("latency_ms"), (int, float))
        and not isinstance(result.get("latency_ms"), bool)
        and result["latency_ms"] >= 0
    ]
    metrics, quality_gate = build_quality_gate(results, policy)
    if infrastructure_errors:
        quality_gate["infrastructure_errors"].extend(infrastructure_errors)

    return {
        "total_queries": len(results),
        "successful": len(successful_results),
        "failed": len(results) - len(successful_results),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "min_latency_ms": round(min(latencies), 2) if latencies else 0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0,
        "metrics": metrics,
        "quality_gate": quality_gate,
        "results": results,
    }


def save_report(
    results: list[dict[str, Any]],
    policy: dict[str, Any],
    args: argparse.Namespace,
    infrastructure_errors: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Persist CSV and JSON reports before upload or process exit."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    csv_path = save_results_csv(results, timestamp, output_dir)
    print(f"CSV saved to: {csv_path}")

    payload = build_report(results, policy, infrastructure_errors)
    json_path, _ = save_results(
        output_dir, "harness", payload, get_commit_hash(), timestamp
    )
    print(f"JSON saved to: {json_path}")
    return payload, json_path


def upload_report(output_dir: Path, timestamp: str) -> None:
    """Upload an already-persisted report without affecting gate status."""
    if os.getenv("GITHUB_ACTIONS"):
        trigger = "ci"
        branch = os.getenv("GITHUB_REF_NAME", "unknown")
    else:
        trigger = "manual"
        branch = getpass.getuser()

    prefix = EVAL_S3_PREFIX or build_prefix(trigger, branch, timestamp)
    print("Uploading results to S3...")
    uploaded_keys = upload_results_with_metadata(output_dir, prefix, trigger, branch)
    if uploaded_keys is None:
        print("✗ Failed to upload results to S3 (check credentials or network)")
    elif uploaded_keys:
        print(f"✓ Successfully uploaded {len(uploaded_keys)} files to S3:")
        for key in uploaded_keys:
            print(f"  - s3://{harness_settings.aws_bucket_name}/{key}")
    else:
        print("⚠ No files available for upload")


def main() -> int:
    """Run or replay the harness and return its stable gate exit code."""
    args = parse_args()
    try:
        policy = load_policy(args.quality_policy)
    except QualityConfigurationError as exc:
        logger.error("Quality policy configuration failed: %s", exc)
        print(f"Configuration error: {exc}")
        return INFRASTRUCTURE_FAILURE

    infrastructure_errors: list[dict[str, str]] = []
    try:
        results = (
            load_report_results(args.from_report)
            if args.from_report
            else asyncio.run(run_harness(args))
        )
    except (QualityConfigurationError, RuntimeError) as exc:
        logger.error("Harness infrastructure failed: %s", exc)
        results = []
        infrastructure_errors.append({"error": str(exc)})

    payload, json_path = save_report(
        results, policy, args, infrastructure_errors=infrastructure_errors
    )
    if EVAL_S3_UPLOAD_ENABLED and not args.no_upload:
        name_parts = json_path.stem.rsplit("_", 2)
        timestamp = f"{name_parts[-2]}_{name_parts[-1]}"
        upload_report(Path(args.output_dir), timestamp)

    exit_code = quality_exit_code(payload["quality_gate"])
    print(
        "Quality gate: "
        + (
            "PASS"
            if exit_code == 0
            else "QUALITY FAILURE"
            if exit_code == 1
            else "INFRASTRUCTURE FAILURE"
        )
    )
    print("=" * 60)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
