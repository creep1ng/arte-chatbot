"""Admin-authenticated chat proxy endpoints."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.admin_auth import verify_admin_key
from backend.app.auth import api_key_principal
from backend.app.config import settings
from backend.app.message_buffer import (
    add_to_buffer,
    clear_pending_chat_response,
    clear_processing,
    flush_buffer,
    get_buffer_count,
    is_buffering,
    is_processing,
    pop_pending_chat_response,
    schedule_flush,
)
from backend.app.security import (
    check_rate_limit,
    validate_session_id,
)
from backend.app.session import session_manager

chat_router = APIRouter(tags=["admin-chat"])


class AdminChatRequest(BaseModel):
    """Request model for the admin chat proxy endpoint."""

    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    is_final: Optional[bool] = Field(
        default=None,
        description="Hint to flush multi-message buffer immediately",
    )


class AdminBufferingResponse(BaseModel):
    """Response returned while admin multi-message buffering is active."""

    status: str = "buffering"
    session_id: str
    poll_url: Optional[str] = Field(default=None)


class AdminBufferResultResponse(BaseModel):
    """Response returned when polling an admin buffered chat result."""

    status: str = Field(default="pending")
    session_id: str
    result: Optional[str] = Field(default=None)


def _admin_principal(admin_key: str) -> str:
    """Return a stable principal namespace for admin chat sessions."""
    return f"admin:{api_key_principal(admin_key)}"


def _bind_or_validate_admin_session(session_id: str, principal: str) -> None:
    """Bind unknown admin chat sessions or validate existing ownership."""
    if not session_manager.has_session_owner(session_id):
        session_manager.bind_session(session_id, principal)
        return

    if not session_manager.is_session_owner(session_id, principal):
        raise HTTPException(status_code=403, detail="Forbidden session_id")


async def _process_admin_buffer_expiry(
    session_id: str,
    joined_message: str,
) -> None:
    """Delegate admin buffer expiry processing to the existing chat callback."""
    from backend.main import _on_buffer_window_expired

    await _on_buffer_window_expired(session_id, joined_message)


@chat_router.post("/chat")
async def admin_chat_endpoint(
    request: AdminChatRequest,
    admin_key: Annotated[str, Depends(verify_admin_key)],
) -> object:
    """Process chat messages through the admin-authenticated proxy."""
    from backend.app.llm_client import LLMServiceError
    from backend.main import (
        _process_chat_message,
        file_inputs_client,
        llm_client,
        s3_client,
    )

    principal = _admin_principal(admin_key)
    check_rate_limit(principal)

    session_id = request.session_id or str(uuid.uuid4())
    validate_session_id(session_id)
    _bind_or_validate_admin_session(session_id, principal)
    request_id = str(uuid.uuid4())

    if settings.multi_message_buffer_enabled:
        current_count = get_buffer_count(session_id)

        if request.is_final or current_count >= 4:
            overflow_result = await add_to_buffer(session_id, request.message)
            joined = overflow_result or await flush_buffer(session_id)
            if joined:
                if len(joined) > settings.max_chat_message_chars:
                    raise HTTPException(
                        status_code=413,
                        detail="Buffered message too large",
                    )
                request = AdminChatRequest(
                    message=joined,
                    session_id=session_id,
                    is_final=request.is_final,
                )
        else:
            clear_pending_chat_response(session_id)
            clear_processing(session_id)
            await add_to_buffer(session_id, request.message)
            schedule_flush(
                session_id,
                settings.buffer_window_seconds,
                _process_admin_buffer_expiry,
            )
            return JSONResponse(
                status_code=202,
                content=AdminBufferingResponse(
                    session_id=session_id,
                    poll_url=f"/admin/chat/buffer-result/{session_id}",
                ).model_dump(),
            )

    try:
        return await _process_chat_message(
            session_id=session_id,
            message=request.message,
            llm_client=llm_client,
            s3_client=s3_client,
            file_inputs_client=file_inputs_client,
            request_id=request_id,
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=503, detail="LLM service unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@chat_router.get(
    "/chat/buffer-result/{session_id}",
    response_model=AdminBufferResultResponse,
)
async def get_admin_buffer_result(
    session_id: str,
    admin_key: Annotated[str, Depends(verify_admin_key)],
) -> AdminBufferResultResponse:
    """Poll for an admin buffered chat response."""
    validate_session_id(session_id)

    principal = _admin_principal(admin_key)
    check_rate_limit(principal)
    _bind_or_validate_admin_session(session_id, principal)

    chat_response_json = pop_pending_chat_response(session_id)
    if chat_response_json:
        return AdminBufferResultResponse(
            status="ready",
            session_id=session_id,
            result=chat_response_json,
        )

    if is_buffering(session_id) or is_processing(session_id):
        return AdminBufferResultResponse(status="pending", session_id=session_id)

    return AdminBufferResultResponse(status="not_found", session_id=session_id)
