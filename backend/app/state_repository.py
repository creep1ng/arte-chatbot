"""Repository contracts and DTOs for Lambda-safe chatbot state."""

from datetime import datetime
from typing import Annotated, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import StringConstraints


class StateRepositoryError(Exception):
    """Base exception for state repository failures."""


class OwnershipConflictError(StateRepositoryError):
    """Raised when a session is already owned by another principal."""


class ChatTurn(BaseModel):
    """A single persisted conversation turn."""

    question: str
    answer: str
    timestamp: datetime
    source_documents: list[str] = Field(default_factory=list)


class TokenTotals(BaseModel):
    """Accumulated token usage for a session."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SessionState(BaseModel):
    """Durable state required to restore a chatbot session."""

    session_id: str
    owner: Optional[str] = None
    profile: Optional[str] = None
    turns: list[ChatTurn] = Field(default_factory=list)
    token_totals: TokenTotals = Field(default_factory=TokenTotals)


class BufferMessage(BaseModel):
    """One buffered user message."""

    message: str
    timestamp: datetime


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ProcessingLease(_FrozenModel):
    """Tokenized ownership of buffer processing until a UTC instant."""

    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def _require_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class ProcessingLeaseResult(_FrozenModel):
    """Backend-neutral processing lease acquisition result."""

    acquired: bool
    lease: Optional[ProcessingLease] = None

    @model_validator(mode="after")
    def _require_consistent_lease(self) -> "ProcessingLeaseResult":
        if self.acquired != (self.lease is not None):
            raise ValueError("acquired must match lease presence")
        return self


class ProcessingLeaseReleaseResult(_FrozenModel):
    """Backend-neutral processing lease release result."""

    released: bool


class ProcessingCompletionResult(_FrozenModel):
    """Outcome of a lease-fenced terminal processing transition."""

    completed: bool


class BufferState(BaseModel):
    """Durable multi-message buffer and polling state."""

    session_id: str
    messages: list[BufferMessage] = Field(default_factory=list)
    processing_payload: list[BufferMessage] = Field(default_factory=list)
    pending_result: Optional[str] = None
    pending_chat_response: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_lease: Optional[ProcessingLease] = None


class RateWindow(BaseModel):
    """A fixed rate-limit window counter."""

    principal: str
    window_started_at: int
    window_seconds: int
    count: int = 0


class RateLimitDecision(BaseModel):
    """Result of a shared rate-limit check."""

    allowed: bool
    retry_after_seconds: int = 0
    remaining: int = 0


@runtime_checkable
class ChatbotStateRepository(Protocol):
    """Persistence boundary for Lambda-safe chatbot state."""

    def get_session(self, session_id: str, max_turns: int = 20) -> SessionState:
        """Return persisted session state with at most the latest turns."""

    def append_turn(self, session_id: str, turn: ChatTurn) -> None:
        """Append one conversation turn."""

    def bind_owner(self, session_id: str, owner: str) -> None:
        """Bind a session to a principal if absent or already matching."""

    def get_owner(self, session_id: str) -> Optional[str]:
        """Return the session owner if present."""

    def set_user_profile(self, session_id: str, profile: str) -> None:
        """Persist the user profile for a session."""

    def add_token_usage(self, session_id: str, totals: TokenTotals) -> None:
        """Accumulate token usage for a session."""

    def get_token_totals(self, session_id: str) -> TokenTotals:
        """Return accumulated token usage for a session."""

    def check_rate_limit(
        self, principal: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Increment and evaluate a shared rate-limit counter."""

    def get_buffer_state(self, session_id: str) -> BufferState:
        """Return current buffer state for a session."""

    def append_buffer_message(self, session_id: str, message: str) -> BufferState:
        """Append one message to the durable buffer."""

    def claim_buffer_messages(
        self, session_id: str, token: str, resume: bool = False
    ) -> list[BufferMessage]:
        """Atomically remove and return the messages present at claim time."""

    def clear_buffer_messages(self, session_id: str) -> None:
        """Remove buffered input messages while preserving polling state."""

    def set_pending_result(self, session_id: str, joined_message: str) -> None:
        """Persist a joined buffer result for polling."""

    def pop_pending_result(self, session_id: str) -> Optional[str]:
        """Consume a stored string once; return None when none is pending.

        At most one concurrent caller receives the value. An empty string is a
        pending value rather than absence.
        """

    def set_pending_chat_response(self, session_id: str, response_json: str) -> None:
        """Persist a processed chat response for polling."""

    def pop_pending_chat_response(self, session_id: str) -> Optional[str]:
        """Consume a stored string once and clear its processing marker.

        At most one concurrent caller receives the stored string. An empty string
        is a pending value; ``None`` means that no string was available. The
        winning consume removes the marker in the same operation; an absent
        response leaves the marker unchanged.
        """

    def set_processing(self, session_id: str) -> None:
        """Mark a flushed session as being processed."""

    def clear_processing(self, session_id: str) -> None:
        """Clear the processing marker for a session."""

    def try_acquire_processing_lease(
        self, session_id: str, *, now: datetime, lease: ProcessingLease
    ) -> ProcessingLeaseResult:
        """Acquire processing ownership when no active lease exists."""

    def release_processing_lease(
        self, session_id: str, token: str
    ) -> ProcessingLeaseReleaseResult:
        """Release processing ownership only when the token matches."""

    def complete_processing(
        self, session_id: str, token: str, response_json: Optional[str]
    ) -> ProcessingCompletionResult:
        """Publish optionally and clean up only for the current lease token."""
