"""Webhook event dispatcher for Chatwoot.

Routes incoming webhook payloads to the appropriate handler, enforces
idempotency via Redis, and logs all events with structured context.
"""

import logging

from backend.app.chatwoot_client import ChatwootClient
from backend.app.config_provider import ConfigProvider
from backend.app.redis_cache import RedisCache
from backend.app.schemas import (
    ChatwootWebhookPayload,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    MessageCreatedPayload,
)

logger = logging.getLogger(__name__)

_PROCESSED_SET_TTL_SECONDS = 3600


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
    ) -> None:
        self._client = chatwoot_client
        self._redis = redis_cache
        self._config = config_provider

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

        Currently a stub that logs the event. Full buffering and LLM
        response flow will be implemented in PR #3.
        """
        conversation_id = payload.conversation.id
        sender_type = payload.sender.type
        content = payload.message.content or ""

        if sender_type == "user":
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

        Currently a stub that logs the event.
        """
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
