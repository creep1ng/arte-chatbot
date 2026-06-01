"""Webhook event dispatcher for Chatwoot.

Routes incoming webhook payloads to the appropriate handler, enforces
idempotency via Redis, and logs all events with structured context.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from backend.app.chatwoot_client import ChatwootClient
from backend.app.config_provider import ConfigProvider
from backend.app.escalation_handler import EscalationHandler
from backend.app.message_buffer import RedisMessageBuffer
from backend.app.redis_cache import RedisCache
from backend.app.schemas import (
    ChatwootWebhookPayload,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    MessageCreatedPayload,
)

logger = logging.getLogger(__name__)

_PROCESSED_SET_TTL_SECONDS = 3600
_MAX_BUFFER_MESSAGES = 5

ProcessMessageCallback = Callable[[str, str, list[Any]], Awaitable[str]]


class ChatwootHandler:
    """Dispatches Chatwoot webhook events to specialised handlers.

    Args:
        chatwoot_client: Client for the Chatwoot Application API.
        redis_cache: Redis cache for idempotency and state.
        config_provider: Runtime configuration provider.
    """

    def __init__(
        self,
        chatwoot_client: ChatwootClient,
        redis_cache: RedisCache,
        config_provider: ConfigProvider,
        message_buffer: Optional[RedisMessageBuffer] = None,
        session_manager: Optional[Any] = None,
        escalation_handler: Optional[EscalationHandler] = None,
        process_message: Optional[ProcessMessageCallback] = None,
    ) -> None:
        self._client = chatwoot_client
        self._redis = redis_cache
        self._config = config_provider
        self._buffer = message_buffer
        self._sessions = session_manager
        self._escalation = escalation_handler
        self._process_message = process_message
        self._flush_tasks: dict[str, asyncio.Task[None]] = {}

    async def handle_event(self, payload: ChatwootWebhookPayload) -> None:
        """Route a webhook payload to the correct handler.

        Idempotency is enforced for ``message_created`` events using a
        Redis set with a 1-hour TTL.
        """
        event = payload.event
        conversation_id = getattr(payload, "conversation", None)
        conv_id = conversation_id.id if conversation_id else None

        logger.info(
            "chatwoot_event_received",
            extra={
                "event_type": event,
                "conversation_id": conv_id,
            },
        )

        if event == "message_created" and isinstance(payload, MessageCreatedPayload):
            if await self._is_duplicate(payload.message.id):
                logger.info(
                    "chatwoot_duplicate_skipped",
                    extra={
                        "message_id": payload.message.id,
                        "conversation_id": conv_id,
                    },
                )
                return
            await self._handle_message_created(payload)
            await self._mark_processed(payload.message.id)
        elif event == "conversation_created" and isinstance(
            payload, ConversationCreatedPayload
        ):
            await self._handle_conversation_created(payload)
        elif event == "conversation_status_changed" and isinstance(
            payload, ConversationStatusChangedPayload
        ):
            await self._handle_conversation_status_changed(payload)
        else:
            logger.warning(
                "chatwoot_unknown_event",
                extra={
                    "event_type": event,
                    "conversation_id": conv_id,
                },
            )

    async def _handle_message_created(self, payload: MessageCreatedPayload) -> None:
        """Handle a ``message_created`` webhook.

        Buffers contact messages for later LLM processing. Human-agent
        messages flush/cancel pending buffers so the human response wins.
        """
        conversation_id = payload.conversation.id
        conversation_key = str(conversation_id)
        sender_type = payload.sender.type
        content = payload.message.content or ""
        message_type = payload.message.message_type

        if payload.message.private or message_type == "outgoing":
            logger.info(
                "chatwoot_message_ignored conversation_id=%s message_id=%s",
                conversation_id,
                payload.message.id,
                extra={
                    "conversation_id": conversation_id,
                    "message_id": payload.message.id,
                    "message_type": message_type,
                    "private": payload.message.private,
                },
            )
            return

        if sender_type == "agent_bot":
            logger.info(
                "chatwoot_agent_bot_self_message_ignored conversation_id=%s message_id=%s",
                conversation_id,
                payload.message.id,
                extra={
                    "conversation_id": conversation_id,
                    "message_id": payload.message.id,
                    "sender_type": sender_type,
                },
            )
            return

        if sender_type == "user":
            if self._buffer is not None:
                await self._buffer.flush_and_cancel(conversation_key)
            logger.info(
                "human agent message detected conversation_id=%s message_id=%s",
                conversation_id,
                payload.message.id,
                extra={
                    "conversation_id": conversation_id,
                    "sender_type": sender_type,
                    "message_id": payload.message.id,
                },
            )
        elif sender_type == "contact":
            account_id = int(payload.account.get("id", 1))
            session_id: Optional[str] = None
            if self._sessions is not None:
                session_id = (
                    await self._sessions.get_or_create_session_for_conversation(
                        conversation_key, account_id=account_id
                    )
                )

            profile = self._config.get_channel_profile(
                str(payload.conversation.inbox_id)
            )
            window_seconds = int(getattr(profile, "buffer_window_seconds", 5))
            buffer_state: Any = None
            if self._buffer is not None:
                buffer_state = await self._buffer.add_message(
                    conversation_key, content, window_seconds
                )
            await self._client.send_typing_indicator(conversation_id)
            if self._should_process_full_buffer(buffer_state):
                self._cancel_scheduled_flush(conversation_key)
                await self._process_full_buffer(
                    conversation_id=conversation_id,
                    conversation_key=conversation_key,
                    session_id=session_id,
                )
            else:
                self._schedule_buffer_flush(
                    conversation_id=conversation_id,
                    conversation_key=conversation_key,
                    session_id=session_id,
                    window_seconds=window_seconds,
                )
            logger.info(
                "user message received conversation_id=%s message_id=%s",
                conversation_id,
                payload.message.id,
                extra={
                    "conversation_id": conversation_id,
                    "sender_type": sender_type,
                    "message_id": payload.message.id,
                    "content_preview": content[:50],
                },
            )
        else:
            logger.info(
                "bot/agent_bot message received conversation_id=%s message_id=%s",
                conversation_id,
                payload.message.id,
                extra={
                    "conversation_id": conversation_id,
                    "sender_type": sender_type,
                    "message_id": payload.message.id,
                },
            )

    async def _handle_conversation_created(
        self, payload: ConversationCreatedPayload
    ) -> None:
        """Handle a ``conversation_created`` webhook.

        Creates the conversation-to-session mapping through SessionManager.
        ``SessionManager`` owns idempotency, so repeated webhooks reuse the
        existing mapping rather than generating a new session ID.
        """
        account_id = int(payload.account.get("id", 1))
        if self._sessions is not None:
            await self._sessions.get_or_create_session_for_conversation(
                str(payload.conversation.id), account_id=account_id
            )
        logger.info(
            "conversation_created conversation_id=%s inbox_id=%s",
            payload.conversation.id,
            payload.conversation.inbox_id,
            extra={
                "conversation_id": payload.conversation.id,
                "inbox_id": payload.conversation.inbox_id,
                "contact_id": payload.conversation.contact_id,
            },
        )

    def _should_process_full_buffer(self, buffer_state: Any) -> bool:
        """Return true when a buffer state has reached the processing limit."""
        if buffer_state is None:
            return False

        messages = getattr(buffer_state, "messages", None)
        return isinstance(messages, list) and len(messages) >= _MAX_BUFFER_MESSAGES

    def _schedule_buffer_flush(
        self,
        conversation_id: int,
        conversation_key: str,
        session_id: Optional[str],
        window_seconds: int,
    ) -> None:
        """Schedule delayed processing after the debounce window expires."""
        if (
            self._buffer is None
            or self._process_message is None
            or self._sessions is None
            or session_id is None
        ):
            return

        self._cancel_scheduled_flush(conversation_key)
        task = asyncio.create_task(
            self._flush_buffer_after_window(
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                session_id=session_id,
                window_seconds=window_seconds,
            )
        )
        self._flush_tasks[conversation_key] = task

    def _cancel_scheduled_flush(self, conversation_key: str) -> None:
        """Cancel an existing delayed flush for a conversation."""
        task = self._flush_tasks.pop(conversation_key, None)
        if task and not task.done():
            task.cancel()

    async def _flush_buffer_after_window(
        self,
        conversation_id: int,
        conversation_key: str,
        session_id: str,
        window_seconds: int,
    ) -> None:
        """Flush and process a buffered message after the debounce window."""
        try:
            await asyncio.sleep(window_seconds)
            await self._process_full_buffer(
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                session_id=session_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "chatwoot_buffer_flush_failed conversation_id=%s: %s",
                conversation_id,
                exc,
            )
        finally:
            current_task = asyncio.current_task()
            if self._flush_tasks.get(conversation_key) is current_task:
                self._flush_tasks.pop(conversation_key, None)

    async def _process_full_buffer(
        self,
        conversation_id: int,
        conversation_key: str,
        session_id: Optional[str],
    ) -> None:
        """Flush a full buffer, call the injected processor, and persist history."""
        if (
            self._buffer is None
            or self._process_message is None
            or self._sessions is None
            or session_id is None
        ):
            return

        joined_message = await self._buffer.flush(conversation_key)
        if not joined_message:
            return

        history = await self._sessions.get_history_async(session_id)
        response_text = await self._process_message(session_id, joined_message, history)
        await self._client.send_message(conversation_id, response_text)
        await self._sessions.add_turn_async(
            session_id,
            joined_message,
            response_text,
            [],
        )

    async def _handle_conversation_status_changed(
        self, payload: ConversationStatusChangedPayload
    ) -> None:
        """Handle a ``conversation_status_changed`` webhook.

        Currently a stub that logs the event.
        """
        logger.info(
            "conversation_status_changed conversation_id=%s new_status=%s",
            payload.conversation.id,
            payload.status,
            extra={
                "conversation_id": payload.conversation.id,
                "new_status": payload.status,
            },
        )

    async def _is_duplicate(self, message_id: int) -> bool:
        """Return ``True`` if *message_id* has already been processed."""
        key = self._redis._build_key("processed_messages", "")
        return await self._redis.sismember(key, str(message_id))

    async def _mark_processed(self, message_id: int) -> bool:
        """Mark *message_id* as processed with a 1-hour TTL.

        .. note::
            Redis sets do not support TTL on individual members, so the
            entire set is given a TTL. In production this may be replaced
            with a sorted set or per-message key.
        """
        key = self._redis._build_key("processed_messages", "")
        result = await self._redis.sadd(key, str(message_id))
        await self._redis.set(
            f"{key}:ttl",
            "1",
            ttl=_PROCESSED_SET_TTL_SECONDS,
        )
        return result
