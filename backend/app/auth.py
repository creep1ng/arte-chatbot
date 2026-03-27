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
