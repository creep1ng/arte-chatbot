"""
S3 upload module for evaluation harness results.

Provides functionality to upload evaluation results (JSON/CSV) to S3
with metadata for trazability.
"""

import getpass
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from boto3.exceptions import Boto3Error

logger = logging.getLogger(__name__)

AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "arte-chatbot-data")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def get_harness_version() -> str:
    """Compute hash of evaluation/harness/ directory content."""
    harness_dir = Path(__file__).parent
    hash_md5 = hashlib.md5()
    for file_path in sorted(harness_dir.glob("*.py")):
        if file_path.name == "__pycache__":
            continue
        with open(file_path, "rb") as f:
            hash_md5.update(f.read())
    return hash_md5.hexdigest()[:12]


def generate_metadata(trigger: str, runner: str) -> dict[str, Any]:
    """Generate metadata.json content for an evaluation run.

    Args:
        trigger: Execution trigger ("ci" or "manual").
        runner: Runner identifier (GitHub Actions hostname or local username).

    Returns:
        Dictionary with metadata fields.
    """
    import subprocess

    git_commit = "unknown"
    git_branch = "unknown"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_commit = result.stdout.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_branch = result.stdout.strip()
    except Exception:
        pass

    return {
        "git_commit": git_commit,
        "git_branch": git_branch,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trigger": trigger,
        "runner": runner,
        "harness_version": get_harness_version(),
    }


def upload_results(output_dir: Path, prefix: str) -> list[str]:
    """Upload all JSON and CSV files from output_dir to S3.

    Args:
        output_dir: Directory containing results to upload.
        prefix: S3 key prefix (e.g., "evaluation/ci/branch/run_id/").

    Returns:
        List of S3 keys that were uploaded. Empty list on failure.
    """
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not access_key or not secret_key:
        logger.warning("AWS credentials not found, skipping S3 upload")
        return None

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=AWS_REGION,
    )
    uploaded: list[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_files = list(output_dir.glob("*.json"))
    csv_files = list(output_dir.glob("*.csv"))

    for file_path in json_files + csv_files:
        s3_key = f"{prefix.rstrip('/')}/{file_path.name}"
        try:
            s3_client.upload_file(str(file_path), AWS_BUCKET_NAME, s3_key)
            logger.info("Uploaded %s to s3://%s/%s", file_path.name, AWS_BUCKET_NAME, s3_key)
            uploaded.append(s3_key)
        except Boto3Error as e:
            logger.error("Failed to upload %s: %s", file_path.name, e)

    return uploaded


def upload_results_with_metadata(
    output_dir: Path,
    prefix: str,
    trigger: str,
    runner: str,
) -> list[str]:
    """Upload results and generate/upload metadata.json.

    Args:
        output_dir: Directory containing results to upload.
        prefix: S3 key prefix.
        trigger: Execution trigger ("ci" or "manual").
        runner: Runner identifier.

    Returns:
        List of S3 keys uploaded (including metadata.json), or None on failure.
    """
    result = upload_results(output_dir, prefix)
    if result is None:
        return None
    uploaded = result

    metadata = generate_metadata(trigger, runner)
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if access_key and secret_key:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=AWS_REGION,
        )
        s3_key = f"{prefix.rstrip('/')}/metadata.json"
        try:
            s3_client.upload_file(str(metadata_path), AWS_BUCKET_NAME, s3_key)
            logger.info("Uploaded metadata.json to s3://%s/%s", AWS_BUCKET_NAME, s3_key)
            uploaded.append(s3_key)
        except Boto3Error as e:
            logger.error("Failed to upload metadata.json: %s", e)

    return uploaded


def build_prefix(trigger: str, runner: str, timestamp: str | None = None) -> str:
    """Build S3 prefix for evaluation results.

    Args:
        trigger: "ci" or "manual".
        runner: Runner identifier (branch/run_id for CI, username for manual).
        timestamp: Optional timestamp (auto-generated if not provided).

    Returns:
        S3 prefix string (e.g., "evaluation/ci/main/1234567890/").
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if trigger == "ci":
        return f"evaluation/ci/{runner}/{timestamp}/"
    else:
        return f"evaluation/manual/{runner}/{timestamp}/"