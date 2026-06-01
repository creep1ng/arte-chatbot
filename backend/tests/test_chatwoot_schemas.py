"""Tests for Chatwoot webhook payload Pydantic schemas.

Validates correct parsing of Chatwoot webhook payloads and rejection
of invalid data (e.g., unknown sender types).
"""

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    ChatwootConversation,
    ChatwootMessage,
    ChatwootSender,
    ChatwootWebhookPayload,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    MessageCreatedPayload,
)


class TestChatwootMessage:
    """Unit tests for the ChatwootMessage schema."""

    def test_valid_message(self) -> None:
        msg = ChatwootMessage(
            id=1,
            content="hello",
            content_type="text",
            private=False,
        )
        assert msg.id == 1
        assert msg.content == "hello"
        assert msg.content_type == "text"
        assert msg.private is False

    def test_defaults(self) -> None:
        msg = ChatwootMessage(id=42)
        assert msg.content is None
        assert msg.content_type == "text"
        assert msg.private is False


class TestChatwootConversation:
    """Unit tests for the ChatwootConversation schema."""

    def test_valid_conversation(self) -> None:
        conv = ChatwootConversation(
            id=10,
            status="open",
            inbox_id=5,
            contact_id=20,
        )
        assert conv.id == 10
        assert conv.status == "open"
        assert conv.inbox_id == 5
        assert conv.contact_id == 20


class TestChatwootSender:
    """Unit tests for the ChatwootSender schema."""

    def test_valid_contact(self) -> None:
        sender = ChatwootSender(id=30, type="contact", name="John")
        assert sender.type == "contact"
        assert sender.name == "John"

    def test_valid_user(self) -> None:
        sender = ChatwootSender(id=31, type="user")
        assert sender.type == "user"
        assert sender.name is None

    def test_valid_agent_bot(self) -> None:
        sender = ChatwootSender(id=32, type="agent_bot")
        assert sender.type == "agent_bot"

    def test_invalid_sender_type(self) -> None:
        with pytest.raises(ValidationError):
            ChatwootSender(id=33, type="invalid")


class TestChatwootWebhookPayload:
    """Unit tests for the base ChatwootWebhookPayload schema."""

    def test_base_payload(self) -> None:
        payload = ChatwootWebhookPayload(
            event="message_created",
            account={"id": 1},
        )
        assert payload.event == "message_created"
        assert payload.account == {"id": 1}

    def test_base_payload_allows_unknown_event_without_account(self) -> None:
        """Real Chatwoot lifecycle events may omit account in the payload."""
        payload = ChatwootWebhookPayload.model_validate(
            {
                "event": "conversation_opened",
                "additional_attributes": {},
                "messages": [],
            }
        )

        assert payload.event == "conversation_opened"
        assert payload.account == {}


class TestMessageCreatedPayload:
    """Unit tests for the MessageCreatedPayload schema."""

    def test_valid_payload(self) -> None:
        payload = MessageCreatedPayload(
            event="message_created",
            account={"id": 1},
            conversation={
                "id": 10,
                "status": "open",
                "inbox_id": 5,
                "contact_id": 20,
            },
            sender={"id": 30, "type": "contact", "name": "John"},
            message={
                "id": 100,
                "content": "Hello",
                "content_type": "text",
                "private": False,
            },
        )
        assert payload.event == "message_created"
        assert payload.message.content == "Hello"
        assert payload.conversation.status == "open"
        assert payload.sender.type == "contact"


class TestConversationCreatedPayload:
    """Unit tests for the ConversationCreatedPayload schema."""

    def test_valid_payload(self) -> None:
        payload = ConversationCreatedPayload(
            event="conversation_created",
            account={"id": 1},
            conversation={
                "id": 11,
                "status": "open",
                "inbox_id": 5,
                "contact_id": 21,
            },
            sender={"id": 31, "type": "user"},
        )
        assert payload.event == "conversation_created"
        assert payload.conversation.id == 11


class TestConversationStatusChangedPayload:
    """Unit tests for the ConversationStatusChangedPayload schema."""

    def test_valid_payload(self) -> None:
        payload = ConversationStatusChangedPayload(
            event="conversation_status_changed",
            account={"id": 1},
            conversation={
                "id": 12,
                "status": "resolved",
                "inbox_id": 5,
                "contact_id": 22,
            },
            sender={"id": 32, "type": "agent_bot"},
            status="resolved",
        )
        assert payload.event == "conversation_status_changed"
        assert payload.status == "resolved"
        assert payload.conversation.status == "resolved"
