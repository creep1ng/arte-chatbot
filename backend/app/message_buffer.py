"""Multi-message input buffer with debounce.

Accumulates incoming messages per session during a configurable window,
then flushes them as a single joined message. Used to handle WhatsApp
users who send multiple short messages in rapid succession.

Local memory mode uses in-process debounce tasks. Repository-backed mode is
Lambda-safe: it stores messages durably and lets ``/buffer-result`` polling
flush due buffers instead of relying on ``asyncio.create_task`` after response.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from backend.app.config import settings
from backend.app.state_repository import (
    ChatbotStateRepository,
    ProcessingLease,
    ProcessingLeaseReleaseResult,
    ProcessingLeaseResult,
)

logger = logging.getLogger(__name__)

_state_repository: Optional[ChatbotStateRepository] = None

# Buffer state per session: session_id -> list of (message, timestamp)
_buffer: dict[str, list[tuple[str, datetime]]] = {}

# Active debounce tasks per session
_buffer_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]

# Pending buffer results: session_id -> (joined_message, timestamp)
_pending_results: dict[str, tuple[str, datetime]] = {}

# Pending chat responses from background processing: session_id -> (chat_response_json, timestamp)
_pending_chat_responses: dict[str, tuple[str, datetime]] = {}

# Sessions whose buffer was flushed and are being processed in background
_processing_sessions: dict[str, datetime] = {}

# Pending delivery and processing state share one lock so consumption and marker
# cleanup are one in-process operation.
_pending_state_lock = RLock()

# Tokenized leases coordinate every local destructive buffer-processing path.
_processing_leases: dict[str, ProcessingLease] = {}
_state_lock = RLock()


@dataclass(frozen=True)
class OwnedBufferedMessage:
    """A flushed message paired with its processing ownership."""

    message: str
    lease: ProcessingLease


def set_state_repository(
    state_repository: Optional[ChatbotStateRepository],
) -> None:
    """Configure durable buffer state for Lambda-safe polling."""
    global _state_repository
    _state_repository = state_repository


async def add_to_buffer(
    session_id: str, message: str, max_messages: int = 5
) -> Optional[OwnedBufferedMessage]:
    """Append message to session buffer.

    Args:
        session_id: The session identifier.
        message: The message text to buffer.
        max_messages: Maximum messages before overflow flush. Default 5.

    Returns:
        Owned joined text if overflow triggered, None if still buffering or
        another worker owns processing.
    """
    if _state_repository is not None:
        state = _state_repository.append_buffer_message(session_id, message)
        if len(state.messages) >= max_messages:
            logger.info(
                "Buffer overflow for session %s: %d messages, flushing",
                session_id,
                len(state.messages),
            )
            return await acquire_and_flush_buffer(session_id)
        return None

    with _state_lock:
        if session_id not in _buffer:
            _buffer[session_id] = []
        _buffer[session_id].append((message, datetime.now(timezone.utc)))
        message_count = len(_buffer[session_id])

    if message_count >= max_messages:
        # Overflow: flush immediately
        logger.info(
            "Buffer overflow for session %s: %d messages, flushing",
            session_id,
            message_count,
        )
        return await acquire_and_flush_buffer(session_id)
    return None


async def flush_buffer(session_id: str) -> Optional[str]:
    """Claim, flush, and release a buffer without retaining processing ownership.

    Processing paths must use :func:`acquire_and_flush_buffer` so ownership is
    retained until their side effects complete.
    """
    owned_message = await acquire_and_flush_buffer(session_id)
    if owned_message is None:
        return None
    try:
        return owned_message.message
    finally:
        release_processing_lease(session_id, owned_message.lease.token)


async def acquire_and_flush_buffer(
    session_id: str,
) -> Optional[OwnedBufferedMessage]:
    """Acquire processing ownership before destructively flushing a buffer."""
    acquired = acquire_processing_lease(session_id)
    if not acquired.acquired or acquired.lease is None:
        return None

    lease = acquired.lease
    try:
        joined = await _flush_owned_buffer(session_id)
    except BaseException:
        release_processing_lease(session_id, lease.token)
        raise
    if joined is None:
        release_processing_lease(session_id, lease.token)
        return None
    return OwnedBufferedMessage(message=joined, lease=lease)


async def _flush_owned_buffer(session_id: str) -> Optional[str]:
    """Flush a buffer after the caller has acquired processing ownership.

    Local mode clears stale pending delivery state before returning the joined
    value to its caller. Repository mode stores the joined value for polling.

    Args:
        session_id: The session identifier.

    Returns:
        Messages joined with newline separator, or None if buffer empty.
    """
    if _state_repository is not None:
        buffer_messages = _state_repository.claim_buffer_messages(session_id)
        if not buffer_messages:
            return None
        joined = "\n".join(message.message for message in buffer_messages)
        _state_repository.set_pending_result(session_id, joined)
        return joined

    with _state_lock:
        buffered_entries = _buffer.pop(session_id, [])
    task = _buffer_tasks.pop(session_id, None)
    current_task = asyncio.current_task()
    if task and task is not current_task and not task.done():
        task.cancel()
    if not buffered_entries:
        return None
    joined = "\n".join(msg for msg, _ in buffered_entries)
    # Clean up stale state from previous flushes to prevent memory leaks
    # and avoid false "not_found" responses while background processing runs.
    with _pending_state_lock:
        _pending_results.pop(session_id, None)
        _pending_chat_responses.pop(session_id, None)
        _processing_sessions.pop(session_id, None)
    return joined


def is_buffering(session_id: str) -> bool:
    """Check if session has buffered messages.

    Args:
        session_id: The session identifier.

    Returns:
        True if buffer has entries, False otherwise.
    """
    if _state_repository is not None:
        return len(_state_repository.get_buffer_state(session_id).messages) > 0
    return session_id in _buffer and len(_buffer[session_id]) > 0


def get_buffer_count(session_id: str) -> int:
    """Get number of buffered messages for a session.

    Args:
        session_id: The session identifier.

    Returns:
        Number of buffered messages.
    """
    if _state_repository is not None:
        return len(_state_repository.get_buffer_state(session_id).messages)
    return len(_buffer.get(session_id, []))


def clear_buffer(session_id: str) -> None:
    """Clear buffer state for a session.

    Cancels any active debounce task for the session.

    Args:
        session_id: The session identifier.
    """
    if _state_repository is not None:
        _state_repository.clear_buffer_messages(session_id)
        _state_repository.pop_pending_result(session_id)
        _state_repository.clear_processing(session_id)
        return

    _buffer.pop(session_id, None)
    task = _buffer_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
    with _pending_state_lock:
        _pending_results.pop(session_id, None)
        _processing_sessions.pop(session_id, None)


def pop_pending_result(session_id: str) -> Optional[str]:
    """Pop and return a pending buffer result for a session.

    Used by the /buffer-result endpoint to retrieve the processed buffer
    result after the window expires. Returns None if no pending result.

    Args:
        session_id: The session identifier.

    Returns:
        The joined message if available, None otherwise.
    """
    if _state_repository is not None:
        return _state_repository.pop_pending_result(session_id)

    with _pending_state_lock:
        result = _pending_results.pop(session_id, None)
        return result[0] if result is not None else None


def set_pending_result(session_id: str, joined_message: str) -> None:
    """Store a joined buffer result for consume-once polling."""
    if _state_repository is not None:
        _state_repository.set_pending_result(session_id, joined_message)
        return
    with _pending_state_lock:
        _pending_results[session_id] = (
            joined_message,
            datetime.now(timezone.utc),
        )


def set_pending_chat_response(session_id: str, response_json: str) -> None:
    """Store a processed chat response for polling.

    Args:
        session_id: The session identifier.
        response_json: JSON string of the ChatResponse.
    """
    if _state_repository is not None:
        _state_repository.set_pending_chat_response(session_id, response_json)
        return
    with _pending_state_lock:
        _pending_chat_responses[session_id] = (
            response_json,
            datetime.now(timezone.utc),
        )


def pop_pending_chat_response(session_id: str) -> Optional[str]:
    """Pop and return a pending chat response for a session.

    Args:
        session_id: The session identifier.

    Returns:
        The JSON chat response if available, None otherwise.
    """
    if _state_repository is not None:
        return _state_repository.pop_pending_chat_response(session_id)

    with _pending_state_lock:
        result = _pending_chat_responses.pop(session_id, None)
        if result is None:
            return None
        _processing_sessions.pop(session_id, None)
        return result[0]


def clear_pending_chat_response(session_id: str) -> None:
    """Clear any pending chat response for a session.

    Args:
        session_id: The session identifier.
    """
    if _state_repository is not None:
        _state_repository.pop_pending_chat_response(session_id)
        _state_repository.clear_processing(session_id)
        return

    with _pending_state_lock:
        _pending_chat_responses.pop(session_id, None)
        _processing_sessions.pop(session_id, None)


def set_processing(session_id: str) -> None:
    """Mark a session as having its buffer flushed and being processed.

    Args:
        session_id: The session identifier.
    """
    if _state_repository is not None:
        _state_repository.set_processing(session_id)
        return
    with _pending_state_lock:
        _processing_sessions[session_id] = datetime.now(timezone.utc)


def clear_processing(session_id: str) -> None:
    """Remove the processing mark for a session.

    Args:
        session_id: The session identifier.
    """
    if _state_repository is not None:
        _state_repository.clear_processing(session_id)
        return
    with _pending_state_lock:
        _processing_sessions.pop(session_id, None)


def acquire_processing_lease(
    session_id: str,
    *,
    now: Optional[datetime] = None,
    token: Optional[str] = None,
) -> ProcessingLeaseResult:
    """Try to claim processing ownership with deterministic test inputs."""
    current_time = _to_utc(now if now is not None else datetime.now(timezone.utc))
    lease = ProcessingLease(
        token=token if token is not None else uuid4().hex,
        expires_at=current_time
        + timedelta(seconds=settings.buffer_processing_lease_seconds),
    )
    if _state_repository is not None:
        return _state_repository.try_acquire_processing_lease(
            session_id, now=current_time, lease=lease
        )
    return try_acquire_local_processing_lease(session_id, now=current_time, lease=lease)


def try_acquire_local_processing_lease(
    session_id: str, *, now: datetime, lease: ProcessingLease
) -> ProcessingLeaseResult:
    """Atomically acquire an absent or expired local processing lease."""
    current_time = _to_utc(now)
    with _state_lock:
        current = _processing_leases.get(session_id)
        if current is not None and current_time < _to_utc(current.expires_at):
            return ProcessingLeaseResult(acquired=False)
        _processing_leases[session_id] = lease
        return ProcessingLeaseResult(acquired=True, lease=lease)


def release_processing_lease(
    session_id: str, token: str
) -> ProcessingLeaseReleaseResult:
    """Release processing ownership only for the current token."""
    if _state_repository is not None:
        return _state_repository.release_processing_lease(session_id, token)
    return release_local_processing_lease(session_id, token)


def release_local_processing_lease(
    session_id: str, token: str
) -> ProcessingLeaseReleaseResult:
    """Atomically release local processing ownership for the caller's token."""
    with _state_lock:
        current = _processing_leases.get(session_id)
        if current is None or current.token != token:
            return ProcessingLeaseReleaseResult(released=False)
        del _processing_leases[session_id]
        return ProcessingLeaseReleaseResult(released=True)


def is_processing(session_id: str) -> bool:
    """Check if a session is currently being processed after a flush.

    Args:
        session_id: The session identifier.

    Returns:
        True if the session's buffered message is being processed.
    """
    if _state_repository is not None:
        return (
            _state_repository.get_buffer_state(session_id).processing_started_at
            is not None
        )
    with _pending_state_lock:
        return session_id in _processing_sessions


def has_active_processing_lease(
    session_id: str, *, now: Optional[datetime] = None
) -> bool:
    """Return whether a tokenized processing lease is currently active."""
    current_time = _to_utc(now or datetime.now(timezone.utc))
    if _state_repository is not None:
        lease = _state_repository.get_buffer_state(session_id).processing_lease
        return lease is not None and current_time < _to_utc(lease.expires_at)
    with _state_lock:
        lease = _processing_leases.get(session_id)
        return lease is not None and current_time < _to_utc(lease.expires_at)


def is_buffer_ready_to_flush(
    session_id: str,
    window_seconds: int,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Return whether the debounce window has elapsed for buffered messages.

    The window is measured from the last buffered message to preserve debounce
    semantics when users send several short messages in quick succession.
    """
    current_time = _to_utc(now or datetime.now(timezone.utc))
    if _state_repository is not None:
        buffer_messages = _state_repository.get_buffer_state(session_id).messages
        if not buffer_messages:
            return False
        last_message_at = _to_utc(buffer_messages[-1].timestamp)
        return current_time >= last_message_at + timedelta(seconds=window_seconds)

    buffered_entries = _buffer.get(session_id, [])
    if not buffered_entries:
        return False
    last_message_at = _to_utc(buffered_entries[-1][1])
    return current_time >= last_message_at + timedelta(seconds=window_seconds)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


FlushCallback = Callable[[str, str, ProcessingLease], Awaitable[None]]


def schedule_flush(
    session_id: str,
    window_seconds: int,
    callback: FlushCallback,
) -> None:
    """Schedule a flush after window_seconds. Cancels previous task.

    In repository-backed Lambda-safe mode this function intentionally does not
    create a background task. Polling ``/buffer-result`` is the durable trigger
    that checks the stored message timestamps and processes due buffers.

    Args:
        session_id: The session identifier.
        window_seconds: Seconds to wait before flushing.
        callback: Async function called with the session, joined message, and
            processing lease when the window expires.
    """
    existing = _buffer_tasks.get(session_id)
    if existing and not existing.done():
        existing.cancel()

    if _state_repository is not None:
        _buffer_tasks.pop(session_id, None)
        logger.info(
            "Repository-backed buffer active for session %s; "
            "skipping in-process debounce task",
            session_id,
        )
        return

    async def _flush_after_delay() -> None:
        try:
            await asyncio.sleep(window_seconds)
        except asyncio.CancelledError:
            return
        owned_message = await acquire_and_flush_buffer(session_id)
        if owned_message is not None:
            await callback(session_id, owned_message.message, owned_message.lease)

    _buffer_tasks[session_id] = asyncio.create_task(_flush_after_delay())
