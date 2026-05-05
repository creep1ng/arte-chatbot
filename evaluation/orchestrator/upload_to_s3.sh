#!/bin/bash
set -e

HASH=$(git rev-parse HEAD 2>/dev/null || echo "${GITHUB_SHA:-unknown}")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
COMMIT_SHORT="${HASH:0:7}"

OUTPUT_DIR="${OUTPUT_DIR:-evaluation/orchestrator/output}"
REPORT_FILE="${OUTPUT_DIR}/report_${COMMIT_SHORT}_${TIMESTAMP}.json"

if [ ! -f "$REPORT_FILE" ]; then
    echo "Error: Report file not found: $REPORT_FILE"
    echo "Run the orchestrator first: python -m evaluation.orchestrator.run"
    exit 1
fi

S3_KEY="evaluation/orchestrator/${COMMIT_SHORT}_${TIMESTAMP}.json"

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Warning: AWS credentials not found, skipping S3 upload"
    echo "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
    exit 0
fi

aws s3 cp "$REPORT_FILE" "s3://arte-chatbot-data/${S3_KEY}" \
    --content-type "application/json" \
    && echo "Uploaded to s3://arte-chatbot-data/${S3_KEY}" \
    || echo "Failed to upload to S3"