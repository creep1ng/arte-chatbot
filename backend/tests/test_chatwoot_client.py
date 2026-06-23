"""Tests for ChatwootClient async HTTP wrapper.

Uses respx to mock the Chatwoot Application API and validates
rate-limiting, retries, error handling, and optional outbox behaviour.
"""

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from backend.app.chatwoot_client import ChatwootClient


@pytest.fixture
def outbox() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(outbox: AsyncMock) -> ChatwootClient:
    return ChatwootClient(
        base_url="https://chatwoot.example.com",
        agent_bot_token="test-token",
        account_id=1,
        outbox=outbox,
    )


class TestConstructor:
    """Client must initialise with correct defaults."""

    def test_base_url_stripped(self, client: ChatwootClient) -> None:
        assert client._base_url == "https://chatwoot.example.com"

    def test_auth_header_set(self, client: ChatwootClient) -> None:
        headers = client._client.headers
        assert headers["api_access_token"] == "test-token"
        assert "Authorization" not in headers

    def test_timeout_configured(self, client: ChatwootClient) -> None:
        assert client._client.timeout == httpx.Timeout(30.0)


class TestSendMessage:
    """POST /accounts/{id}/conversations/{id}/messages"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, client: ChatwootClient) -> None:
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(
                return_value=httpx.Response(200, json={"id": 99, "content": "hello"})
            )
            result = await client.send_message(42, "hello")
            assert result == {"id": 99, "content": "hello"}
            assert route.called

    @pytest.mark.asyncio
    async def test_send_message_4xx_no_retry(self, client: ChatwootClient) -> None:
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(return_value=httpx.Response(422, json={"error": "invalid"}))
            result = await client.send_message(42, "hello")
            assert result == {}
            assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_send_message_5xx_retries_then_outbox(
        self, client: ChatwootClient, outbox: Any
    ) -> None:
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(return_value=httpx.Response(500, text="boom"))
            result = await client.send_message(42, "hello")
            assert result == {}
            assert route.call_count == 3
            outbox.lpush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_message_respects_retry_after(
        self, client: ChatwootClient, outbox: Any
    ) -> None:
        del outbox
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(
                return_value=httpx.Response(
                    429, text="rate limited", headers={"Retry-After": "2"}
                )
            )
            result = await client.send_message(42, "hello")
            assert result == {}
            assert route.call_count == 3


class TestSendTypingIndicator:
    """Typing indicator via activity message."""

    @pytest.mark.asyncio
    async def test_send_typing_indicator(self, client: ChatwootClient) -> None:
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(return_value=httpx.Response(200, json={"id": 1}))
            success = await client.send_typing_indicator(42)
            assert success is True
            request = route.calls.last.request
            import json

            body = json.loads(request.content)
            assert body["message_type"] == "activity"
            assert body["content"] == "typing_on"


class TestToggleStatus:
    """POST toggle_status."""

    @pytest.mark.asyncio
    async def test_toggle_status_success(self, client: ChatwootClient) -> None:
        with respx.mock:
            respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/toggle_status"
            ).mock(return_value=httpx.Response(200, json={"status": "resolved"}))
            result = await client.toggle_status(42, "resolved")
            assert result == {"status": "resolved"}

    @pytest.mark.asyncio
    async def test_toggle_status_4xx(self, client: ChatwootClient) -> None:
        with respx.mock:
            respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/toggle_status"
            ).mock(return_value=httpx.Response(404))
            result = await client.toggle_status(42, "resolved")
            assert result == {}


class TestAssignConversation:
    """POST assignments."""

    @pytest.mark.asyncio
    async def test_assign_conversation(self, client: ChatwootClient) -> None:
        with respx.mock:
            route = respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/assignments"
            ).mock(return_value=httpx.Response(200, json={"id": 42}))
            result = await client.assign_conversation(42, team_id=3, assignee_id=7)
            assert result == {"id": 42}
            request = route.calls.last.request
            import json

            body = json.loads(request.content)
            assert body["team_id"] == 3
            assert body["assignee_id"] == 7


class TestAddLabel:
    """POST labels."""

    @pytest.mark.asyncio
    async def test_add_label(self, client: ChatwootClient) -> None:
        with respx.mock:
            respx.post(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/labels"
            ).mock(return_value=httpx.Response(200, json={"labels": ["urgent"]}))
            result = await client.add_label(42, "urgent")
            assert result == {"labels": ["urgent"]}


class TestFetchMessages:
    """GET messages."""

    @pytest.mark.asyncio
    async def test_fetch_messages(self, client: ChatwootClient) -> None:
        with respx.mock:
            route = respx.get(
                "https://chatwoot.example.com/api/v1/accounts/1/conversations/42/messages"
            ).mock(return_value=httpx.Response(200, json={"payload": [{"id": 1}]}))
            result = await client.fetch_messages(42, limit=5)
            assert result == {"payload": [{"id": 1}]}
            assert "limit=5" in str(route.calls.last.request.url)


class TestOutbox:
    """Outbox pattern for failed actions."""

    @pytest.mark.asyncio
    async def test_enqueue_failed_action(
        self, client: ChatwootClient, outbox: Any
    ) -> None:
        action = {"type": "send_message", "conversation_id": 42}
        result = await client.enqueue_failed_action(action)
        assert result is True
        outbox.lpush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_outbox_stub(
        self, client: ChatwootClient, outbox: Any
    ) -> None:
        outbox.lrange.return_value = ['{"type": "send_message"}']
        result = await client.process_outbox()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "send_message"
