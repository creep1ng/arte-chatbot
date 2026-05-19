import hashlib
import hmac
from typing import Optional

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from backend.app.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_chat_api_key() -> Optional[str]:
    """Get the CHAT_API_KEY from settings, returning None if not set."""
    return settings.chat_api_key


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Dependency that validates the X-API-Key header against the
    CHAT_API_KEY environment variable.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    valid_key = _get_chat_api_key()
    if not valid_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CHAT_API_KEY not configured on server",
        )

    if not hmac.compare_digest(api_key, valid_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key


def verify_chatwoot_signature(
    payload: bytes,
    signature: Optional[str],
    secret: Optional[str],
) -> bool:
    """Verify a Chatwoot webhook HMAC-SHA256 signature.

    Args:
        payload: Raw request body bytes exactly as received.
        signature: Signature header value. Supports raw hex and
            ``sha256=<hex>`` values.
        secret: Shared webhook secret configured in Chatwoot.

    Returns:
        ``True`` when the signature matches, otherwise ``False``.
    """
    if not payload or not signature or not secret:
        return False

    supplied_signature = signature.strip()
    if supplied_signature.startswith("sha256="):
        supplied_signature = supplied_signature.removeprefix("sha256=")

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected_signature)
