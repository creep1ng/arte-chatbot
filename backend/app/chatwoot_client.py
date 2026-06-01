"""Async HTTP client for the Chatwoot Application API.

Provides connection-pooled requests, automatic retry with exponential
backoff + jitter for transient failures, and a Redis outbox for
background replay of failed actions.
"""

import asyncio
import json
import logging
import random
from typing import Any, Literal, Optional

import httpx

from backend.app.redis_cache import RedisCache

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


class ChatwootClient:
    """High-level async client for Chatwoot.

    Args:
        base_url: Chatwoot instance base URL (e.g. ``https://chatwoot.example.com``).
        agent_bot_token: API token for the agent bot.
        account_id: Chatwoot account identifier.
        redis_cache: Redis cache instance for the outbox.
    """

    def __init__(
        self,
        base_url: str,
        agent_bot_token: str,
        account_id: int,
        redis_cache: RedisCache,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._account_id = account_id
        self._redis = redis_cache
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"api_access_token": agent_bot_token},
        )

    def _conversation_url(self, conversation_id: int, suffix: str = "") -> str:
        path = f"/api/v1/accounts/{self._account_id}/conversations/{conversation_id}"
        if suffix:
            path = f"{path}/{suffix}"
        return f"{self._base_url}{path}"

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry logic.

        Retries on 5xx, 429, and network timeouts up to ``_MAX_RETRIES``
        total attempts. 4xx client errors are not retried.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.NetworkError as exc:
                logger.warning("Chatwoot network error (attempt %d): %s", attempt, exc)
                if attempt == _MAX_RETRIES:
                    return {}
                await self._backoff(response=None, attempt=attempt)
                continue

            if response.status_code < 400:
                return response.json()

            if response.status_code < 500 and response.status_code != 429:
                logger.error(
                    "Chatwoot client error %d: %s", response.status_code, response.text
                )
                return {}

            logger.warning(
                "Chatwoot transient error %d (attempt %d)",
                response.status_code,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                break
            await self._backoff(response=response, attempt=attempt)

        return {}

    async def _backoff(self, response: Optional[httpx.Response], attempt: int) -> None:
        """Sleep with exponential backoff and optional jitter."""
        retry_after: Optional[int] = None
        if response is not None:
            raw = response.headers.get("Retry-After")
            if raw is not None and raw.isdigit():
                retry_after = int(raw)

        if retry_after is not None:
            delay = retry_after
        else:
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            delay = delay * (0.5 + random.random())  # jitter ±50%

        await asyncio.sleep(delay)

    async def send_message(
        self, conversation_id: int, content: str, message_type: str = "outgoing"
    ) -> dict[str, Any]:
        """Send a text message to a conversation.

        Returns:
            Parsed JSON response or empty dict on failure.
        """
        url = self._conversation_url(conversation_id, "messages")
        payload = {"content": content, "message_type": message_type, "private": False}
        result = await self._request_with_retry("POST", url, json=payload)
        if not result:
            await self.enqueue_failed_action(
                {
                    "method": "POST",
                    "url": url,
                    "payload": payload,
                }
            )
        return result

    async def send_typing_indicator(self, conversation_id: int) -> bool:
        """Send a typing-on activity indicator.

        Returns:
            ``True`` if the indicator was accepted.
        """
        url = self._conversation_url(conversation_id, "messages")
        payload = {"message_type": "activity", "content": "typing_on"}
        result = await self._request_with_retry("POST", url, json=payload)
        return bool(result)

    async def toggle_status(
        self, conversation_id: int, status: Literal["pending", "open", "resolved"]
    ) -> dict[str, Any]:
        """Toggle the conversation status.

        Returns:
            Parsed JSON response or empty dict on failure.
        """
        url = self._conversation_url(conversation_id, "toggle_status")
        payload = {"status": status}
        return await self._request_with_retry("POST", url, json=payload)

    async def assign_conversation(
        self,
        conversation_id: int,
        team_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Assign a conversation to a team or user.

        Returns:
            Parsed JSON response or empty dict on failure.
        """
        url = self._conversation_url(conversation_id, "assignments")
        payload: dict[str, Any] = {}
        if team_id is not None:
            payload["team_id"] = team_id
        if assignee_id is not None:
            payload["assignee_id"] = assignee_id
        return await self._request_with_retry("POST", url, json=payload)

    async def add_label(self, conversation_id: int, label: str) -> dict[str, Any]:
        """Add a label to a conversation.

        Returns:
            Parsed JSON response or empty dict on failure.
        """
        url = self._conversation_url(conversation_id, "labels")
        payload = {"labels": [label]}
        return await self._request_with_retry("POST", url, json=payload)

    async def fetch_messages(
        self, conversation_id: int, limit: int = 10
    ) -> dict[str, Any]:
        """Fetch recent messages from a conversation.

        Returns:
            Parsed JSON response or empty dict on failure.
        """
        url = self._conversation_url(conversation_id, "messages")
        params = {"limit": limit}
        return await self._request_with_retry("GET", url, params=params)

    async def enqueue_failed_action(self, action: dict[str, Any]) -> bool:
        """Store a failed action in the Redis outbox for later replay.

        Returns:
            ``True`` if the action was queued successfully.
        """
        key = f"{self._redis._prefix}:outbox"
        try:
            await self._redis.lpush(key, json.dumps(action))
            return True
        except Exception as exc:
            logger.warning("Failed to enqueue action: %s", exc)
            return False

    async def process_outbox(self) -> list[dict[str, Any]]:
        """Retry failed actions from the outbox.

        .. note::
            This is a stub implementation. Full retry logic will be
            added in a later PR.

        Returns:
            List of actions that were in the outbox.
        """
        key = f"{self._redis._prefix}:outbox"
        try:
            raw_items = await self._redis.lrange(key, 0, -1)
            actions = [json.loads(item) for item in raw_items]
            return actions
        except Exception as exc:
            logger.warning("Failed to process outbox: %s", exc)
            return []
