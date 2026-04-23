"""Upload mock data to S3 for testing.

This script generates mock evaluation data and uploads it to S3
for testing the quality report notebook.
"""

import argparse
from pathlib import Path

from evaluation.mock_data_generator import save_mock_data
from evaluation.s3_client import S3ReportsClient


def upload_mock_data_to_s3(sprints: list[str] | None = None) -> None:
    """Generate and upload mock data to S3.

    Args:
        sprints: List of sprint identifiers to upload.
    """
    if sprints is None:
        sprints = ["sprint_2", "sprint_5"]

    try:
        s3_client = S3ReportsClient()
    except ValueError as e:
        print(f"✗ {e}")
        print("  Asegúrate de tener las variables de entorno AWS configuradas:")
        print("  - AWS_ACCESS_KEY_ID")
        print("  - AWS_SECRET_ACCESS_KEY")
        print("  - AWS_BUCKET_NAME")
        return

    print("=" * 60)
    print("Upload Mock Data to S3")
    print("=" * 60)
    print(f"Bucket: {s3_client.BUCKET_NAME}")
    print(f"Sprints: {', '.join(sprints)}")
    print()

    for sprint in sprints:
        print(f"Processing {sprint}...")

        # Generate mock data
        from evaluation.mock_data_generator import generate_quality_report_data

        data = generate_quality_report_data(sprint)

        # Upload harness results
        if data.get("harness"):
            harness_key = s3_client.build_s3_key(sprint, "harness")
            if s3_client.upload_json(data["harness"], harness_key):
                print(f"  ✓ Harness: s3://{s3_client.BUCKET_NAME}/{harness_key}")
            else:
                print(f"  ✗ Harness: Failed to upload")

        # Upload hallucination results
        if data.get("hallucination"):
            hal_key = s3_client.build_s3_key(sprint, "hallucination")
            if s3_client.upload_json(data["hallucination"], hal_key):
                print(f"  ✓ Hallucination: s3://{s3_client.BUCKET_NAME}/{hal_key}")
            else:
                print(f"  ✗ Hallucination: Failed to upload")

        # Upload human eval results
        if data.get("human_eval"):
            human_key = s3_client.build_s3_key(sprint, "human_eval")
            if s3_client.upload_json(data["human_eval"], human_key):
                print(f"  ✓ Human Eval: s3://{s3_client.BUCKET_NAME}/{human_key}")
            else:
                print(f"  ✗ Human Eval: Failed to upload")

        print()

    print("=" * 60)
    print("Upload complete!")
    print()
    print("Estructura en S3:")
    print("  arte-chatbot-data/")
    print("  └── evaluation/")
    print("      └── reports/")
    print("          ├── sprint_2/")
    print("          │   ├── harness/report_TIMESTAMP.json")
    print("          │   ├── hallucination/report_TIMESTAMP.json")
    print("          │   └── human_eval/report_TIMESTAMP.json")
    print("          └── sprint_5/")
    print("              ├── harness/report_TIMESTAMP.json")
    print("              ├── hallucination/report_TIMESTAMP.json")
    print("              └── human_eval/report_TIMESTAMP.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload mock evaluation data to S3")
    parser.add_argument(
        "--sprints",
        nargs="+",
        default=["sprint_2", "sprint_5"],
        help="Sprint identifiers to upload",
    )

    args = parser.parse_args()
    upload_mock_data_to_s3(args.sprints)
