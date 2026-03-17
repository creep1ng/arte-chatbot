import hmac
import os

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_chat_api_key() -> str:
    key = os.environ.get("CHAT_API_KEY")
    if not key:
        raise RuntimeError("CHAT_API_KEY environment variable is not set")
    return key


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
    if not hmac.compare_digest(api_key, _get_chat_api_key()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key
