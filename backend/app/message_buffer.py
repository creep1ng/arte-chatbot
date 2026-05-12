"""Multi-message input buffer with debounce.

Accumulates incoming messages per session during a configurable window,
then flushes them as a single joined message. Used to handle WhatsApp
users who send multiple short messages in rapid succession.

Design: module-level dicts for buffer state (NOT in SessionManager).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Buffer state per session: session_id -> list of (message, timestamp)
_buffer: dict[str, list[tuple[str, datetime]]] = {}

# Active debounce tasks per session
_buffer_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]

# Pending buffer results: session_id -> (joined_message, timestamp)
_pending_results: dict[str, tuple[str, datetime]] = {}


async def add_to_buffer(
    session_id: str, message: str, max_messages: int = 5
) -> Optional[str]:
    """Append message to session buffer.

    Args:
        session_id: The session identifier.
        message: The message text to buffer.
        max_messages: Maximum messages before overflow flush. Default 5.

    Returns:
        Joined text if overflow triggered, None if still buffering.
    """
    if session_id not in _buffer:
        _buffer[session_id] = []
    _buffer[session_id].append((message, datetime.now(timezone.utc)))

    if len(_buffer[session_id]) >= max_messages:
        # Overflow: flush immediately
        logger.info(
            "Buffer overflow for session %s: %d messages, flushing",
            session_id,
            len(_buffer[session_id]),
        )
        return await flush_buffer(session_id)
    return None


async def flush_buffer(session_id: str) -> Optional[str]:
    """Flush buffer and return joined message. None if empty.

    Also stores the result in _pending_results so callers can retrieve it
    after the async window expiration callback fires.

    Args:
        session_id: The session identifier.

    Returns:
        Messages joined with newline separator, or None if buffer empty.
    """
    messages = _buffer.pop(session_id, [])
    task = _buffer_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
    if not messages:
        return None
    joined = "\n".join(msg for msg, _ in messages)
    _pending_results[session_id] = (joined, datetime.now(timezone.utc))
    return joined


def is_buffering(session_id: str) -> bool:
    """Check if session has buffered messages.

    Args:
        session_id: The session identifier.

    Returns:
        True if buffer has entries, False otherwise.
    """
    return session_id in _buffer and len(_buffer[session_id]) > 0


def get_buffer_count(session_id: str) -> int:
    """Get number of buffered messages for a session.

    Args:
        session_id: The session identifier.

    Returns:
        Number of buffered messages.
    """
    return len(_buffer.get(session_id, []))


def clear_buffer(session_id: str) -> None:
    """Clear buffer state for a session.

    Cancels any active debounce task for the session.

    Args:
        session_id: The session identifier.
    """
    _buffer.pop(session_id, None)
    task = _buffer_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()


def pop_pending_result(session_id: str) -> Optional[str]:
    """Pop and return a pending buffer result for a session.

    Used by the /buffer-result endpoint to retrieve the processed buffer
    result after the window expires. Returns None if no pending result.

    Args:
        session_id: The session identifier.

    Returns:
        The joined message if available, None otherwise.
    """
    result = _pending_results.pop(session_id, None)
    if result:
        return result[0]
    return None


FlushCallback = Callable[[str, str], Awaitable[None]]


def schedule_flush(
    session_id: str,
    window_seconds: int,
    callback: FlushCallback,
) -> None:
    """Schedule a flush after window_seconds. Cancels previous task.

    Args:
        session_id: The session identifier.
        window_seconds: Seconds to wait before flushing.
        callback: Async function called with (session_id, joined_message)
                  when the window expires.
    """
    existing = _buffer_tasks.get(session_id)
    if existing and not existing.done():
        existing.cancel()

    async def _flush_after_delay() -> None:
        try:
            await asyncio.sleep(window_seconds)
        except asyncio.CancelledError:
            return
        message = await flush_buffer(session_id)
        if message:
            await callback(session_id, message)

    _buffer_tasks[session_id] = asyncio.create_task(_flush_after_delay())
