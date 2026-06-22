"""Runtime secret reference resolution for Lambda-safe configuration.

Lambda receives references such as ``OPENAI_API_KEY_SECRET_REF`` from
Terraform. This module resolves those references through the AWS default
credential chain, so plaintext secrets do not need to be present in Lambda
environment variables or packaged files.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class SecretResolutionError(RuntimeError):
    """Raised when a configured AWS secret reference cannot be resolved."""


def configured_secret_value(
    plaintext_value: Optional[str],
    secret_ref: Optional[str],
    *,
    region_name: Optional[str] = None,
) -> Optional[str]:
    """Return plaintext config or resolve a configured AWS secret reference.

    Args:
        plaintext_value: Directly injected secret value, if present.
        secret_ref: SSM Parameter Store or Secrets Manager name/ARN.
        region_name: Optional AWS region for the boto3 client.

    Returns:
        The usable secret value, or ``None`` when neither source is configured.
    """
    if plaintext_value:
        return plaintext_value
    if not isinstance(secret_ref, str) or not secret_ref.strip():
        return None
    return _resolve_runtime_secret_cached(secret_ref.strip(), region_name)


def clear_runtime_secret_cache() -> None:
    """Clear resolved secret cache for tests and explicit config reloads."""
    _resolve_runtime_secret_cached.cache_clear()


@lru_cache(maxsize=32)
def _resolve_runtime_secret_cached(
    secret_ref: str,
    region_name: Optional[str],
) -> str:
    return resolve_runtime_secret(secret_ref, region_name=region_name)


def resolve_runtime_secret(
    secret_ref: str, *, region_name: Optional[str] = None
) -> str:
    """Resolve an SSM Parameter Store or Secrets Manager reference.

    Args:
        secret_ref: Parameter/secret name or ARN.
        region_name: Optional AWS region for the boto3 client.

    Returns:
        The plaintext secret value returned by AWS.

    Raises:
        SecretResolutionError: If the reference is empty, unsupported, or AWS
            cannot return a value.
    """
    normalized_ref = secret_ref.strip()
    if not normalized_ref:
        raise SecretResolutionError("Secret reference must not be empty")

    if _is_ssm_reference(normalized_ref):
        return _resolve_ssm_parameter(normalized_ref, region_name=region_name)

    if _is_secrets_manager_reference(normalized_ref):
        return _resolve_secrets_manager_secret(
            normalized_ref,
            region_name=region_name,
        )

    errors: list[str] = []
    for resolver in (_resolve_ssm_parameter, _resolve_secrets_manager_secret):
        try:
            return resolver(normalized_ref, region_name=region_name)
        except SecretResolutionError as exc:
            errors.append(str(exc))

    raise SecretResolutionError(
        f"Unable to resolve secret reference {normalized_ref!r}: " + "; ".join(errors)
    )


def _resolve_ssm_parameter(secret_ref: str, *, region_name: Optional[str]) -> str:
    client = boto3.client("ssm", region_name=region_name)
    try:
        response = client.get_parameter(Name=secret_ref, WithDecryption=True)
    except (BotoCoreError, ClientError) as exc:
        raise SecretResolutionError(
            f"Unable to resolve SSM parameter reference {secret_ref!r}"
        ) from exc

    value = response.get("Parameter", {}).get("Value")
    if not value:
        raise SecretResolutionError(
            f"SSM parameter reference {secret_ref!r} returned no value"
        )
    return str(value)


def _resolve_secrets_manager_secret(
    secret_ref: str,
    *,
    region_name: Optional[str],
) -> str:
    client = boto3.client("secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_ref)
    except (BotoCoreError, ClientError) as exc:
        raise SecretResolutionError(
            f"Unable to resolve Secrets Manager reference {secret_ref!r}"
        ) from exc

    secret_string = response.get("SecretString")
    if secret_string:
        return str(secret_string)

    secret_binary = response.get("SecretBinary")
    if isinstance(secret_binary, bytes):
        return secret_binary.decode("utf-8")
    if isinstance(secret_binary, str):
        return base64.b64decode(secret_binary).decode("utf-8")

    raise SecretResolutionError(
        f"Secrets Manager reference {secret_ref!r} returned no value"
    )


def _is_ssm_reference(secret_ref: str) -> bool:
    return (
        secret_ref.startswith("/")
        or ":ssm:" in secret_ref
        or ":parameter/" in secret_ref
    )


def _is_secrets_manager_reference(secret_ref: str) -> bool:
    return ":secretsmanager:" in secret_ref or ":secret:" in secret_ref
