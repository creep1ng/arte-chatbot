"""Tests for Chatwoot webhook signature verification."""

import hashlib
import hmac

from backend.app.auth import verify_chatwoot_signature


def _signature(payload: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest for *payload*."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _timestamped_signature(payload: bytes, secret: str, timestamp: str) -> str:
    """Return Chatwoot's timestamped HMAC-SHA256 hex digest."""
    signed_payload = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()


def test_verify_chatwoot_signature_accepts_valid_raw_hex() -> None:
    """Valid raw hex signatures should pass verification."""
    payload = b'{"event":"message_created"}'
    secret = "test-secret"

    assert verify_chatwoot_signature(payload, _signature(payload, secret), secret)


def test_verify_chatwoot_signature_rejects_invalid_signature() -> None:
    """Invalid signatures should fail verification."""
    payload = b'{"event":"message_created"}'

    assert not verify_chatwoot_signature(payload, "invalid", "test-secret")


def test_verify_chatwoot_signature_rejects_missing_signature() -> None:
    """Missing signatures should fail verification."""
    assert not verify_chatwoot_signature(b"{}", None, "test-secret")


def test_verify_chatwoot_signature_accepts_sha256_prefix() -> None:
    """Common sha256=<hex> prefixed signatures should pass verification."""
    payload = b'{"event":"message_created"}'
    secret = "test-secret"
    signature = f"sha256={_signature(payload, secret)}"

    assert verify_chatwoot_signature(payload, signature, secret)


def test_verify_chatwoot_signature_accepts_chatwoot_timestamped_signature() -> None:
    """Real AgentBot webhooks sign '<timestamp>.<body>'."""
    payload = b'{"event":"message_created"}'
    secret = "test-secret"
    timestamp = "1779820000"
    signature = f"sha256={_timestamped_signature(payload, secret, timestamp)}"

    assert verify_chatwoot_signature(payload, signature, secret, timestamp=timestamp)


def test_verify_chatwoot_signature_rejects_timestamped_signature_without_timestamp() -> (
    None
):
    """Timestamped signatures must not verify as body-only signatures."""
    payload = b'{"event":"message_created"}'
    secret = "test-secret"
    signature = f"sha256={_timestamped_signature(payload, secret, '1779820000')}"

    assert not verify_chatwoot_signature(payload, signature, secret)


def test_verify_chatwoot_signature_rejects_garbage_signature() -> None:
    """Unsupported signature formats should fail closed."""
    payload = b'{"event":"message_created"}'

    assert not verify_chatwoot_signature(payload, "sha1=abc", "test-secret")


def test_verify_chatwoot_signature_accepts_empty_body_valid_signature() -> None:
    """Valid HMACs for empty bodies should pass signature verification."""
    payload = b""
    secret = "test-secret"

    assert verify_chatwoot_signature(payload, _signature(payload, secret), secret)


def test_verify_chatwoot_signature_rejects_none_payload() -> None:
    """None payloads must fail closed instead of being treated as empty bodies."""
    secret = "test-secret"
    empty_body_signature = _signature(b"", secret)

    assert not verify_chatwoot_signature(None, empty_body_signature, secret)


def test_verify_chatwoot_signature_rejects_empty_body_invalid_signature() -> None:
    """Empty bodies with invalid signatures should fail verification."""
    assert not verify_chatwoot_signature(b"", "invalid", "test-secret")


def test_verify_chatwoot_signature_rejects_missing_secret() -> None:
    """Enabled webhooks without a configured secret must fail closed."""
    payload = b'{"event":"message_created"}'
    signature = _signature(payload, "test-secret")

    assert not verify_chatwoot_signature(payload, signature, None)
