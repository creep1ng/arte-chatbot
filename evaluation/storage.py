"""
Shared storage utilities for evaluation modules.

Provides common functions for saving results locally and uploading to S3,
following the schema: evaluations/{harness-component}/{commit_hash}_{timestamp}.json
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "arte-chatbot-data")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def get_commit_hash() -> str:
    """Get current git commit hash or return 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def upload_to_s3(file_path: Path, s3_key: str) -> bool:
    """Upload file to S3 bucket. Returns True on success."""
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not access_key or not secret_key:
        print("Warning: AWS credentials not found, skipping S3 upload")
        return False

    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=AWS_REGION,
        )
        s3_client.upload_file(str(file_path), AWS_BUCKET_NAME, s3_key)
        print(f"Uploaded to s3://{AWS_BUCKET_NAME}/{s3_key}")
        return True
    except (BotoCoreError, ClientError) as e:
        print(f"Warning: Failed to upload to S3: {e}")
        return False


def save_results(
    output_dir: Path,
    harness_component: str,
    results: dict[str, Any],
    commit_hash: str | None = None,
    timestamp: str | None = None,
) -> tuple[Path, str]:
    """Save evaluation results to JSON file and return local path and S3 key.

    Schema: evaluations/{harness-component}/{commit_hash}_{timestamp}.json

    Args:
        output_dir: Local directory to save the JSON file
        harness_component: Name of the harness component (e.g., 'harness', 'escalation', 'intent')
        results: Dictionary containing evaluation results to save
        commit_hash: Git commit hash (auto-generated if not provided)
        timestamp: Timestamp string YYYYMMDD_HHMMSS (auto-generated if not provided)

    Returns:
        Tuple of (local_output_path, s3_key)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if commit_hash is None:
        commit_hash = get_commit_hash()
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    s3_key = f"evaluations/{harness_component}/{commit_hash}_{timestamp}.json"
    output_path = output_dir / f"results_{harness_component}_{commit_hash}_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "commit_hash": commit_hash,
        "s3_key": s3_key,
        **results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_path, s3_key


def upload_and_save(
    output_dir: Path,
    harness_component: str,
    results: dict[str, Any],
    commit_hash: str | None = None,
    timestamp: str | None = None,
    no_upload: bool = False,
) -> tuple[Path, str]:
    """Save results locally and optionally upload to S3.

    Args:
        output_dir: Local directory to save the JSON file
        harness_component: Name of the harness component
        results: Dictionary containing evaluation results
        commit_hash: Git commit hash (auto-generated if not provided)
        timestamp: Timestamp string (auto-generated if not provided)
        no_upload: If True, skip S3 upload

    Returns:
        Tuple of (local_output_path, s3_key)
    """
    if commit_hash is None:
        commit_hash = get_commit_hash()
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    output_path, s3_key = save_results(output_dir, harness_component, results, commit_hash, timestamp)
    print(f"Results saved to: {output_path}")

    if not no_upload:
        upload_to_s3(output_path, s3_key)

    return output_path, s3_key
