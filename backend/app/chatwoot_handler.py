"""Webhook event dispatcher for Chatwoot.

Routes incoming webhook payloads to the appropriate handler, enforces
idempotency via the configured state repository, and logs all events with
structured context.
"""

import logging
from typing import Any, Awaitable, Callable, Optional

from backend.app.chatwoot_client import ChatwootClient
from backend.app.config_provider import ConfigProvider
from backend.app.escalation_handler import EscalationHandler
from backend.app.message_buffer import ChatwootMessageBuffer
from backend.app.schemas import (
    ChatwootWebhookPayload,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    MessageCreatedPayload,
)
from backend.app.state_repository import ChatbotStateRepository

logger = logging.getLogger(__name__)

_MAX_BUFFER_MESSAGES = 5

ProcessMessageCallback = Callable[[str, str, list[Any]], Awaitable[str]]


class ChatwootHandler:
    """Dispatches Chatwoot webhook events to specialised handlers.

    Args:
        chatwoot_client: Client for the Chatwoot Application API.
        config_provider: Runtime configuration provider.
    """

    def __init__(
        self,
        chatwoot_client: ChatwootClient,
        config_provider: ConfigProvider,
        state_repository: Optional[ChatbotStateRepository] = None,
        message_buffer: Optional[ChatwootMessageBuffer] = None,
        session_manager: Optional[Any] = None,
        escalation_handler: Optional[EscalationHandler] = None,
        process_message: Optional[ProcessMessageCallback] = None,
    ) -> None:
        self._client = chatwoot_client
        self._config = config_provider
        self._state_repository = state_repository
        self._buffer = message_buffer
        self._sessions = session_manager
        self._escalation = escalation_handler
        self._process_message = process_message
        self._processed_messages: set[str] = set()

    async def handle_event(self, payload: ChatwootWebhookPayload) -> None:
        """Route a webhook payload to the correct handler.

        Idempotency is enforced for ``message_created`` events using durable
        state when configured.
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
            message_id = payload.message.id
            if await self._is_duplicate(message_id):
                logger.info(
                    "chatwoot_duplicate_skipped",
                    extra={
                        "message_id": payload.message.id,
                        "conversation_id": conv_id,
                    },
                )
                return
            await self._handle_message_created(payload)
            await self._mark_processed(message_id)
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
                await self._process_full_buffer(
                    conversation_id=conversation_id,
                    conversation_key=conversation_key,
                    session_id=session_id,
                )
            elif self._process_message is not None:
                await self._process_full_buffer(
                    conversation_id=conversation_id,
                    conversation_key=conversation_key,
                    session_id=session_id,
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

    async def _is_duplicate(self, message_id: str | int) -> bool:
        """Return ``True`` if *message_id* has already been processed."""
        message_key = str(message_id)
        if self._state_repository is not None:
            return self._state_repository.has_processed_chatwoot_message(message_key)
        return message_key in self._processed_messages

    async def _mark_processed(self, message_id: str | int) -> bool:
        """Mark *message_id* as processed with a 1-hour TTL.

        .. note::
            DynamoDB-backed state is the production path. In-memory tracking is
            only a local/test fallback for handlers without a repository.
        """
        message_key = str(message_id)
        if self._state_repository is not None:
            return self._state_repository.mark_chatwoot_message_processed(message_key)
        was_new = message_key not in self._processed_messages
        self._processed_messages.add(message_key)
        return was_new
