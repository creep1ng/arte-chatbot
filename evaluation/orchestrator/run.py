"""Evaluation Orchestrator for ARTE Chatbot.

This module provides a centralized evaluation system that:
1. Loads a unified dataset
2. Executes queries against /chat in a single pass
3. Runs multiple analyzers on the results
4. Generates consolidated reports
5. Uploads artifacts to S3

Usage:
    python -m evaluation.orchestrator.run
    python -m evaluation.orchestrator.run --no-upload
    python -m evaluation.orchestrator.run --from-raw path/to/raw_results.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from evaluation.orchestrator.analyzers import (
    EscalationAnalyzer,
    GeneralAnalyzer,
    HallucinationAnalyzer,
    IntentAnalyzer,
)
from evaluation.orchestrator.executor import check_api_health, execute_batch
from evaluation.orchestrator.settings import orchestrator_settings
from evaluation.s3_client import get_git_commit, get_git_branch
from evaluation.storage import get_commit_hash

load_dotenv()

logger = logging.getLogger(__name__)

OUTPUT_DIR = orchestrator_settings.output_dir


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluation Orchestrator for ARTE Chatbot"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip S3 upload, save results locally only",
    )
    parser.add_argument(
        "--from-raw",
        type=Path,
        default=None,
        help="Path to raw_results.json to use instead of running queries",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output directory",
    )
    return parser.parse_args()


def load_dataset() -> list[dict[str, object]]:
    """Load the unified test dataset."""
    dataset_path = orchestrator_settings.dataset_path
    if not dataset_path.exists():
        logger.error("Dataset not found at %s", dataset_path)
        sys.exit(1)

    with open(dataset_path, encoding="utf-8") as f:
        return json.load(f)


def save_raw_results(
    results: list[dict[str, object]],
    output_dir: Path,
    commit_hash: str,
    timestamp: str,
) -> Path:
    """Save raw results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"raw_results_{commit_hash}_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "commit_hash": commit_hash,
        "total_queries": len(results),
        "results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_path


def run_analyzers(raw_results: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Run all analyzers on raw results.

    Args:
        raw_results: List of raw result dictionaries.

    Returns:
        Dictionary mapping analyzer names to their analysis results.
    """
    analyzers = [
        GeneralAnalyzer(),
        IntentAnalyzer(),
        EscalationAnalyzer(),
        HallucinationAnalyzer(),
    ]

    analyses = {}
    for analyzer in analyzers:
        logger.info("Running %s analyzer", analyzer.name)
        analyses[analyzer.name] = analyzer.analyze(raw_results)

    return analyses


def save_consolidated_report(
    raw_results: list[dict[str, object]],
    analyses: dict[str, dict[str, object]],
    output_dir: Path,
    commit_hash: str,
    timestamp: str,
) -> tuple[Path, str]:
    """Save consolidated report to JSON and CSV.

    Returns:
        Tuple of (json_path, s3_key).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": timestamp,
        "commit_hash": commit_hash,
        "total_queries": len(raw_results),
        "analyses": analyses,
    }

    s3_key = f"evaluation/orchestrator/{commit_hash}_{timestamp}.json"
    json_path = output_dir / f"report_{commit_hash}_{timestamp}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return json_path, s3_key


def print_summary(
    analyses: dict[str, dict[str, object]],
    raw_results: list[dict[str, object]],
) -> None:
    """Print a summary of the evaluation results."""
    print()
    print("=" * 60)
    print("EVALUATION ORCHESTRATOR - SUMMARY")
    print("=" * 60)
    print()

    analyzers = [
        GeneralAnalyzer(),
        IntentAnalyzer(),
        EscalationAnalyzer(),
        HallucinationAnalyzer(),
    ]

    for analyzer in analyzers:
        if analyzer.name in analyses:
            print(analyzer.summarize(analyses[analyzer.name]))
            print()

    print("=" * 60)


async def run_orchestrator(args: argparse.Namespace) -> None:
    """Run the complete evaluation orchestrator."""
    print("=" * 60)
    print("ARTE Chatbot Evaluation Orchestrator")
    print("=" * 60)
    print()

    git_commit = get_git_commit()
    git_branch = get_git_branch()
    print(f"Git commit: {git_commit}")
    print(f"Git branch: {git_branch}")
    print()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or OUTPUT_DIR

    raw_results: list[dict[str, object]]

    if args.from_raw:
        print(f"Loading raw results from: {args.from_raw}")
        with open(args.from_raw, encoding="utf-8") as f:
            raw_data = json.load(f)
            raw_results = raw_data.get("results", [])
            if not raw_results:
                logger.error("No results found in %s", args.from_raw)
                sys.exit(1)
    else:
        print("Running API health check...")
        is_healthy = await check_api_health()
        if not is_healthy:
            logger.error("API health check failed. Make sure the backend is running.")
            print("✗ Error: API health check failed")
            print("  Make sure the backend is running (docker compose up)")
            sys.exit(1)
        print("✓ API is healthy")
        print()

        dataset = load_dataset()
        print(f"Loaded {len(dataset)} queries from dataset")
        print()
        print("Executing queries...")
        print("-" * 60)

        def progress_callback(index: int, total: int, result: dict[str, object]) -> None:
            query_id = result.get("query_id", f"q{index}")
            if result.get("error"):
                print(f"[{index}/{total}] {query_id}: ✗ {result['error'][:50]}")
            else:
                print(f"[{index}/{total}] {query_id}: ✓ {result.get('latency_ms', 0):.0f}ms")

        raw_results = await execute_batch(dataset, progress_callback)

        print()
        print("Saving raw results...")
        raw_path = save_raw_results(raw_results, output_dir, git_commit[:7], timestamp)
        print(f"Raw results saved to: {raw_path}")

    print()
    print("Running analyzers...")
    print("-" * 60)
    analyses = run_analyzers(raw_results)
    print()

    print("Generating consolidated report...")
    json_path, s3_key = save_consolidated_report(
        raw_results, analyses, output_dir, git_commit[:7], timestamp
    )
    print(f"Report saved to: {json_path}")

    if not args.no_upload:
        print()
        print("Uploading to S3...")
        from evaluation.storage import upload_to_s3
        if upload_to_s3(json_path, s3_key):
            print(f"✓ Uploaded to s3://arte-chatbot-data/{s3_key}")
        else:
            print("⚠ S3 upload skipped (credentials not available)")

    print_summary(analyses, raw_results)


def main() -> None:
    """Entry point for the orchestrator."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    args = parse_args()
    asyncio.run(run_orchestrator(args))


if __name__ == "__main__":
    main()