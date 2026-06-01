"""Endpoint security helpers for authenticated chat sessions."""

import re

from fastapi import HTTPException

from backend.app.config import settings
from backend.app.rate_limit import rate_limiter
from backend.app.session import session_manager

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


def check_rate_limit(principal: str) -> None:
    """Apply API rate limiting for a hashed principal."""
    decision = rate_limiter.check(
        principal,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def bind_or_validate_session(session_id: str, principal: str, *, is_new: bool) -> None:
    """Bind new sessions and reject client-provided sessions not issued here."""
    if is_new:
        session_manager.bind_session(session_id, principal)
        return

    if not session_manager.has_session_owner(session_id):
        raise HTTPException(status_code=403, detail="Unknown session_id")

    if not session_manager.is_session_owner(session_id, principal):
        raise HTTPException(status_code=403, detail="Forbidden session_id")


def validate_session_id(session_id: str) -> None:
    """Validate externally supplied session identifiers."""
    if len(
        session_id
    ) > settings.max_session_id_chars or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status_code=422, detail="Invalid session_id")
