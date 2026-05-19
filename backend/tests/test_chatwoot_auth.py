"""Tests for Chatwoot webhook signature verification."""

import hashlib
import hmac

from backend.app.auth import verify_chatwoot_signature


def _signature(payload: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest for *payload*."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


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
