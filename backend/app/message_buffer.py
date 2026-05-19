"""Multi-message input buffer with debounce.

Accumulates incoming messages per session during a configurable window,
then flushes them as a single joined message. Used to handle WhatsApp
users who send multiple short messages in rapid succession.

Design: Redis-backed buffer state with in-memory fallback for resilience.
"""

import asyncio
import json
import logging
import time
import warnings
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BufferResult(BaseModel):
    """Result of adding a message to the buffer.

    Attributes:
        is_buffering: True if the buffer is still accumulating messages.
        joined_message: The flushed message if auto-flush occurred, else None.
    """

    is_buffering: bool
    joined_message: Optional[str] = None


class BufferState(BaseModel):
    """Redis-serializable Chatwoot buffer state.

    Attributes:
        conversation_id: Chatwoot conversation identifier.
        messages: Buffered user messages.
        timer_deadline_epoch: Unix timestamp when the debounce window ends.
        is_flushing: True while a human-agent race flush is in progress.
    """

    conversation_id: str
    messages: list[str]
    timer_deadline_epoch: Optional[float] = None
    is_flushing: bool = False


class MessageBuffer:
    """Redis-backed message buffer with in-memory fallback.

    Args:
        redis_cache: Async Redis cache instance for persistent buffer state.
        config_provider: Provider for runtime configuration (window_seconds).
    """

    def __init__(
        self,
        redis_cache: Any,
        config_provider: Any,
    ) -> None:
        self._redis = redis_cache
        self._config = config_provider
        self._tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]
        # In-memory fallback when Redis is unavailable
        self._fallback_buffer: dict[str, list[str]] = {}
        self._fallback_deadline: dict[str, float] = {}
        self._fallback_flushing: dict[str, bool] = {}

    def _buffer_key(self, session_id: str) -> str:
        return self._redis._build_key("buffer", session_id)

    def _lock_key(self, session_id: str) -> str:
        return self._redis._build_key("buffer", session_id, "lock")

    def _window_seconds(self) -> int:
        value = self._config.get("buffer_window_seconds")
        return int(value) if value is not None else 5

    def _max_messages(self) -> int:
        value = self._config.get("buffer_max_messages")
        return int(value) if value is not None else 5

    async def add(
        self,
        session_id: str,
        message: str,
        conversation_id: str = "",
    ) -> BufferResult:
        """Append a message to the session buffer.

        Args:
            session_id: The session identifier.
            message: The message text to buffer.
            conversation_id: Optional Chatwoot conversation ID.

        Returns:
            BufferResult with is_buffering=False and joined_message set if
            the buffer auto-flushed (count limit or deadline expired).
        """
        key = self._buffer_key(session_id)

        # Try Redis first
        try:
            raw = await self._redis.get(key)
            if raw:
                state = BufferState.model_validate(
                    self._normalise_state(session_id, raw)
                )
                if state.is_flushing:
                    return BufferResult(is_buffering=True)
                state.messages.append(message)
                if len(state.messages) >= self._max_messages() or time.time() >= (
                    state.timer_deadline_epoch or 0
                ):
                    joined = "\n".join(state.messages)
                    await self._redis.delete(key)
                    return BufferResult(is_buffering=False, joined_message=joined)
                ok = await self._redis.set(
                    key,
                    state.model_dump_json(),
                    ttl=self._window_seconds() + 60,
                )
                if not ok:
                    raise RuntimeError("Redis set returned False")
                return BufferResult(is_buffering=True)

            # New buffer
            state = BufferState(
                conversation_id=session_id,
                messages=[message],
                timer_deadline_epoch=time.time() + self._window_seconds(),
                is_flushing=False,
            )
            ok = await self._redis.set(
                key,
                state.model_dump_json(),
                ttl=self._window_seconds() + 60,
            )
            if not ok:
                raise RuntimeError("Redis set returned False")
            return BufferResult(is_buffering=True)
        except Exception as exc:
            logger.warning("Redis buffer add failed, falling back to memory: %s", exc)
            return self._add_fallback(session_id, message)

    async def add_message(
        self, conversation_id: str, message: str, window_seconds: int
    ) -> BufferState:
        """Append a Chatwoot message and return persisted buffer state.

        Args:
            conversation_id: Chatwoot conversation identifier.
            message: Message text to buffer.
            window_seconds: Debounce window in seconds for this channel.

        Returns:
            The resulting buffer state.
        """
        key = self._buffer_key(conversation_id)
        state = BufferState(
            conversation_id=conversation_id,
            messages=[],
            timer_deadline_epoch=time.time() + window_seconds,
            is_flushing=False,
        )
        try:
            raw = await self._redis.get(key)
            if raw:
                state = BufferState.model_validate(
                    self._normalise_state(conversation_id, raw)
                )
            if not state.is_flushing:
                state.messages.append(message)
                state.timer_deadline_epoch = time.time() + window_seconds
                ok = await self._redis.set(
                    key,
                    state.model_dump_json(),
                    ttl=window_seconds + 60,
                )
                if not ok:
                    raise RuntimeError("Redis set returned False")
            return state
        except Exception as exc:
            logger.warning("Redis add_message failed, falling back to memory: %s", exc)
            if conversation_id not in self._fallback_buffer:
                self._fallback_buffer[conversation_id] = []
            self._fallback_buffer[conversation_id].append(message)
            self._fallback_deadline[conversation_id] = time.time() + window_seconds
            return BufferState(
                conversation_id=conversation_id,
                messages=list(self._fallback_buffer[conversation_id]),
                timer_deadline_epoch=self._fallback_deadline[conversation_id],
                is_flushing=self._fallback_flushing.get(conversation_id, False),
            )

    def _add_fallback(self, session_id: str, message: str) -> BufferResult:
        """In-memory fallback for add when Redis is unavailable."""
        if (
            session_id in self._fallback_flushing
            and self._fallback_flushing[session_id]
        ):
            return BufferResult(is_buffering=True)

        if session_id not in self._fallback_buffer:
            self._fallback_buffer[session_id] = []
            self._fallback_deadline[session_id] = time.time() + self._window_seconds()

        self._fallback_buffer[session_id].append(message)

        if (
            len(self._fallback_buffer[session_id]) >= self._max_messages()
            or time.time() >= self._fallback_deadline[session_id]
        ):
            joined = "\n".join(self._fallback_buffer.pop(session_id, []))
            self._fallback_deadline.pop(session_id, None)
            self._fallback_flushing.pop(session_id, None)
            return BufferResult(is_buffering=False, joined_message=joined)

        return BufferResult(is_buffering=True)

    async def flush(self, session_id: str) -> Optional[str]:
        """Flush buffer and return joined message. None if empty.

        Args:
            session_id: The session identifier.

        Returns:
            Messages joined with newline separator, or None if buffer empty.
        """
        key = self._buffer_key(session_id)
        lock_key = self._lock_key(session_id)
        messages: list[str] = []
        lock_acquired = False
        try:
            lock_acquired = await self._redis.acquire_lock(lock_key, ttl_seconds=30)
            if not lock_acquired:
                return None
            raw = await self._redis.get(key)
            if raw:
                state = BufferState.model_validate(
                    self._normalise_state(session_id, raw)
                )
                messages = state.messages
                await self._redis.delete(key)
            # Cancel any pending task
            task = self._tasks.pop(session_id, None)
            current_task = asyncio.current_task()
            if task and task is not current_task and not task.done():
                task.cancel()
        except Exception as exc:
            logger.warning("Redis buffer flush failed, falling back to memory: %s", exc)
            messages = self._fallback_buffer.pop(session_id, [])
            self._fallback_deadline.pop(session_id, None)
            self._fallback_flushing.pop(session_id, None)
        finally:
            if lock_acquired:
                await self._redis.release_lock(lock_key)

        # Also check fallback if Redis returned empty but fallback has data
        if not messages and session_id in self._fallback_buffer:
            messages = self._fallback_buffer.pop(session_id, [])
            self._fallback_deadline.pop(session_id, None)
            self._fallback_flushing.pop(session_id, None)

        if messages:
            return "\n".join(messages)
        return None

    async def flush_and_cancel(self, session_id: str) -> Optional[str]:
        """Flush buffer with distributed lock (race-condition guard).

        Used when a human agent sends a message to prevent concurrent
        bot responses.

        Args:
            session_id: The session identifier.

        Returns:
            Joined message or None if buffer was empty.
        """
        lock_key = self._lock_key(session_id)
        try:
            acquired = await self._redis.acquire_lock(lock_key, ttl_seconds=30)
            if not acquired:
                logger.warning(
                    "flush_and_cancel could not acquire lock for session %s", session_id
                )
                return None

            try:
                key = self._buffer_key(session_id)
                raw = await self._redis.get(key)
                if raw:
                    state = BufferState.model_validate(
                        self._normalise_state(session_id, raw)
                    )
                    state.is_flushing = True
                    await self._redis.set(key, state.model_dump_json())
                    messages = state.messages
                    await self._redis.delete(key)
                    if messages:
                        return "\n".join(messages)
                # Cancel any pending task
                task = self._tasks.pop(session_id, None)
                current_task = asyncio.current_task()
                if task and task is not current_task and not task.done():
                    task.cancel()
            finally:
                await self._redis.release_lock(lock_key)
        except Exception as exc:
            logger.warning(
                "Redis buffer flush_and_cancel failed, falling back to memory: %s", exc
            )
            # Fallback: just flush in-memory
            messages = self._fallback_buffer.pop(session_id, [])
            self._fallback_deadline.pop(session_id, None)
            self._fallback_flushing.pop(session_id, None)
            if messages:
                return "\n".join(messages)
        return None

    async def is_buffering(self, session_id: str) -> bool:
        """Check if session has buffered messages.

        Args:
            session_id: The session identifier.

        Returns:
            True if buffer has entries, False otherwise.
        """
        key = self._buffer_key(session_id)
        try:
            raw = await self._redis.get(key)
            if raw:
                state = BufferState.model_validate(
                    self._normalise_state(session_id, raw)
                )
                return len(state.messages) > 0
        except Exception as exc:
            logger.warning("Redis buffer is_buffering failed, using memory: %s", exc)
        # Fallback check
        return (
            session_id in self._fallback_buffer
            and len(self._fallback_buffer[session_id]) > 0
        )

    async def get_count(self, session_id: str) -> int:
        """Get number of buffered messages for a session.

        Args:
            session_id: The session identifier.

        Returns:
            Number of buffered messages.
        """
        key = self._buffer_key(session_id)
        try:
            raw = await self._redis.get(key)
            if raw:
                state = BufferState.model_validate(
                    self._normalise_state(session_id, raw)
                )
                return len(state.messages)
        except Exception as exc:
            logger.warning("Redis buffer get_count failed, using memory: %s", exc)
        # Fallback check
        return len(self._fallback_buffer.get(session_id, []))

    def _normalise_state(self, conversation_id: str, raw: str) -> dict[str, Any]:
        """Load legacy or spec buffer JSON into BufferState-compatible dict."""
        data = json.loads(raw)
        return {
            "conversation_id": data.get("conversation_id", conversation_id),
            "messages": data.get("messages", []),
            "timer_deadline_epoch": data.get(
                "timer_deadline_epoch", data.get("deadline")
            ),
            "is_flushing": data.get("is_flushing", False),
        }


RedisMessageBuffer = MessageBuffer


# ---------------------------------------------------------------------------
# Module-level state for pending results and processing flags
# (not migrated to Redis in this PR — kept for backward compatibility)
# ---------------------------------------------------------------------------

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

# Global MessageBuffer instance (initialized lazily so tests can swap it)
_message_buffer: Optional[MessageBuffer] = None


def _get_message_buffer() -> MessageBuffer:
    """Return the module-level MessageBuffer instance.

    Raises:
        RuntimeError: If the global instance has not been set.
    """
    if _message_buffer is None:
        raise RuntimeError(
            "MessageBuffer has not been initialized. "
            "Set backend.app.message_buffer._message_buffer before calling legacy wrappers."
        )
    return _message_buffer


async def add_to_buffer(
    session_id: str, message: str, max_messages: int = 5
) -> Optional[str]:
    """Append message to session buffer.

    .. deprecated::
        Use ``MessageBuffer.add()`` directly. This wrapper is kept for
        backward compatibility with existing callers.

    Args:
        session_id: The session identifier.
        message: The message text to buffer.
        max_messages: Maximum messages before overflow flush. Default 5.

    Returns:
        Joined text if overflow triggered, None if still buffering.
    """
    warnings.warn(
        "add_to_buffer is deprecated; use MessageBuffer.add()",
        DeprecationWarning,
        stacklevel=2,
    )
    if _message_buffer is not None:
        result = await _message_buffer.add(session_id, message)
        return result.joined_message
    # Legacy fallback
    if session_id not in _buffer:
        _buffer[session_id] = []
    _buffer[session_id].append((message, datetime.now(timezone.utc)))
    if len(_buffer[session_id]) >= max_messages:
        return await flush_buffer(session_id)
    return None


async def flush_buffer(session_id: str) -> Optional[str]:
    """Flush buffer and return joined message. None if empty.

    .. deprecated::
        Use ``MessageBuffer.flush()`` directly.

    Also stores the result in _pending_results so callers can retrieve it
    after the async window expiration callback fires.

    Args:
        session_id: The session identifier.

    Returns:
        Messages joined with newline separator, or None if buffer empty.
    """
    warnings.warn(
        "flush_buffer is deprecated; use MessageBuffer.flush()",
        DeprecationWarning,
        stacklevel=2,
    )
    if _message_buffer is not None:
        return await _message_buffer.flush(session_id)
    # Legacy fallback
    messages = _buffer.pop(session_id, [])
    task = _buffer_tasks.pop(session_id, None)
    current_task = asyncio.current_task()
    if task and task is not current_task and not task.done():
        task.cancel()
    if not messages:
        return None
    joined = "\n".join(msg for msg, _ in messages)
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
    if _message_buffer is not None:
        # We cannot await in a sync function; fall back to legacy dict
        return session_id in _buffer and len(_buffer[session_id]) > 0
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


def set_pending_chat_response(session_id: str, response_json: str) -> None:
    """Store a processed chat response for polling.

    Args:
        session_id: The session identifier.
        response_json: JSON string of the ChatResponse.
    """
    _pending_chat_responses[session_id] = (response_json, datetime.now(timezone.utc))


def pop_pending_chat_response(session_id: str) -> Optional[str]:
    """Pop and return a pending chat response for a session.

    Args:
        session_id: The session identifier.

    Returns:
        The JSON chat response if available, None otherwise.
    """
    result = _pending_chat_responses.pop(session_id, None)
    if result:
        return result[0]
    return None


def clear_pending_chat_response(session_id: str) -> None:
    """Clear any pending chat response for a session.

    Args:
        session_id: The session identifier.
    """
    _pending_chat_responses.pop(session_id, None)
    _processing_sessions.pop(session_id, None)


def set_processing(session_id: str) -> None:
    """Mark a session as having its buffer flushed and being processed.

    Args:
        session_id: The session identifier.
    """
    _processing_sessions[session_id] = datetime.now(timezone.utc)


def clear_processing(session_id: str) -> None:
    """Remove the processing mark for a session.

    Args:
        session_id: The session identifier.
    """
    _processing_sessions.pop(session_id, None)


def is_processing(session_id: str) -> bool:
    """Check if a session is currently being processed after a flush.

    Args:
        session_id: The session identifier.

    Returns:
        True if the session's buffered message is being processed.
    """
    return session_id in _processing_sessions


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
        if _message_buffer is not None:
            message = await _message_buffer.flush(session_id)
        else:
            message = await flush_buffer(session_id)
        if message:
            await callback(session_id, message)

    _buffer_tasks[session_id] = asyncio.create_task(_flush_after_delay())
