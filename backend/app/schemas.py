from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Unified response model for all LLM client methods.

    Attributes:
        text: The LLM output text.
        tool_calls: List of tool call dicts from the LLM response.
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
        total_tokens: Total tokens consumed (input + output).
    """

    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SourceDocument(BaseModel):
    ruta: str
    contenido_relevante: Optional[str] = None


class ChatwootMessage(BaseModel):
    """Nested message object inside a Chatwoot webhook payload."""

    id: int
    content: Optional[str] = None
    content_type: str = "text"
    message_type: Literal["incoming", "outgoing", "activity"] = "incoming"
    private: bool = False


class ChatwootConversation(BaseModel):
    """Nested conversation object inside a Chatwoot webhook payload."""

    id: int
    status: str
    inbox_id: int
    contact_id: int


class ChatwootSender(BaseModel):
    """Nested sender object inside a Chatwoot webhook payload."""

    id: int
    type: Literal["contact", "user", "agent_bot"]
    name: Optional[str] = None


class ChatwootWebhookPayload(BaseModel):
    """Base schema for all Chatwoot webhook payloads."""

    event: str
    account: dict[str, Any] = Field(default_factory=dict)


class MessageCreatedPayload(ChatwootWebhookPayload):
    """Schema for the 'message_created' webhook event."""

    conversation: ChatwootConversation
    sender: ChatwootSender
    message: ChatwootMessage


class ConversationCreatedPayload(ChatwootWebhookPayload):
    """Schema for the 'conversation_created' webhook event."""

    conversation: ChatwootConversation
    sender: ChatwootSender


class ConversationStatusChangedPayload(ChatwootWebhookPayload):
    """Schema for the 'conversation_status_changed' webhook event."""

    conversation: ChatwootConversation
    sender: ChatwootSender
    status: str
