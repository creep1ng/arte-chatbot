"""DynamoDB implementation of the chatbot state repository."""

from datetime import datetime, timezone
import time
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from backend.app.state_repository import (
    BufferMessage,
    BufferState,
    ChatTurn,
    OwnershipConflictError,
    RateLimitDecision,
    SessionState,
    TokenTotals,
)


class DynamoDBStateRepository:
    """Persist chatbot state in a single DynamoDB table.

    Keys follow the migration design:
    - ``PK=SESSION#{session_id}``, ``SK=META|TURN#{iso}|TOKENS|BUFFER``
    - ``PK=RATE#{principal}``, ``SK=WINDOW#{epoch_bucket}``
    """

    def __init__(
        self,
        table_name: Optional[str] = None,
        *,
        table: Optional[Any] = None,
        region_name: Optional[str] = None,
        key_prefix: str = "",
        session_ttl_seconds: int = 30 * 24 * 60 * 60,
        buffer_ttl_seconds: int = 24 * 60 * 60,
        rate_ttl_seconds: int = 24 * 60 * 60,
    ) -> None:
        if table is None and not table_name:
            raise ValueError("table_name is required when table is not provided")

        self._table = table or boto3.resource(
            "dynamodb", region_name=region_name
        ).Table(table_name)
        self._key_prefix = key_prefix.strip("#")
        self._session_ttl_seconds = session_ttl_seconds
        self._buffer_ttl_seconds = buffer_ttl_seconds
        self._rate_ttl_seconds = rate_ttl_seconds

    def get_session(self, session_id: str, max_turns: int = 20) -> SessionState:
        """Return persisted session state or an empty state for cold starts."""
        if max_turns < 1:
            raise ValueError("max_turns must be greater than zero")

        meta = self._get_item(self._session_pk(session_id), "META")
        tokens = self.get_token_totals(session_id)
        turns = self._get_turns(session_id, max_turns)
        return SessionState(
            session_id=session_id,
            owner=meta.get("owner") if meta else None,
            profile=meta.get("profile") if meta else None,
            turns=turns,
            token_totals=tokens,
        )

    def append_turn(self, session_id: str, turn: ChatTurn) -> None:
        """Append a conversation turn as an immutable item."""
        timestamp = self._to_utc(turn.timestamp).isoformat()
        self._table.put_item(
            Item={
                "PK": self._session_pk(session_id),
                "SK": f"TURN#{timestamp}",
                "question": turn.question,
                "answer": turn.answer,
                "timestamp": timestamp,
                "source_documents": turn.source_documents,
                "expires_at": self._ttl(self._session_ttl_seconds),
            }
        )

    def bind_owner(self, session_id: str, owner: str) -> None:
        """Conditionally bind a session owner."""
        try:
            self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "META"},
                UpdateExpression="SET #owner = :owner, expires_at = :ttl",
                ConditionExpression="attribute_not_exists(#owner) OR #owner = :owner",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":ttl": self._ttl(self._session_ttl_seconds),
                },
            )
        except ClientError as exc:
            if (
                exc.response.get("Error", {}).get("Code")
                == "ConditionalCheckFailedException"
            ):
                raise OwnershipConflictError(
                    f"Session {session_id!r} is owned by another principal"
                ) from exc
            raise

    def get_owner(self, session_id: str) -> Optional[str]:
        """Return the persisted owner if present."""
        item = self._get_item(self._session_pk(session_id), "META")
        return item.get("owner") if item else None

    def set_user_profile(self, session_id: str, profile: str) -> None:
        """Persist the user profile on the session metadata item."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "META"},
            UpdateExpression="SET profile = :profile, expires_at = :ttl",
            ExpressionAttributeValues={
                ":profile": profile,
                ":ttl": self._ttl(self._session_ttl_seconds),
            },
        )

    def add_token_usage(self, session_id: str, totals: TokenTotals) -> None:
        """Accumulate token counters atomically."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "TOKENS"},
            UpdateExpression=(
                "SET expires_at = :ttl "
                "ADD input_tokens :input, output_tokens :output, total_tokens :total"
            ),
            ExpressionAttributeValues={
                ":input": totals.input_tokens,
                ":output": totals.output_tokens,
                ":total": totals.total_tokens,
                ":ttl": self._ttl(self._session_ttl_seconds),
            },
        )

    def get_token_totals(self, session_id: str) -> TokenTotals:
        """Return accumulated token totals for a session."""
        item = self._get_item(self._session_pk(session_id), "TOKENS")
        if not item:
            return TokenTotals()
        return TokenTotals(
            input_tokens=int(item.get("input_tokens", 0)),
            output_tokens=int(item.get("output_tokens", 0)),
            total_tokens=int(item.get("total_tokens", 0)),
        )

    def check_rate_limit(
        self, principal: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Increment a fixed-window shared rate counter and evaluate it."""
        now = int(time.time())
        window_started_at = now - (now % window_seconds)
        response = self._table.update_item(
            Key={
                "PK": self._rate_pk(principal),
                "SK": f"WINDOW#{window_started_at}",
            },
            UpdateExpression=(
                "SET window_started_at = :started, window_seconds = :window, "
                "expires_at = :ttl ADD #count :one"
            ),
            ExpressionAttributeNames={"#count": "count"},
            ExpressionAttributeValues={
                ":one": 1,
                ":started": window_started_at,
                ":window": window_seconds,
                ":ttl": self._ttl(self._rate_ttl_seconds),
            },
            ReturnValues="ALL_NEW",
        )
        count = int(response.get("Attributes", {}).get("count", 0))
        allowed = count <= limit
        retry_after = 0 if allowed else max(1, window_started_at + window_seconds - now)
        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=retry_after,
            remaining=max(0, limit - count),
        )

    def get_buffer_state(self, session_id: str) -> BufferState:
        """Return the current durable buffer state."""
        item = self._get_item(self._session_pk(session_id), "BUFFER")
        if not item:
            return BufferState(session_id=session_id)
        return self._buffer_state_from_item(session_id, item)

    def append_buffer_message(self, session_id: str, message: str) -> BufferState:
        """Append a buffered input message."""
        state = self.get_buffer_state(session_id)
        state.messages.append(
            BufferMessage(message=message, timestamp=datetime.now(timezone.utc))
        )
        self._put_buffer_state(state)
        return state

    def clear_buffer_messages(self, session_id: str) -> None:
        """Clear accumulated buffer messages."""
        state = self.get_buffer_state(session_id)
        state.messages = []
        self._put_buffer_state(state)

    def set_pending_result(self, session_id: str, joined_message: str) -> None:
        """Persist a joined buffer result."""
        state = self.get_buffer_state(session_id)
        state.pending_result = joined_message
        self._put_buffer_state(state)

    def pop_pending_result(self, session_id: str) -> Optional[str]:
        """Consume and clear the pending joined buffer result."""
        state = self.get_buffer_state(session_id)
        result = state.pending_result
        if result is not None:
            state.pending_result = None
            self._put_buffer_state(state)
        return result

    def set_pending_chat_response(self, session_id: str, response_json: str) -> None:
        """Persist a completed chat response for polling."""
        state = self.get_buffer_state(session_id)
        state.pending_chat_response = response_json
        self._put_buffer_state(state)

    def pop_pending_chat_response(self, session_id: str) -> Optional[str]:
        """Consume and clear a pending chat response."""
        state = self.get_buffer_state(session_id)
        result = state.pending_chat_response
        if result is not None:
            state.pending_chat_response = None
            state.processing_started_at = None
            self._put_buffer_state(state)
        return result

    def set_processing(self, session_id: str) -> None:
        """Mark a session as being processed."""
        state = self.get_buffer_state(session_id)
        state.processing_started_at = datetime.now(timezone.utc)
        self._put_buffer_state(state)

    def clear_processing(self, session_id: str) -> None:
        """Clear the processing marker."""
        state = self.get_buffer_state(session_id)
        state.processing_started_at = None
        self._put_buffer_state(state)

    def _get_turns(self, session_id: str, max_turns: int) -> list[ChatTurn]:
        items: list[dict[str, Any]] = []
        exclusive_start_key: Optional[dict[str, Any]] = None

        while len(items) < max_turns:
            query_options: dict[str, Any] = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
                "ExpressionAttributeValues": {
                    ":pk": self._session_pk(session_id),
                    ":prefix": "TURN#",
                },
                "ScanIndexForward": False,
                "Limit": max_turns - len(items),
            }
            if exclusive_start_key is not None:
                query_options["ExclusiveStartKey"] = exclusive_start_key

            response = self._table.query(**query_options)
            items.extend(response.get("Items", []))
            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                break

        return [self._turn_from_item(item) for item in reversed(items)]

    def _put_buffer_state(self, state: BufferState) -> None:
        self._table.put_item(
            Item={
                "PK": self._session_pk(state.session_id),
                "SK": "BUFFER",
                "messages": [
                    {
                        "message": message.message,
                        "timestamp": self._to_utc(message.timestamp).isoformat(),
                    }
                    for message in state.messages
                ],
                "pending_result": state.pending_result,
                "pending_chat_response": state.pending_chat_response,
                "processing_started_at": (
                    self._to_utc(state.processing_started_at).isoformat()
                    if state.processing_started_at
                    else None
                ),
                "expires_at": self._ttl(self._buffer_ttl_seconds),
            }
        )

    def _get_item(self, pk: str, sk: str) -> dict[str, Any]:
        response = self._table.get_item(Key={"PK": pk, "SK": sk})
        return response.get("Item", {})

    def _session_pk(self, session_id: str) -> str:
        key = f"SESSION#{session_id}"
        return f"{self._key_prefix}#{key}" if self._key_prefix else key

    def _rate_pk(self, principal: str) -> str:
        key = f"RATE#{principal}"
        return f"{self._key_prefix}#{key}" if self._key_prefix else key

    @staticmethod
    def _ttl(seconds: int) -> int:
        return int(time.time()) + seconds

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _turn_from_item(item: dict[str, Any]) -> ChatTurn:
        return ChatTurn(
            question=item["question"],
            answer=item["answer"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
            source_documents=list(item.get("source_documents", [])),
        )

    @staticmethod
    def _buffer_state_from_item(session_id: str, item: dict[str, Any]) -> BufferState:
        processing_started_at = item.get("processing_started_at")
        return BufferState(
            session_id=session_id,
            messages=[
                BufferMessage(
                    message=message["message"],
                    timestamp=datetime.fromisoformat(message["timestamp"]),
                )
                for message in item.get("messages", [])
            ],
            pending_result=item.get("pending_result"),
            pending_chat_response=item.get("pending_chat_response"),
            processing_started_at=(
                datetime.fromisoformat(processing_started_at)
                if processing_started_at
                else None
            ),
        )
