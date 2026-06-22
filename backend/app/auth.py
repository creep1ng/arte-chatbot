import hashlib
import hmac
import time
from typing import Optional

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from backend.app.config import settings
from backend.app.secret_resolver import configured_secret_value

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_chat_api_key() -> Optional[str]:
    """Get CHAT_API_KEY from plaintext config or a runtime secret reference."""
    return configured_secret_value(
        settings.chat_api_key,
        settings.chat_api_key_secret_ref,
        region_name=settings.aws_region,
    )


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


def api_key_principal(api_key: str) -> str:
    """Return a stable non-secret principal identifier for an API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_chatwoot_signature(
    payload: bytes,
    signature: Optional[str],
    secret: Optional[str],
    *,
    timestamp: Optional[str] = None,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify Chatwoot webhook HMAC signatures.

    Chatwoot AgentBot webhooks sign ``{timestamp}.{payload}`` and prefix the
    digest with ``sha256=``. Older/local tests may sign the raw payload only;
    both forms are accepted when no timestamp is present.
    """
    if not isinstance(payload, bytes) or not signature or not secret:
        return False

    received_digest = signature.removeprefix("sha256=")
    candidates = [payload]
    if timestamp:
        try:
            timestamp_seconds = int(timestamp)
        except ValueError:
            return False
        if abs(int(time.time()) - timestamp_seconds) > tolerance_seconds:
            return False
        candidates.insert(0, f"{timestamp}.".encode("utf-8") + payload)

    secret_bytes = secret.encode("utf-8")
    for signed_payload in candidates:
        expected_digest = hmac.new(
            secret_bytes,
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(received_digest, expected_digest):
            return True
    return False
