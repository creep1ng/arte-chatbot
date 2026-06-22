"""Rollback helpers for Lambda backend delivery.

Rollback is Lambda-version only after the destructive production cutover. The
EC2 Compose/Cloudflare Tunnel fallback path has been removed from production.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from typing import Any

import boto3


@dataclass(frozen=True)
class AliasTarget:
    """Lambda alias target metadata."""

    function_name: str
    alias_name: str
    function_version: str
    routing_config: dict[str, Any]


def discover_alias_target(
    lambda_client: Any,
    *,
    function_name: str,
    alias_name: str,
) -> AliasTarget:
    """Return the current target for a Lambda alias."""
    response = lambda_client.get_alias(FunctionName=function_name, Name=alias_name)
    return AliasTarget(
        function_name=function_name,
        alias_name=alias_name,
        function_version=str(response["FunctionVersion"]),
        routing_config=dict(response.get("RoutingConfig") or {}),
    )


def rollback_lambda_alias(
    lambda_client: Any,
    *,
    function_name: str,
    alias_name: str,
    target_version: str,
    dry_run: bool = False,
) -> AliasTarget:
    """Move ``alias_name`` back to ``target_version`` unless ``dry_run`` is set."""
    _validate_lambda_version(target_version)
    before = discover_alias_target(
        lambda_client,
        function_name=function_name,
        alias_name=alias_name,
    )
    if dry_run:
        return before

    lambda_client.update_alias(
        FunctionName=function_name,
        Name=alias_name,
        FunctionVersion=target_version,
        Description=f"Rollback to version {target_version}",
    )
    return discover_alias_target(
        lambda_client,
        function_name=function_name,
        alias_name=alias_name,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)

    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover-alias")
    discover.add_argument("--aws-region", default="us-east-2")
    discover.add_argument("--function-name", required=True)
    discover.add_argument("--alias-name", required=True)

    rollback = subparsers.add_parser("rollback-alias")
    rollback.add_argument("--aws-region", default="us-east-2")
    rollback.add_argument("--function-name", required=True)
    rollback.add_argument("--alias-name", required=True)
    rollback.add_argument("--target-version", required=True)
    rollback.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    lambda_client = boto3.client("lambda", region_name=args.aws_region)
    if args.command == "discover-alias":
        target = discover_alias_target(
            lambda_client,
            function_name=args.function_name,
            alias_name=args.alias_name,
        )
    else:
        target = rollback_lambda_alias(
            lambda_client,
            function_name=args.function_name,
            alias_name=args.alias_name,
            target_version=args.target_version,
            dry_run=args.dry_run,
        )

    print(json.dumps(target.__dict__, indent=2, sort_keys=True))


def _validate_lambda_version(value: str) -> None:
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("target Lambda version must be a positive published version")


if __name__ == "__main__":
    main()
