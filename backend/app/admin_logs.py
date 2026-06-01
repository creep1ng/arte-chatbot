"""Admin conversation logs endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import (
    ConversationLogEntry,
    ConversationLogSummary,
    LogFilterParams,
)
from backend.app.conversation_logger import get_log, list_logs

logger = logging.getLogger(__name__)

logs_router = APIRouter()


@logs_router.get("/logs")
async def admin_list_logs(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
    session_id: str | None = None,
    intent_type: str | None = None,
    escalated: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List conversation logs with optional filtering and pagination.

    Query parameters mirror LogFilterParams fields.
    """
    filters = LogFilterParams(
        session_id=session_id,
        intent_type=intent_type,
        escalated=escalated,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    try:
        summaries, total = await list_logs(filters)
    except Exception as e:
        logger.error("Failed to list logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversation logs",
        ) from e

    return {"items": summaries, "total": total}


@logs_router.get("/logs/{session_id}", response_model=list[ConversationLogEntry])
async def admin_get_log_detail(
    session_id: str,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> list[ConversationLogEntry]:
    """Retrieve the full transcript for a single session.

    Args:
        session_id: The session identifier.

    Returns:
        List of ConversationLogEntry sorted by turn_number.

    Raises:
        HTTPException: 404 if session has no logs.
    """
    try:
        entries = await get_log(session_id)
    except Exception as e:
        logger.error("Failed to get log detail: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session logs",
        ) from e

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    return entries
