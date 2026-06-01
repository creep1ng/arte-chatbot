"""Conversation logger service for writing structured JSON logs to S3.

Provides async fire-and-forget conversation logging. Each turn in a
conversation is serialized as a Pydantic model and uploaded to S3
as a JSON file. Failures are caught silently to never block responses.
"""

import asyncio
from collections import defaultdict
import logging
import re
from typing import Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from backend.app.admin_schemas import ConversationLogSummary, LogFilterParams
from backend.app.config import settings
from backend.app.s3_client import S3Client

logger = logging.getLogger(__name__)

_REDACTION_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+?\d[\d .()/-]{7,}\d)\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
]


def redact_text(text: str) -> str:
    """Redact common sensitive values before writing logs."""
    redacted = text
    for pattern in _REDACTION_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


_log_reader_s3 = S3Client()


class ConversationLogEntry(BaseModel):
    """Structured log entry for a single conversation turn.

    Attributes:
        session_id: Unique session identifier.
        turn_number: Sequential turn number within the session.
        timestamp: ISO 8601 timestamp of the turn.
        user_message: The user's message text.
        bot_response: The bot's response text.
        intent_type: Classified intent type (FAQ, product_info, etc.).
        escalate: Whether the turn was escalated to a human agent.
        source_documents: List of S3 paths to source documents used.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        total_tokens: Total tokens consumed.
        response_time_ms: Response time in milliseconds.
        model: LLM model identifier used.
        git_commit_hash: Git commit hash for traceability.
        user_profile: Inferred user profile (novato, intermedio, experto).
    """

    session_id: str
    turn_number: int
    timestamp: str
    user_message: str
    bot_response: str
    intent_type: str
    escalate: bool
    source_documents: list[str] = Field(default_factory=list)
    input_tokens: int
    output_tokens: int
    total_tokens: int
    response_time_ms: float
    model: str
    git_commit_hash: str
    user_profile: Optional[str] = None

    @model_validator(mode="after")
    def _redact_sensitive_text(self) -> "ConversationLogEntry":
        if settings.conversation_log_redaction_enabled:
            self.user_message = redact_text(self.user_message)
            self.bot_response = redact_text(self.bot_response)
        return self


class ConversationLogger:
    """Async conversation logger that writes structured JSON to S3.

    Uses fire-and-forget pattern: log_turn never blocks the caller and
    silently catches all exceptions to avoid affecting chat responses.
    """

    def __init__(
        self,
        s3_client: S3Client,
        bucket: str,
        prefix: str = "conversations",
    ) -> None:
        """Initialize the ConversationLogger.

        Args:
            s3_client: An S3Client instance for uploading logs.
            bucket: S3 bucket name.
            prefix: Key prefix for log files. Defaults to 'conversations'.
        """
        self._s3_client = s3_client
        self._bucket = bucket
        self._prefix = prefix

    def _upload(self, entry: ConversationLogEntry) -> None:
        """Upload a single log entry to S3 (synchronous).

        Builds the S3 key as: {prefix}/{session_id}/{turn_number}_{timestamp}.json

        Args:
            entry: The conversation log entry to upload.
        """
        key = (
            f"{self._prefix}/{entry.session_id}/"
            f"{entry.turn_number}_{entry.timestamp}.json"
        )
        data = entry.model_dump_json().encode("utf-8")
        self._s3_client.put_object(key=key, data=data, content_type="application/json")

    async def log_turn(self, entry: ConversationLogEntry) -> None:
        """Log a conversation turn asynchronously (fire-and-forget).

        Runs _upload in a thread to avoid blocking the event loop.
        Catches ALL exceptions silently — logging failures must never
        affect the chat response.

        Args:
            entry: The conversation log entry to log.
        """
        try:
            await asyncio.to_thread(self._upload, entry)
        except Exception:
            logger.warning(
                "Conversation log failed for session=%s turn=%d",
                entry.session_id,
                entry.turn_number,
                exc_info=True,
            )


async def list_logs(
    filters: LogFilterParams,
) -> Tuple[list[ConversationLogSummary], int]:
    """List and filter conversation logs from S3.

    Args:
        filters: Filtering and pagination parameters.

    Returns:
        Tuple of (paginated summaries, total count).
    """
    prefix = f"{settings.conversation_log_prefix}/"
    objects = await _log_reader_s3.list_objects(prefix=prefix)

    entries: list[ConversationLogEntry] = []
    for obj in objects:
        key = obj.get("Key", "")
        if not key.endswith(".json"):
            continue
        try:
            data = await asyncio.to_thread(_log_reader_s3.download_pdf, key)
            entry = ConversationLogEntry.model_validate_json(data)
            entries.append(entry)
        except Exception:
            continue

    filtered = entries
    if filters.session_id:
        filtered = [e for e in filtered if e.session_id == filters.session_id]
    if filters.intent_type:
        filtered = [e for e in filtered if e.intent_type == filters.intent_type]
    if filters.escalated is not None:
        filtered = [e for e in filtered if e.escalate == filters.escalated]
    if filters.date_from:
        filtered = [e for e in filtered if e.timestamp >= filters.date_from]
    if filters.date_to:
        filtered = [e for e in filtered if e.timestamp <= filters.date_to]

    sessions: dict[str, list[ConversationLogEntry]] = defaultdict(list)
    for e in filtered:
        sessions[e.session_id].append(e)

    summaries: list[ConversationLogSummary] = []
    for session_id, session_entries in sessions.items():
        sorted_entries = sorted(session_entries, key=lambda x: x.turn_number)
        intent_types = list({e.intent_type for e in sorted_entries})
        escalated = any(e.escalate for e in sorted_entries)
        last_ts = sorted_entries[-1].timestamp if sorted_entries else None
        summaries.append(
            ConversationLogSummary(
                session_id=session_id,
                turn_count=len(sorted_entries),
                last_timestamp=last_ts,
                intent_types=intent_types,
                escalated=escalated,
            )
        )

    summaries.sort(key=lambda s: s.last_timestamp or "", reverse=True)

    total = len(summaries)
    paginated = summaries[filters.offset : filters.offset + filters.limit]
    return paginated, total


async def get_log(session_id: str) -> list[ConversationLogEntry]:
    """Retrieve the full transcript for a session.

    Args:
        session_id: The session identifier.

    Returns:
        List of ConversationLogEntry sorted by turn_number.
    """
    prefix = f"{settings.conversation_log_prefix}/{session_id}/"
    objects = await _log_reader_s3.list_objects(prefix=prefix)

    entries: list[ConversationLogEntry] = []
    for obj in objects:
        key = obj.get("Key", "")
        if not key.endswith(".json"):
            continue
        try:
            data = await asyncio.to_thread(_log_reader_s3.download_pdf, key)
            entry = ConversationLogEntry.model_validate_json(data)
            entries.append(entry)
        except Exception:
            continue

    entries.sort(key=lambda e: e.turn_number)
    return entries
