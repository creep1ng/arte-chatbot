"""S3 client module for evaluation reports.

Handles uploading and downloading evaluation results from S3.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError


class S3ReportsClient:
    """Client for managing evaluation reports in S3."""

    BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "arte-chatbot-data")
    REPORTS_PREFIX = "evaluation/reports"

    def __init__(self) -> None:
        """Initialize S3 client with credentials from environment variables."""
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        region = os.getenv("AWS_REGION", "us-east-1")

        if not access_key or not secret_key:
            raise ValueError(
                "AWS credentials not found. "
                "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )

        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def upload_json(
        self, data: dict[str, Any], s3_key: str, content_type: str = "application/json"
    ) -> bool:
        """Upload a JSON object to S3.

        Args:
            data: Dictionary to upload as JSON.
            s3_key: S3 key (path) where to store the file.
            content_type: Content type for the object.

        Returns:
            True if upload successful, False otherwise.
        """
        try:
            self._s3.put_object(
                Bucket=self.BUCKET_NAME,
                Key=s3_key,
                Body=json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
                ContentType=content_type,
            )
            return True
        except ClientError as e:
            print(f"✗ Failed to upload to S3: {e}")
            return False

    def download_json(self, s3_key: str) -> dict[str, Any] | None:
        """Download a JSON object from S3.

        Args:
            s3_key: S3 key (path) of the file to download.

        Returns:
            Dictionary with the parsed JSON content, or None if not found.
        """
        try:
            response = self._s3.get_object(Bucket=self.BUCKET_NAME, Key=s3_key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            print(f"✗ Failed to download from S3: {e}")
            return None

    def list_reports(
        self, sprint: str | None = None, report_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List available evaluation reports in S3.

        Args:
            sprint: Optional sprint identifier (e.g., "sprint_2", "sprint_5").
            report_type: Optional report type (e.g., "harness", "hallucination", "human_eval").

        Returns:
            List of report metadata dictionaries.
        """
        prefix_parts = [self.REPORTS_PREFIX]
        if sprint:
            prefix_parts.append(sprint)
        if report_type:
            prefix_parts.append(report_type)

        prefix = "/".join(prefix_parts) + "/"

        try:
            response = self._s3.list_objects_v2(
                Bucket=self.BUCKET_NAME,
                Prefix=prefix,
            )

            reports = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue

                filename = key.split("/")[-1]
                if filename.endswith(".json"):
                    reports.append(
                        {
                            "key": key,
                            "filename": filename,
                            "size_bytes": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        }
                    )

            return sorted(reports, key=lambda x: x["last_modified"], reverse=True)

        except ClientError as e:
            print(f"✗ Failed to list reports from S3: {e}")
            return []

    def download_latest_report(
        self, sprint: str | None = None, report_type: str | None = None
    ) -> dict[str, Any] | None:
        """Download the most recent report of a given type.

        Args:
            sprint: Optional sprint identifier.
            report_type: Report type (e.g., "harness", "hallucination", "human_eval").

        Returns:
            Parsed JSON content of the latest report, or None if not found.
        """
        reports = self.list_reports(sprint=sprint, report_type=report_type)
        if not reports:
            return None

        latest = reports[0]
        return self.download_json(latest["key"])

    def build_s3_key(
        self, sprint: str, report_type: str, timestamp: str | None = None
    ) -> str:
        """Build an S3 key for a report.

        Args:
            sprint: Sprint identifier (e.g., "sprint_2", "sprint_5").
            report_type: Type of report (e.g., "harness", "hallucination", "human_eval").
            timestamp: Optional timestamp string. If not provided, uses current UTC time.

        Returns:
            S3 key path for the report.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        return f"{self.REPORTS_PREFIX}/{sprint}/{report_type}/report_{timestamp}.json"

    def list_sprints(self) -> list[str]:
        """List all available sprints in S3.

        Returns:
            List of sprint identifiers (e.g., ["sprint_2", "sprint_5", "release_1.0"]).
        """
        try:
            response = self._s3.list_objects_v2(
                Bucket=self.BUCKET_NAME,
                Prefix=self.REPORTS_PREFIX + "/",
            )
            sprints: set[str] = set()
            for obj in response.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")
                if len(parts) >= 2:
                    sprints.add(parts[1])
            return sorted(list(sprints))
        except ClientError:
            return []


def get_git_commit() -> str:
    """Get the current git commit hash.

    Returns:
        The short commit hash (7 characters) or "unknown" if not available.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def get_git_branch() -> str:
    """Get the current git branch name.

    Returns:
        The branch name or "unknown" if not available.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
