"""DynamoDB implementation of the chatbot state repository."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
from typing import Any, Optional

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from backend.app.state_repository import (
    BufferMessage,
    BufferState,
    ChatTurn,
    OwnershipConflictError,
    ProcessingCompletionResult,
    ProcessingLease,
    ProcessingLeaseReleaseResult,
    ProcessingLeaseResult,
    RateLimitDecision,
    SessionState,
    StaleProcessingOwnershipError,
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
        self._table_name = getattr(self._table, "name", table_name)
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

    def append_turn(
        self,
        session_id: str,
        turn: ChatTurn,
        *,
        generation_id: Optional[str] = None,
        lease_token: Optional[str] = None,
    ) -> None:
        """Append a conversation turn as an immutable item."""
        timestamp = self._to_utc(turn.timestamp).isoformat()
        item = {
            "PK": self._session_pk(session_id),
            "SK": f"TURN#{generation_id or timestamp}",
            "question": turn.question,
            "answer": turn.answer,
            "timestamp": timestamp,
            "source_documents": turn.source_documents,
            "expires_at": self._ttl(self._session_ttl_seconds),
        }
        if generation_id is None:
            self._table.put_item(Item=item)
            return
        self._require_fence(generation_id, lease_token)
        item["processing_generation"] = generation_id
        try:
            self._transact_write(
                [
                    self._lease_condition(session_id, lease_token),
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": item,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if self._is_duplicate_side_effect(exc):
                return

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

    def add_token_usage(
        self,
        session_id: str,
        totals: TokenTotals,
        *,
        generation_id: Optional[str] = None,
        lease_token: Optional[str] = None,
    ) -> None:
        """Accumulate token counters atomically."""
        if generation_id is not None:
            self._require_fence(generation_id, lease_token)
            pk = self._session_pk(session_id)
            try:
                self._transact_write(
                    [
                        self._lease_condition(session_id, lease_token),
                        {
                            "Update": {
                                "TableName": self._table_name,
                                "Key": {"PK": pk, "SK": "TOKENS"},
                                "UpdateExpression": (
                                    "SET expires_at = :ttl ADD input_tokens :input, "
                                    "output_tokens :output, total_tokens :total, "
                                    "#generations :generation_set"
                                ),
                                "ConditionExpression": (
                                    "attribute_not_exists(#generations) OR "
                                    "NOT contains(#generations, :generation)"
                                ),
                                "ExpressionAttributeNames": {
                                    "#generations": "processing_generations"
                                },
                                "ExpressionAttributeValues": {
                                    ":input": totals.input_tokens,
                                    ":output": totals.output_tokens,
                                    ":total": totals.total_tokens,
                                    ":ttl": self._ttl(self._session_ttl_seconds),
                                    ":generation": generation_id,
                                    ":generation_set": {generation_id},
                                },
                            }
                        },
                    ]
                )
            except ClientError as exc:
                if self._is_duplicate_side_effect(exc):
                    return
            return
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
        """Atomically append a buffered input message and refresh its TTL."""
        timestamp = datetime.now(timezone.utc).isoformat()
        response = self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression=(
                "SET #messages = list_append(if_not_exists(#messages, :empty), "
                ":message), #expires_at = :ttl"
            ),
            ExpressionAttributeNames={
                "#messages": "messages",
                "#expires_at": "expires_at",
            },
            ExpressionAttributeValues={
                ":empty": [],
                ":message": [{"message": message, "timestamp": timestamp}],
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
            ReturnValues="ALL_NEW",
        )
        return self._buffer_state_from_item(session_id, response.get("Attributes", {}))

    def clear_buffer_messages(self, session_id: str) -> None:
        """Clear accumulated buffer messages."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression="SET messages = :messages, expires_at = :ttl",
            ExpressionAttributeValues={
                ":messages": [],
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
        )

    def claim_buffer_messages(
        self, session_id: str, token: str, resume: bool = False
    ) -> list[BufferMessage]:
        """Atomically rotate the current message batch out of the buffer."""
        names = {
            "#payload": "processing_payload",
            "#response": "pending_chat_response",
            "#expires_at": "expires_at",
            "#lease_token": "lease_token",
        }
        if resume:
            update = "SET #expires_at = :ttl REMOVE #response"
            condition = "#lease_token = :token AND attribute_exists(#payload)"
        else:
            names["#messages"] = "messages"
            update = (
                "SET #payload = #messages, #expires_at = :ttl "
                "REMOVE #messages, #response"
            )
            condition = (
                "#lease_token = :token AND attribute_not_exists(#payload) "
                "AND attribute_exists(#messages)"
            )
        try:
            response = self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=update,
                ConditionExpression=condition,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues={
                    ":token": token,
                    ":ttl": self._ttl(self._buffer_ttl_seconds),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if self._is_conditional_failure(exc):
                if resume:
                    return []
                return self.claim_buffer_messages(session_id, token, True)
            raise
        return self._buffer_state_from_item(
            session_id, response.get("Attributes", {})
        ).processing_payload

    def set_pending_result(self, session_id: str, joined_message: str) -> None:
        """Persist a joined buffer result."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression="SET pending_result = :value, expires_at = :ttl",
            ExpressionAttributeValues={
                ":value": joined_message,
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
        )

    def pop_pending_result(self, session_id: str) -> Optional[str]:
        """Atomically consume a pending joined buffer result once."""
        return self._pop_pending_string(session_id, "pending_result")

    def set_pending_chat_response(self, session_id: str, response_json: str) -> None:
        """Persist a completed chat response for polling."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression="SET pending_chat_response = :value, expires_at = :ttl",
            ExpressionAttributeValues={
                ":value": response_json,
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
        )

    def pop_pending_chat_response(self, session_id: str) -> Optional[str]:
        """Atomically consume a chat response and its processing marker once."""
        return self._pop_pending_string(
            session_id,
            "pending_chat_response",
            additional_remove="processing_started_at",
        )

    def pop_pending_chat_response_if_unowned(
        self, session_id: str, *, now: Optional[datetime] = None
    ) -> Optional[str]:
        """Atomically consume a response only outside active ownership."""
        current_time = self._to_utc(now or datetime.now(timezone.utc))
        try:
            response = self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=(
                    "REMOVE #response, #processing_started_at, #lease_token, "
                    "#lease_expires_at"
                ),
                ConditionExpression=(
                    "attribute_type(#response, :string_type) AND "
                    "(attribute_not_exists(#lease_token) OR "
                    "(#lease_expires_at <= :now AND "
                    "(attribute_not_exists(#payload) OR "
                    "(attribute_type(#payload, :list_type) AND "
                    "size(#payload) = :zero)) AND "
                    "(attribute_not_exists(#messages) OR "
                    "(attribute_type(#messages, :list_type) AND "
                    "size(#messages) = :zero))))"
                ),
                ExpressionAttributeNames={
                    "#response": "pending_chat_response",
                    "#processing_started_at": "processing_started_at",
                    "#lease_token": "lease_token",
                    "#lease_expires_at": "lease_expires_at",
                    "#payload": "processing_payload",
                    "#messages": "messages",
                },
                ExpressionAttributeValues={
                    ":string_type": "S",
                    ":list_type": "L",
                    ":zero": 0,
                    ":now": self._epoch_seconds(current_time),
                },
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if self._is_conditional_failure(exc):
                return None
            raise
        return str(response["Attributes"]["pending_chat_response"])

    def set_processing(self, session_id: str) -> None:
        """Mark a session as being processed."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression=("SET processing_started_at = :value, expires_at = :ttl"),
            ExpressionAttributeValues={
                ":value": datetime.now(timezone.utc).isoformat(),
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
        )

    def clear_processing(self, session_id: str) -> None:
        """Clear the processing marker."""
        self._table.update_item(
            Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
            UpdateExpression="SET expires_at = :ttl REMOVE processing_started_at",
            ExpressionAttributeValues={
                ":ttl": self._ttl(self._buffer_ttl_seconds),
            },
        )

    def _pop_pending_string(
        self,
        session_id: str,
        attribute: str,
        *,
        additional_remove: Optional[str] = None,
    ) -> Optional[str]:
        attribute_names = {"#pending": attribute}
        remove_expression = "#pending"
        if additional_remove is not None:
            attribute_names["#additional"] = additional_remove
            remove_expression = "#pending, #additional"

        try:
            response = self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=f"REMOVE {remove_expression}",
                ConditionExpression="attribute_type(#pending, :string_type)",
                ExpressionAttributeNames=attribute_names,
                ExpressionAttributeValues={":string_type": "S"},
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if (
                exc.response.get("Error", {}).get("Code")
                == "ConditionalCheckFailedException"
            ):
                return None
            raise

        result = response["Attributes"][attribute]
        return str(result)

    def try_acquire_processing_lease(
        self, session_id: str, *, now: datetime, lease: ProcessingLease
    ) -> ProcessingLeaseResult:
        """Atomically acquire an absent or expired processing lease."""
        now_utc = self._to_utc(now)
        lease_expires = self._to_utc(lease.expires_at)
        try:
            response = self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=(
                    "SET #lease_token = :token, #lease_expires_at = :lease_expires, "
                    "#processing_started_at = :started, #expires_at = :ttl"
                ),
                ConditionExpression=(
                    "(attribute_not_exists(#payload) OR "
                    "attribute_type(#payload, :list_type)) AND "
                    "(attribute_not_exists(#messages) OR "
                    "attribute_type(#messages, :list_type)) AND "
                    "((attribute_type(#payload, :list_type) AND "
                    "size(#payload) > :zero) OR (attribute_type(#messages, "
                    ":list_type) AND size(#messages) > :zero)) AND "
                    "(attribute_not_exists(#lease_token) OR "
                    "attribute_not_exists(#lease_expires_at) OR "
                    "#lease_expires_at <= :now)"
                ),
                ExpressionAttributeNames={
                    "#lease_token": "lease_token",
                    "#lease_expires_at": "lease_expires_at",
                    "#processing_started_at": "processing_started_at",
                    "#expires_at": "expires_at",
                    "#payload": "processing_payload",
                    "#messages": "messages",
                },
                ExpressionAttributeValues={
                    ":token": lease.token,
                    ":lease_expires": self._epoch_seconds(lease_expires),
                    ":started": now_utc.isoformat(),
                    ":now": self._epoch_seconds(now_utc),
                    ":ttl": self._ttl(self._buffer_ttl_seconds),
                    ":list_type": "L",
                    ":zero": 0,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if self._is_conditional_failure(exc):
                return ProcessingLeaseResult(acquired=False)
            raise
        state = self._buffer_state_from_item(session_id, response.get("Attributes", {}))
        return ProcessingLeaseResult(acquired=True, lease=state.processing_lease)

    def release_processing_lease(
        self, session_id: str, token: str
    ) -> ProcessingLeaseReleaseResult:
        """Atomically release a processing lease owned by ``token``."""
        try:
            self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=(
                    "SET #expires_at = :ttl REMOVE #lease_token, "
                    "#lease_expires_at, #processing_started_at"
                ),
                ConditionExpression="#lease_token = :token",
                ExpressionAttributeNames={
                    "#lease_token": "lease_token",
                    "#lease_expires_at": "lease_expires_at",
                    "#processing_started_at": "processing_started_at",
                    "#expires_at": "expires_at",
                },
                ExpressionAttributeValues={
                    ":token": token,
                    ":ttl": self._ttl(self._buffer_ttl_seconds),
                },
            )
        except ClientError as exc:
            if self._is_conditional_failure(exc):
                return ProcessingLeaseReleaseResult(released=False)
            raise
        return ProcessingLeaseReleaseResult(released=True)

    def complete_processing(
        self, session_id: str, token: str, response_json: Optional[str]
    ) -> ProcessingCompletionResult:
        """Fence response publication and lease payload cleanup by token."""
        names = {
            "#lease_token": "lease_token",
            "#lease_expires_at": "lease_expires_at",
            "#processing_started_at": "processing_started_at",
            "#payload": "processing_payload",
            "#pending_result": "pending_result",
            "#response": "pending_chat_response",
            "#expires_at": "expires_at",
        }
        values: dict[str, Any] = {
            ":token": token,
            ":ttl": self._ttl(self._buffer_ttl_seconds),
        }
        update = (
            "SET #expires_at = :ttl REMOVE #lease_token, #lease_expires_at, "
            "#processing_started_at, #payload, #pending_result, #response"
        )
        if response_json is not None:
            values[":response"] = response_json
            update = (
                "SET #expires_at = :ttl, #response = :response REMOVE "
                "#lease_token, #lease_expires_at, #processing_started_at, "
                "#payload, #pending_result"
            )
        try:
            self._table.update_item(
                Key={"PK": self._session_pk(session_id), "SK": "BUFFER"},
                UpdateExpression=update,
                ConditionExpression="#lease_token = :token",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if self._is_conditional_failure(exc):
                return ProcessingCompletionResult(completed=False)
            raise
        return ProcessingCompletionResult(completed=True)

    def _lease_condition(
        self, session_id: str, lease_token: Optional[str]
    ) -> dict[str, Any]:
        return {
            "ConditionCheck": {
                "TableName": self._table_name,
                "Key": {"PK": self._session_pk(session_id), "SK": "BUFFER"},
                "ConditionExpression": "#lease_token = :token",
                "ExpressionAttributeNames": {"#lease_token": "lease_token"},
                "ExpressionAttributeValues": {":token": lease_token},
            }
        }

    def _transact_write(self, items: list[dict[str, Any]]) -> None:
        serializer = TypeSerializer()
        serialized = []
        for action in items:
            operation, parameters = next(iter(action.items()))
            request = dict(parameters)
            for field in ("Key", "Item", "ExpressionAttributeValues"):
                if field in request:
                    request[field] = {
                        key: serializer.serialize(value)
                        for key, value in request[field].items()
                    }
            serialized.append({operation: request})
        self._table.meta.client.transact_write_items(TransactItems=serialized)

    @staticmethod
    def _require_fence(generation_id: str, lease_token: Optional[str]) -> None:
        if not generation_id or not lease_token:
            raise ValueError("generation_id and lease_token must be provided together")

    @staticmethod
    def _is_duplicate_side_effect(exc: ClientError) -> bool:
        if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
            raise exc
        try:
            lease_reason, marker_reason = (
                reason["Code"] for reason in exc.response["CancellationReasons"]
            )
        except (KeyError, TypeError, ValueError):
            raise exc
        if lease_reason == "ConditionalCheckFailed" and marker_reason in (
            "None",
            "ConditionalCheckFailed",
        ):
            raise StaleProcessingOwnershipError from exc
        if (lease_reason, marker_reason) == ("None", "ConditionalCheckFailed"):
            return True
        raise exc

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

    @classmethod
    def _epoch_seconds(cls, value: datetime) -> Decimal:
        delta = cls._to_utc(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return Decimal(delta.days * 86400 + delta.seconds) + Decimal(
            delta.microseconds
        ) / Decimal(1_000_000)

    @staticmethod
    def _is_conditional_failure(exc: ClientError) -> bool:
        return (
            exc.response.get("Error", {}).get("Code")
            == "ConditionalCheckFailedException"
        )

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
        lease_token = item.get("lease_token")
        lease_expires_at = item.get("lease_expires_at")
        return BufferState(
            session_id=session_id,
            messages=[
                BufferMessage(
                    message=message["message"],
                    timestamp=datetime.fromisoformat(message["timestamp"]),
                )
                for message in item.get("messages", [])
            ],
            processing_payload=[
                BufferMessage(
                    message=message["message"],
                    timestamp=datetime.fromisoformat(message["timestamp"]),
                )
                for message in item.get("processing_payload", [])
            ],
            pending_result=item.get("pending_result"),
            pending_chat_response=item.get("pending_chat_response"),
            processing_started_at=(
                datetime.fromisoformat(processing_started_at)
                if processing_started_at
                else None
            ),
            processing_lease=(
                ProcessingLease(
                    token=lease_token,
                    expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(
                        microseconds=int(Decimal(str(lease_expires_at)) * 1_000_000)
                    ),
                )
                if lease_token is not None and lease_expires_at is not None
                else None
            ),
        )
