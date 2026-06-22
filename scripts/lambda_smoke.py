"""Smoke checks for Lambda-backed chatbot endpoints.

The checks validate direct API Gateway endpoints, authenticated chat, optional
DynamoDB state persistence, optional IAM-denied probes, and staging isolation
from production URLs. They intentionally do not deploy or mutate infrastructure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import boto3
from botocore.exceptions import ClientError
import httpx


DEFAULT_CHAT_MESSAGE = (
    "Validación staging: responde usando una ficha técnica de panel solar del catálogo."
)
ACCESS_DENIED_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "UnauthorizedOperation",
}


class HttpClient(Protocol):
    """Protocol for the subset of ``httpx.Client`` used by smoke checks."""

    def get(self, url: str, **kwargs: Any) -> httpx.Response: ...

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


@dataclass(frozen=True)
class SmokeConfig:
    """Configuration for Lambda smoke validation."""

    base_url: str
    chat_api_key: str
    chat_message: str = DEFAULT_CHAT_MESSAGE
    environment: str = "staging"
    forbidden_urls: tuple[str, ...] = field(default_factory=tuple)
    require_source_docs: bool = False
    state_table_name: str = ""
    state_key_prefix: str = ""
    aws_region: str = "us-east-2"
    iam_denied_dynamodb_table_name: str = ""
    iam_denied_s3_uri: str = ""


def run_smoke(
    config: SmokeConfig,
    *,
    http_client: HttpClient | None = None,
    dynamodb_resource: Any | None = None,
    dynamodb_client: Any | None = None,
    s3_client: Any | None = None,
) -> list[str]:
    """Run smoke checks and return human-readable evidence lines."""
    _validate_endpoint_isolation(config)
    evidence: list[str] = []

    owns_http_client = http_client is None
    client = http_client or httpx.Client(timeout=35.0)
    try:
        health_body = check_health(config.base_url, client)
        evidence.append(f"health ok: {health_body.get('status', 'unknown')}")

        chat_body = check_chat(config, client)
        session_id = str(chat_body.get("session_id") or "")
        evidence.append(f"chat ok: session_id={session_id}")

        if config.require_source_docs:
            source_count = int(chat_body.get("num_sources") or 0)
            if source_count <= 0:
                raise RuntimeError("chat response did not include source documents")
            evidence.append(f"file inputs ok: source_documents={source_count}")

        if config.state_table_name:
            table = dynamodb_resource or boto3.resource(
                "dynamodb", region_name=config.aws_region
            )
            verify_dynamodb_persistence(
                table,
                table_name=config.state_table_name,
                session_id=session_id,
                state_key_prefix=config.state_key_prefix,
            )
            evidence.append("dynamodb persistence ok")

        if config.iam_denied_dynamodb_table_name:
            ddb_client = dynamodb_client or boto3.client(
                "dynamodb", region_name=config.aws_region
            )
            expect_dynamodb_access_denied(
                ddb_client,
                config.iam_denied_dynamodb_table_name,
            )
            evidence.append("iam denied ok: dynamodb")

        if config.iam_denied_s3_uri:
            client_s3 = s3_client or boto3.client("s3", region_name=config.aws_region)
            expect_s3_access_denied(client_s3, config.iam_denied_s3_uri)
            evidence.append("iam denied ok: s3")
    finally:
        if owns_http_client:
            client.close()

    return evidence


def check_health(base_url: str, client: HttpClient) -> dict[str, Any]:
    """Assert that ``GET /health`` returns healthy JSON."""
    response = client.get(_url(base_url, "/health"))
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "healthy":
        raise RuntimeError(f"unexpected health response: {body}")
    return body


def check_chat(config: SmokeConfig, client: HttpClient) -> dict[str, Any]:
    """Assert that authenticated ``POST /chat`` succeeds."""
    if not config.chat_api_key:
        raise RuntimeError("chat API key is required for Lambda smoke checks")
    response = client.post(
        _url(config.base_url, "/chat"),
        json={"message": config.chat_message},
        headers={"X-API-Key": config.chat_api_key},
        timeout=60.0,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("session_id"):
        raise RuntimeError(f"chat response did not include session_id: {body}")
    if not body.get("response"):
        raise RuntimeError(f"chat response did not include response text: {body}")
    return body


def verify_dynamodb_persistence(
    dynamodb_resource: Any,
    *,
    table_name: str,
    session_id: str,
    state_key_prefix: str,
) -> None:
    """Verify that a chat request produced session rows in DynamoDB."""
    if not session_id:
        raise RuntimeError("session_id is required for DynamoDB persistence check")
    pk = _session_partition_key(session_id, state_key_prefix)
    table = dynamodb_resource.Table(table_name)
    response = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": pk},
    )
    items = response.get("Items", [])
    if not items:
        raise RuntimeError(f"no DynamoDB state rows found for partition key {pk}")


def expect_dynamodb_access_denied(dynamodb_client: Any, table_name: str) -> None:
    """Assert that a DynamoDB table probe is denied by IAM."""
    try:
        dynamodb_client.describe_table(TableName=table_name)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ACCESS_DENIED_CODES:
            return
        raise RuntimeError(
            f"DynamoDB denied probe returned {error_code}, expected access denied"
        ) from exc
    raise RuntimeError("DynamoDB denied probe unexpectedly succeeded")


def expect_s3_access_denied(s3_client: Any, s3_uri: str) -> None:
    """Assert that an S3 object probe is denied by IAM."""
    bucket, key = _parse_s3_uri(s3_uri)
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ACCESS_DENIED_CODES:
            return
        raise RuntimeError(
            f"S3 denied probe returned {error_code}, expected access denied"
        ) from exc
    raise RuntimeError("S3 denied probe unexpectedly succeeded")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--chat-api-key", default="")
    parser.add_argument("--chat-message", default=DEFAULT_CHAT_MESSAGE)
    parser.add_argument(
        "--environment", choices=("staging", "production"), default="staging"
    )
    parser.add_argument("--forbidden-url", action="append", default=[])
    parser.add_argument("--require-source-docs", action="store_true")
    parser.add_argument("--state-table-name", default="")
    parser.add_argument("--state-key-prefix", default="")
    parser.add_argument("--aws-region", default="us-east-2")
    parser.add_argument("--expect-iam-denied-dynamodb-table", default="")
    parser.add_argument("--expect-iam-denied-s3-uri", default="")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    config = SmokeConfig(
        base_url=args.base_url,
        chat_api_key=args.chat_api_key,
        chat_message=args.chat_message,
        environment=args.environment,
        forbidden_urls=tuple(args.forbidden_url),
        require_source_docs=args.require_source_docs,
        state_table_name=args.state_table_name,
        state_key_prefix=args.state_key_prefix,
        aws_region=args.aws_region,
        iam_denied_dynamodb_table_name=args.expect_iam_denied_dynamodb_table,
        iam_denied_s3_uri=args.expect_iam_denied_s3_uri,
    )
    for line in run_smoke(config):
        print(line)


def _validate_endpoint_isolation(config: SmokeConfig) -> None:
    base = _normalize_url(config.base_url)
    if config.environment == "staging":
        host = urlparse(base).netloc.lower()
        if host.startswith(("api.", "chatbot.")) and "staging" not in host:
            raise RuntimeError(f"staging smoke must not target production host: {base}")

    for forbidden_url in config.forbidden_urls:
        if not forbidden_url:
            continue
        if _normalize_url(forbidden_url) == base:
            raise RuntimeError(f"smoke base URL is forbidden: {base}")


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"invalid URL: {value}")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")


def _session_partition_key(session_id: str, state_key_prefix: str) -> str:
    key = f"SESSION#{session_id}"
    prefix = state_key_prefix.strip("#")
    return f"{prefix}#{key}" if prefix else key


def _parse_s3_uri(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise RuntimeError(f"invalid S3 URI: {value}")
    return parsed.netloc, parsed.path.lstrip("/")


if __name__ == "__main__":
    main()
