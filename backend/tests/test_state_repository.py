"""Tests for Lambda-safe state repository contracts and DynamoDB behavior."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from numbers import Number
import re
from threading import Barrier, Event, RLock, Thread, current_thread
from typing import Any, Callable

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from backend.app.dynamodb_state_repository import DynamoDBStateRepository
from backend.app.state_repository import (
    BufferMessage,
    ChatTurn,
    OwnershipConflictError,
    ProcessingLease,
    ProcessingLeaseResult,
    TokenTotals,
)


class FakeDynamoDBTable:
    """Small in-memory DynamoDB Table fake for repository unit tests."""

    def __init__(self, query_page_size: int | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.query_calls: list[dict[str, Any]] = []
        self.query_page_size = query_page_size
        self._lock = RLock()

    def get_item(self, Key: dict[str, str]) -> dict[str, Any]:
        with self._lock:
            item = self.items.get((Key["PK"], Key["SK"]))
            return {"Item": deepcopy(item)} if item else {}

    def put_item(self, Item: dict[str, Any]) -> None:
        with self._lock:
            self.items[(Item["PK"], Item["SK"])] = deepcopy(Item)

    def query(
        self,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ScanIndexForward: bool = True,
        Limit: int | None = None,
        ExclusiveStartKey: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        expected_expression = "PK = :pk AND begins_with(SK, :prefix)"
        if KeyConditionExpression != expected_expression:
            raise ValueError(
                f"Unsupported key condition expression: {KeyConditionExpression}"
            )

        with self._lock:
            self.query_calls.append(
                {
                    "ScanIndexForward": ScanIndexForward,
                    "Limit": Limit,
                    "ExclusiveStartKey": deepcopy(ExclusiveStartKey),
                }
            )
            prefix = ExpressionAttributeValues[":prefix"]
            pk = ExpressionAttributeValues[":pk"]
            items = [
                deepcopy(item)
                for (item_pk, item_sk), item in self.items.items()
                if item_pk == pk and item_sk.startswith(prefix)
            ]
            items = sorted(
                items,
                key=lambda item: item["SK"],
                reverse=not ScanIndexForward,
            )

            if ExclusiveStartKey is not None:
                start_index = next(
                    index + 1
                    for index, item in enumerate(items)
                    if item["PK"] == ExclusiveStartKey["PK"]
                    and item["SK"] == ExclusiveStartKey["SK"]
                )
                items = items[start_index:]

            page_limit = Limit
            if self.query_page_size is not None:
                page_limit = min(
                    Limit or self.query_page_size,
                    self.query_page_size,
                )

            page_items = items[:page_limit]
            response: dict[str, Any] = {"Items": page_items}
            if page_limit is not None and len(items) > page_limit:
                response["LastEvaluatedKey"] = {
                    "PK": page_items[-1]["PK"],
                    "SK": page_items[-1]["SK"],
                }
            return response

    def update_item(
        self,
        Key: dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        if ReturnValues not in (None, "ALL_NEW", "ALL_OLD"):
            raise ValueError(f"Unsupported return values: {ReturnValues}")

        key = (Key["PK"], Key["SK"])
        names = ExpressionAttributeNames or {}
        expression = " ".join(UpdateExpression.split())
        used = f"{UpdateExpression} {ConditionExpression or ''}"
        used_names = set(re.findall(r"#[A-Za-z0-9_]+", used))
        used_values = set(re.findall(r":[A-Za-z0-9_]+", used))
        if used_names != set(names) or used_values != set(ExpressionAttributeValues):
            raise ValueError("Unused expression attribute")

        with self._lock:
            item = deepcopy(self.items.get(key, {"PK": Key["PK"], "SK": Key["SK"]}))
            old_item = deepcopy(item)
            self._evaluate_condition(
                item, ConditionExpression, names, ExpressionAttributeValues
            )
            self._apply_update(item, expression, names, ExpressionAttributeValues)
            self.items[key] = deepcopy(item)
            if ReturnValues == "ALL_NEW":
                return {"Attributes": deepcopy(item)}
            if ReturnValues == "ALL_OLD":
                return {"Attributes": old_item}
            return {}

    @staticmethod
    def _evaluate_condition(
        item: dict[str, Any],
        expression: str | None,
        names: dict[str, str],
        values: dict[str, Any],
    ) -> None:
        """Evaluate a supported condition before mutating the item."""
        if expression is None:
            return
        if expression == "attribute_type(#pending, :string_type)":
            pending_name = names.get("#pending")
            if values.get(":string_type") != "S" or not isinstance(
                item.get(pending_name), str
            ):
                FakeDynamoDBTable._conditional_failure("pending value is not a string")
            return
        if expression == (
            "attribute_type(#response, :string_type) AND "
            "(attribute_not_exists(#lease_token) OR (#lease_expires_at <= :now AND "
            "(attribute_not_exists(#payload) OR (attribute_type(#payload, "
            ":list_type) AND size(#payload) = :zero)) AND "
            "(attribute_not_exists(#messages) OR (attribute_type(#messages, "
            ":list_type) AND size(#messages) = :zero))))"
        ):
            response_name = names["#response"]
            lease_token = names["#lease_token"]
            work = [item.get(names[field], []) for field in ("#payload", "#messages")]
            has_no_work = all(isinstance(value, list) and not value for value in work)
            expiry = item.get(names["#lease_expires_at"])
            is_orphan = (
                lease_token in item
                and isinstance(expiry, Number)
                and expiry <= values[":now"]
                and has_no_work
            )
            if (values[":string_type"], values[":list_type"], values[":zero"]) != (
                "S",
                "L",
                0,
            ):
                raise ValueError("Unsupported orphan response values")
            if not isinstance(item.get(response_name), str) or (
                lease_token in item and not is_orphan
            ):
                FakeDynamoDBTable._conditional_failure("response is owned")
            return
        if expression == "attribute_not_exists(#owner) OR #owner = :owner":
            owner_name = names.get("#owner")
            if owner_name != "owner":
                raise ValueError("Unsupported owner attribute mapping")
            if item.get(owner_name) not in (None, values[":owner"]):
                FakeDynamoDBTable._conditional_failure("owner mismatch")
            return
        if expression == (
            "(attribute_not_exists(#payload) OR attribute_type(#payload, "
            ":list_type)) AND (attribute_not_exists(#messages) OR "
            "attribute_type(#messages, :list_type)) AND "
            "((attribute_type(#payload, :list_type) AND size(#payload) > :zero) OR "
            "(attribute_type(#messages, :list_type) AND size(#messages) > :zero)) "
            "AND (attribute_not_exists(#lease_token) OR "
            "attribute_not_exists(#lease_expires_at) OR #lease_expires_at <= :now)"
        ):
            work_fields = names["#payload"], names["#messages"]
            if work_fields != ("processing_payload", "messages"):
                raise ValueError("Unsupported work attribute mapping")
            if (values[":list_type"], values[":zero"]) != ("L", 0):
                raise ValueError("Unsupported work predicate values")
            work = [item.get(field, []) for field in work_fields]
            has_work = any(isinstance(value, list) and value for value in work)
            has_valid_types = all(isinstance(value, list) for value in work)
            has_lease = "lease_token" in item and "lease_expires_at" in item
            expiry = item.get("lease_expires_at")
            is_expired = isinstance(expiry, Number) and expiry <= values[":now"]
            if not has_valid_types or not has_work or (has_lease and not is_expired):
                FakeDynamoDBTable._conditional_failure("lease unavailable or no work")
            return
        if expression == (
            "attribute_not_exists(#lease_token) OR "
            "attribute_not_exists(#lease_expires_at) OR "
            "#lease_expires_at <= :now"
        ):
            token_name = names.get("#lease_token")
            expiry_name = names.get("#lease_expires_at")
            if token_name != "lease_token" or expiry_name != "lease_expires_at":
                raise ValueError("Unsupported lease attribute mapping")
            if (
                token_name in item
                and expiry_name in item
                and item[expiry_name] > values[":now"]
            ):
                FakeDynamoDBTable._conditional_failure("active lease")
            return
        if expression == "#lease_token = :token":
            token_name = names.get("#lease_token")
            if token_name != "lease_token":
                raise ValueError("Unsupported lease token mapping")
            if item.get(token_name) != values[":token"]:
                FakeDynamoDBTable._conditional_failure("token mismatch")
            return
        if expression.startswith("#lease_token = :token AND attribute_"):
            is_resume = expression.endswith("attribute_exists(#payload)")
            is_invalid = item.get(names["#lease_token"]) != values[":token"]
            is_invalid |= (names["#payload"] in item) != is_resume
            is_invalid |= not is_resume and names["#messages"] not in item
            if is_invalid:
                FakeDynamoDBTable._conditional_failure("payload claim failed")
            return
        else:
            raise ValueError(f"Unsupported condition expression: {expression}")

    @staticmethod
    def _conditional_failure(message: str) -> None:
        raise ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": message}},
            "UpdateItem",
        )

    @staticmethod
    def _apply_update(
        item: dict[str, Any],
        expression: str,
        names: dict[str, str],
        values: dict[str, Any],
    ) -> None:
        """Apply one of the repository's supported update expressions."""
        if expression == "SET #owner = :owner, expires_at = :ttl":
            if names.get("#owner") != "owner":
                raise ValueError("Unsupported owner attribute mapping")
            item["owner"] = deepcopy(values[":owner"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression == "SET profile = :profile, expires_at = :ttl":
            item["profile"] = deepcopy(values[":profile"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression in (
            "SET pending_result = :value, expires_at = :ttl",
            "SET pending_chat_response = :value, expires_at = :ttl",
        ):
            pending_name = expression.split()[1]
            item[pending_name] = deepcopy(values[":value"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression == "SET messages = :messages, expires_at = :ttl":
            item["messages"] = deepcopy(values[":messages"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression == "SET processing_started_at = :value, expires_at = :ttl":
            item["processing_started_at"] = deepcopy(values[":value"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression == "SET expires_at = :ttl REMOVE processing_started_at":
            item["expires_at"] = deepcopy(values[":ttl"])
            item.pop("processing_started_at", None)
            return

        if expression in ("REMOVE #pending", "REMOVE #pending, #additional"):
            for alias in expression.removeprefix("REMOVE ").split(", "):
                item.pop(names.get(alias, alias), None)
            return

        if expression == (
            "REMOVE #response, #processing_started_at, #lease_token, #lease_expires_at"
        ):
            for alias in (
                "#response",
                "#processing_started_at",
                "#lease_token",
                "#lease_expires_at",
            ):
                item.pop(names[alias], None)
            return

        if expression == (
            "SET expires_at = :ttl ADD input_tokens :input, "
            "output_tokens :output, total_tokens :total"
        ):
            item["input_tokens"] = int(item.get("input_tokens", 0)) + int(
                values[":input"]
            )
            item["output_tokens"] = int(item.get("output_tokens", 0)) + int(
                values[":output"]
            )
            item["total_tokens"] = int(item.get("total_tokens", 0)) + int(
                values[":total"]
            )
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        if expression in (
            "SET #expires_at = :ttl REMOVE #response",
            "SET #payload = #messages, #expires_at = :ttl REMOVE #messages, #response",
        ):
            if expression.startswith("SET #payload"):
                item[names["#payload"]] = deepcopy(item[names["#messages"]])
                item.pop(names["#messages"])
            item[names["#expires_at"]] = deepcopy(values[":ttl"])
            item.pop(names["#response"], None)
            return

        if (
            expression.startswith("SET #expires_at = :ttl")
            and "#lease_token" in expression
        ):
            item[names["#expires_at"]] = deepcopy(values[":ttl"])
            for attribute in (
                "lease_token",
                "lease_expires_at",
                "processing_started_at",
                "processing_payload",
                "pending_result",
                "pending_chat_response",
            ):
                item.pop(attribute, None)
            if ":response" in values:
                item[names["#response"]] = deepcopy(values[":response"])
            return

        if expression == (
            "SET #lease_token = :token, #lease_expires_at = :lease_expires, "
            "#processing_started_at = :started, #expires_at = :ttl"
        ):
            item[names["#lease_token"]] = deepcopy(values[":token"])
            item[names["#lease_expires_at"]] = deepcopy(values[":lease_expires"])
            item[names["#processing_started_at"]] = deepcopy(values[":started"])
            item[names["#expires_at"]] = deepcopy(values[":ttl"])
            return

        if expression == (
            "SET #expires_at = :ttl REMOVE #lease_token, #lease_expires_at, "
            "#processing_started_at"
        ):
            item[names["#expires_at"]] = deepcopy(values[":ttl"])
            for alias in (
                "#lease_token",
                "#lease_expires_at",
                "#processing_started_at",
            ):
                item.pop(names[alias], None)
            return

        if expression == (
            "SET window_started_at = :started, window_seconds = :window, "
            "expires_at = :ttl ADD #count :one"
        ):
            if names.get("#count") != "count":
                raise ValueError("Unsupported count attribute mapping")
            item["window_started_at"] = deepcopy(values[":started"])
            item["window_seconds"] = deepcopy(values[":window"])
            item["expires_at"] = deepcopy(values[":ttl"])
            item["count"] = int(item.get("count", 0)) + int(values[":one"])
            return

        if expression == (
            "SET #messages = list_append(if_not_exists(#messages, :empty), "
            ":message), #expires_at = :ttl"
        ):
            if names.get("#messages") != "messages":
                raise ValueError("Unsupported messages attribute mapping")
            if names.get("#expires_at") != "expires_at":
                raise ValueError("Unsupported expiry attribute mapping")
            existing_messages = deepcopy(item.get("messages", values[":empty"]))
            item["messages"] = existing_messages + deepcopy(values[":message"])
            item["expires_at"] = deepcopy(values[":ttl"])
            return

        raise ValueError(f"Unsupported update expression: {expression}")


class ProcessingInterleavingTable(FakeDynamoDBTable):
    """Pause a processing mutation after an old read or before an atomic write."""

    def __init__(self) -> None:
        super().__init__()
        self.processing_mutation_started = Event()
        self.allow_processing_mutation = Event()

    def get_item(self, Key: dict[str, str]) -> dict[str, Any]:
        response = super().get_item(Key)
        if current_thread().name == "processing-race" and Key["SK"] == "BUFFER":
            self.processing_mutation_started.set()
            assert self.allow_processing_mutation.wait(timeout=2)
        return response

    def update_item(
        self,
        Key: dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        update_expression = UpdateExpression
        is_processing_update = (
            update_expression.startswith("SET processing_started_at")
            or "REMOVE processing_started_at" in update_expression
        )
        if current_thread().name == "processing-race" and is_processing_update:
            self.processing_mutation_started.set()
            assert self.allow_processing_mutation.wait(timeout=2)
        return super().update_item(
            Key,
            UpdateExpression,
            ExpressionAttributeValues,
            ExpressionAttributeNames,
            ConditionExpression,
            ReturnValues,
        )


class MessageInterleavingTable(ProcessingInterleavingTable):
    """Pause a message mutation after its read or before its field update."""

    def update_item(
        self,
        Key: dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        update_expression = UpdateExpression
        is_message_update = update_expression.startswith(
            "SET messages = :messages"
        ) or update_expression.startswith("SET #messages = list_append")
        if current_thread().name == "processing-race" and is_message_update:
            self.processing_mutation_started.set()
            assert self.allow_processing_mutation.wait(timeout=2)
        return super().update_item(
            Key,
            UpdateExpression,
            ExpressionAttributeValues,
            ExpressionAttributeNames,
            ConditionExpression,
            ReturnValues,
        )


class ClaimInterleavingTable(FakeDynamoDBTable):
    """Pause a claim immediately before or after its atomic rotation."""

    def __init__(self, pause: str) -> None:
        super().__init__()
        self.pause = pause
        self.claim_reached = Event()
        self.allow_claim = Event()

    def update_item(
        self,
        Key: dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        is_claim = (
            current_thread().name == "buffer-claim"
            and UpdateExpression.startswith("SET #payload = #messages")
            and ReturnValues == "ALL_NEW"
        )
        if is_claim and self.pause == "before":
            self.claim_reached.set()
            assert self.allow_claim.wait(timeout=2)
        response = super().update_item(
            Key,
            UpdateExpression,
            ExpressionAttributeValues,
            ExpressionAttributeNames,
            ConditionExpression,
            ReturnValues,
        )
        if is_claim and self.pause == "after":
            self.claim_reached.set()
            assert self.allow_claim.wait(timeout=2)
        return response


def run_paused_buffer_mutation(
    table: ProcessingInterleavingTable,
    mutation: Callable[[], None],
    interleaved_operation: Callable[[], None],
) -> None:
    """Run an operation while a processing mutation holds a stale/queued view."""
    errors: list[BaseException] = []

    def run_mutation() -> None:
        try:
            mutation()
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = Thread(target=run_mutation, name="processing-race")
    thread.start()
    try:
        assert table.processing_mutation_started.wait(timeout=2)
        interleaved_operation()
    finally:
        table.allow_processing_mutation.set()
        thread.join(timeout=2)

    assert thread.is_alive() is False
    assert errors == []


@pytest.fixture()
def repository() -> DynamoDBStateRepository:
    """Create a repository backed by an isolated fake table."""
    return DynamoDBStateRepository(
        table=FakeDynamoDBTable(),
        key_prefix="staging",
        session_ttl_seconds=3600,
        buffer_ttl_seconds=600,
        rate_ttl_seconds=300,
    )


def test_fake_dynamodb_table_isolates_nested_values() -> None:
    """The fake does not leak mutable nested values across table boundaries."""
    table = FakeDynamoDBTable()
    source: dict[str, Any] = {
        "PK": "SESSION#s1",
        "SK": "BUFFER",
        "messages": [{"message": "Hola"}],
    }

    table.put_item(Item=source)
    source["messages"][0]["message"] = "mutated before read"
    first_read = table.get_item(Key={"PK": "SESSION#s1", "SK": "BUFFER"})["Item"]
    first_read["messages"][0]["message"] = "mutated after read"

    second_read = table.get_item(Key={"PK": "SESSION#s1", "SK": "BUFFER"})["Item"]
    assert second_read["messages"] == [{"message": "Hola"}]


def test_fake_dynamodb_table_rejects_unsupported_expressions() -> None:
    """Unsupported expressions fail loudly instead of producing false confidence."""
    table = FakeDynamoDBTable()
    key = {"PK": "SESSION#s1", "SK": "META"}

    with pytest.raises(ValueError, match="Unsupported condition expression"):
        table.update_item(
            Key=key,
            UpdateExpression="SET profile = :profile, expires_at = :ttl",
            ConditionExpression="attribute_exists(profile)",
            ExpressionAttributeValues={":profile": "expert", ":ttl": 1},
        )
    assert table.get_item(Key=key) == {}

    with pytest.raises(ValueError, match="Unsupported update expression"):
        table.update_item(
            Key=key,
            UpdateExpression="REMOVE profile",
            ExpressionAttributeValues={},
        )

    with pytest.raises(ValueError, match="Unsupported key condition expression"):
        table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": "SESSION#s1", ":prefix": "TURN#"},
        )


def test_session_survives_cold_start_with_new_repository_instance() -> None:
    """Persisted state is restored by a new repository instance."""
    table = FakeDynamoDBTable()
    first_repo = DynamoDBStateRepository(table=table)
    first_repo.bind_owner("s1", "client-a")
    first_repo.set_user_profile("s1", "experto")
    first_repo.append_turn(
        "s1",
        ChatTurn(
            question="Q1",
            answer="A1",
            timestamp=datetime.now(timezone.utc),
            source_documents=["panel.pdf"],
        ),
    )
    first_repo.add_token_usage(
        "s1", TokenTotals(input_tokens=2, output_tokens=3, total_tokens=5)
    )

    cold_start_repo = DynamoDBStateRepository(table=table)
    state = cold_start_repo.get_session("s1")

    assert state.owner == "client-a"
    assert state.profile == "experto"
    assert state.turns[0].source_documents == ["panel.pdf"]
    assert state.token_totals.total_tokens == 5


@pytest.mark.parametrize(
    ("turn_count", "max_turns", "expected_questions"),
    [
        (2, 3, ["Q0", "Q1"]),
        (3, 3, ["Q0", "Q1", "Q2"]),
        (5, 3, ["Q2", "Q3", "Q4"]),
    ],
)
def test_get_session_reads_only_latest_turns_in_chronological_order(
    turn_count: int,
    max_turns: int,
    expected_questions: list[str],
) -> None:
    """The repository bounds reads while preserving consumer ordering."""
    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table)
    for index in range(turn_count):
        repository.append_turn(
            "s1",
            ChatTurn(
                question=f"Q{index}",
                answer=f"A{index}",
                timestamp=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
            ),
        )

    state = repository.get_session("s1", max_turns=max_turns)

    assert [turn.question for turn in state.turns] == expected_questions
    assert table.query_calls == [
        {
            "ScanIndexForward": False,
            "Limit": max_turns,
            "ExclusiveStartKey": None,
        }
    ]


def test_get_session_follows_dynamodb_pagination() -> None:
    """The repository follows continuation keys until the turn limit is reached."""
    table = FakeDynamoDBTable(query_page_size=2)
    repository = DynamoDBStateRepository(table=table)
    for index in range(5):
        repository.append_turn(
            "s1",
            ChatTurn(
                question=f"Q{index}",
                answer=f"A{index}",
                timestamp=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
            ),
        )

    state = repository.get_session("s1", max_turns=3)

    assert [turn.question for turn in state.turns] == ["Q2", "Q3", "Q4"]
    assert [call["Limit"] for call in table.query_calls] == [3, 1]
    assert table.query_calls[1]["ExclusiveStartKey"] is not None


@pytest.mark.parametrize("max_turns", [0, -1])
def test_get_session_rejects_non_positive_turn_limit(max_turns: int) -> None:
    """Invalid limits fail before issuing a DynamoDB query."""
    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table)

    with pytest.raises(ValueError, match="max_turns must be greater than zero"):
        repository.get_session("s1", max_turns=max_turns)

    assert table.query_calls == []


def test_bind_owner_allows_same_owner_and_rejects_conflict(
    repository: DynamoDBStateRepository,
) -> None:
    """Conditional owner writes allow idempotency but reject conflicts."""
    repository.bind_owner("s1", "client-a")
    repository.bind_owner("s1", "client-a")

    with pytest.raises(OwnershipConflictError):
        repository.bind_owner("s1", "client-b")


def test_buffer_state_persists_pending_results(
    repository: DynamoDBStateRepository,
) -> None:
    """Durable buffer state supports polling across repository instances."""
    repository.append_buffer_message("s1", "Hola")
    repository.append_buffer_message("s1", "mundo")
    state = repository.get_buffer_state("s1")
    assert [message.message for message in state.messages] == ["Hola", "mundo"]

    repository.clear_buffer_messages("s1")
    repository.set_pending_result("s1", "Hola\nmundo")
    assert repository.pop_pending_result("s1") == "Hola\nmundo"
    assert repository.pop_pending_result("s1") is None


@pytest.mark.parametrize(
    ("setter_name", "popper_name", "attribute"),
    [
        ("set_pending_result", "pop_pending_result", "pending_result"),
        (
            "set_pending_chat_response",
            "pop_pending_chat_response",
            "pending_chat_response",
        ),
    ],
)
@pytest.mark.parametrize("value", ["ready", ""])
def test_pending_strings_are_delivered_exactly_once(
    repository: DynamoDBStateRepository,
    setter_name: str,
    popper_name: str,
    attribute: str,
    value: str,
) -> None:
    """Stored strings, including empty strings, are consumed only once."""
    setter = getattr(repository, setter_name)
    popper = getattr(repository, popper_name)

    assert popper("s1") is None
    setter("s1", value)

    assert popper("s1") == value
    assert popper("s1") is None
    assert getattr(repository.get_buffer_state("s1"), attribute) is None


@pytest.mark.parametrize(
    ("setter_name", "popper_name"),
    [
        ("set_pending_result", "pop_pending_result"),
        ("set_pending_chat_response", "pop_pending_chat_response"),
    ],
)
def test_concurrent_pending_consumers_have_exactly_one_winner(
    repository: DynamoDBStateRepository,
    setter_name: str,
    popper_name: str,
) -> None:
    """A conditional remove gives one winner under concurrent polling."""
    getattr(repository, setter_name)("s1", "ready")
    barrier = Barrier(8)

    def consume() -> str | None:
        barrier.wait()
        return getattr(repository, popper_name)("s1")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: consume(), range(8)))

    assert results.count("ready") == 1
    assert results.count(None) == 7


@pytest.mark.parametrize("processing_mutation", ["set_processing", "clear_processing"])
@pytest.mark.parametrize(
    ("pending_setter", "pending_popper"),
    [
        ("set_pending_result", "pop_pending_result"),
        ("set_pending_chat_response", "pop_pending_chat_response"),
    ],
)
def test_processing_mutation_cannot_erase_concurrent_pending_value(
    processing_mutation: str,
    pending_setter: str,
    pending_popper: str,
) -> None:
    """Set/clear processing preserve pending data written during the mutation."""
    table = ProcessingInterleavingTable()
    repository = DynamoDBStateRepository(table=table)
    repository.append_buffer_message("s1", "keep me")
    if processing_mutation == "clear_processing":
        repository.set_processing("s1")

    run_paused_buffer_mutation(
        table,
        lambda: getattr(repository, processing_mutation)("s1"),
        lambda: getattr(repository, pending_setter)("s1", "pending"),
    )

    state = repository.get_buffer_state("s1")
    assert [message.message for message in state.messages] == ["keep me"]
    assert getattr(repository, pending_popper)("s1") == "pending"


def test_clear_processing_cannot_reinsert_a_consumed_chat_response() -> None:
    """A stale processing clear cannot resurrect a response after its winner."""
    table = ProcessingInterleavingTable()
    repository = DynamoDBStateRepository(table=table)
    repository.set_processing("s1")
    repository.set_pending_chat_response("s1", "ready")
    first_result: list[str | None] = []

    run_paused_buffer_mutation(
        table,
        lambda: repository.clear_processing("s1"),
        lambda: first_result.append(repository.pop_pending_chat_response("s1")),
    )

    assert first_result == ["ready"]
    assert repository.pop_pending_chat_response("s1") is None


@pytest.mark.parametrize("message_mutation", ["append", "clear"])
def test_message_mutation_cannot_reinsert_consumed_chat_response(
    message_mutation: str,
) -> None:
    """An append/clear snapshot cannot resurrect a response after its winner."""
    table = MessageInterleavingTable()
    repository = DynamoDBStateRepository(table=table)
    repository.append_buffer_message("s1", "existing")
    repository.set_processing("s1")
    repository.set_pending_result("s1", "keep result")
    repository.set_pending_chat_response("s1", "ready")
    first_result: list[str | None] = []

    def mutation() -> None:
        if message_mutation == "append":
            repository.append_buffer_message("s1", "new")
        else:
            repository.clear_buffer_messages("s1")

    run_paused_buffer_mutation(
        table,
        mutation,
        lambda: first_result.append(repository.pop_pending_chat_response("s1")),
    )

    state = repository.get_buffer_state("s1")
    assert first_result == ["ready"]
    assert repository.pop_pending_chat_response("s1") is None
    assert state.pending_result == "keep result"
    assert [message.message for message in state.messages] == (
        ["existing", "new"] if message_mutation == "append" else []
    )


@pytest.mark.parametrize("message_mutation", ["append", "clear"])
@pytest.mark.parametrize(
    ("pending_setter", "pending_popper"),
    [
        ("set_pending_result", "pop_pending_result"),
        ("set_pending_chat_response", "pop_pending_chat_response"),
    ],
)
def test_message_mutation_preserves_concurrently_set_pending_value(
    message_mutation: str,
    pending_setter: str,
    pending_popper: str,
) -> None:
    """Messages-only updates preserve pending and processing fields."""
    table = MessageInterleavingTable()
    repository = DynamoDBStateRepository(table=table)
    repository.append_buffer_message("s1", "existing")
    repository.set_processing("s1")

    def mutation() -> None:
        if message_mutation == "append":
            repository.append_buffer_message("s1", "new")
        else:
            repository.clear_buffer_messages("s1")

    run_paused_buffer_mutation(
        table,
        mutation,
        lambda: getattr(repository, pending_setter)("s1", "pending"),
    )

    state = repository.get_buffer_state("s1")
    assert state.processing_started_at is not None
    assert getattr(repository, pending_popper)("s1") == "pending"
    assert [message.message for message in state.messages] == (
        ["existing", "new"] if message_mutation == "append" else []
    )


def test_chat_response_winner_removes_processing_marker_and_preserves_other_fields(
    repository: DynamoDBStateRepository,
) -> None:
    """Winning chat consumption jointly removes only response and processing."""
    repository.append_buffer_message("s1", "keep me")
    repository.set_pending_result("s1", "keep result")
    repository.set_processing("s1")
    repository.set_pending_chat_response("s1", "response")

    assert repository.pop_pending_chat_response("s1") == "response"

    state = repository.get_buffer_state("s1")
    assert state.processing_started_at is None
    assert state.pending_result == "keep result"
    assert [message.message for message in state.messages] == ["keep me"]


def test_missing_chat_response_does_not_clear_processing_marker(
    repository: DynamoDBStateRepository,
) -> None:
    """A losing chat poll cannot clear processing without consuming a value."""
    repository.set_processing("s1")

    assert repository.pop_pending_chat_response("s1") is None
    assert repository.get_buffer_state("s1").processing_started_at is not None


def test_historical_null_pending_value_is_absent() -> None:
    """Legacy DynamoDB NULL values are not treated as consumable strings."""
    table = FakeDynamoDBTable()
    table.items[("SESSION#s1", "BUFFER")] = {
        "PK": "SESSION#s1",
        "SK": "BUFFER",
        "pending_result": None,
    }
    repository = DynamoDBStateRepository(table=table)

    assert repository.pop_pending_result("s1") is None
    assert table.items[("SESSION#s1", "BUFFER")]["pending_result"] is None


def test_pending_pop_propagates_non_conditional_client_errors() -> None:
    """Only absence conditions are translated to None."""

    class FailingTable(FakeDynamoDBTable):
        def update_item(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise ClientError(
                {
                    "Error": {
                        "Code": "ProvisionedThroughputExceededException",
                        "Message": "throttled",
                    }
                },
                "UpdateItem",
            )

    repository = DynamoDBStateRepository(table=FailingTable())

    with pytest.raises(ClientError) as exc_info:
        repository.pop_pending_result("s1")

    assert (
        exc_info.value.response["Error"]["Code"]
        == "ProvisionedThroughputExceededException"
    )


def test_append_buffer_message_refreshes_ttl_and_returns_utc_state() -> None:
    """Atomic append returns the new durable state with UTC metadata."""
    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table, buffer_ttl_seconds=600)

    state = repository.append_buffer_message("s1", "Hola")

    item = table.items[("SESSION#s1", "BUFFER")]
    assert item["expires_at"] > int(datetime.now(timezone.utc).timestamp())
    assert state.messages[0].message == "Hola"
    assert state.messages[0].timestamp.tzinfo == timezone.utc


def test_concurrent_buffer_appends_retain_each_message_exactly_once() -> None:
    """Atomic appends do not overwrite a concurrently accepted message."""

    class CoordinatedReadTable(FakeDynamoDBTable):
        """Force legacy read/put writers to observe the same buffer state."""

        def __init__(self) -> None:
            super().__init__()
            self._buffer_read_barrier = Barrier(2)
            self.coordinate_buffer_reads = True

        def get_item(self, Key: dict[str, str]) -> dict[str, Any]:
            response = super().get_item(Key)
            if Key["SK"] == "BUFFER" and self.coordinate_buffer_reads:
                self._buffer_read_barrier.wait(timeout=5)
            return response

    table = CoordinatedReadTable()
    repository = DynamoDBStateRepository(table=table)
    start_barrier = Barrier(2)

    def append(message: str) -> None:
        start_barrier.wait(timeout=5)
        repository.append_buffer_message("s1", message)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append, message) for message in ("Hola", "mundo")]
        for future in futures:
            future.result(timeout=5)

    table.coordinate_buffer_reads = False
    messages = [
        buffered.message for buffered in repository.get_buffer_state("s1").messages
    ]
    assert len(messages) == 2
    assert sorted(messages) == ["Hola", "mundo"]
    assert messages.count("Hola") == 1
    assert messages.count("mundo") == 1


@pytest.mark.parametrize(
    ("pause", "claimed", "remaining"),
    [
        ("before", ["first", "interleaved"], []),
        ("after", ["first"], ["interleaved"]),
    ],
)
def test_atomic_buffer_claim_partitions_deterministic_interleaving(
    pause: str, claimed: list[str], remaining: list[str]
) -> None:
    """Appends on either side of the claim belong to exactly one batch."""
    table = ClaimInterleavingTable(pause)
    repository = DynamoDBStateRepository(table=table)
    repository.append_buffer_message("s1", "first")
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    lease = ProcessingLease(token="owner", expires_at=now + timedelta(minutes=1))
    assert repository.try_acquire_processing_lease("s1", now=now, lease=lease).acquired
    result: list[BufferMessage] = []

    thread = Thread(
        target=lambda: result.extend(
            repository.claim_buffer_messages("s1", lease.token)
        ),
        name="buffer-claim",
    )
    thread.start()
    assert table.claim_reached.wait(timeout=2)
    repository.append_buffer_message("s1", "interleaved")
    table.allow_claim.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert [message.message for message in result] == claimed
    state = repository.get_buffer_state("s1")
    assert [message.message for message in state.messages] == remaining


def test_processing_lease_has_one_winner_and_exact_expiry_takeover(
    repository: DynamoDBStateRepository,
) -> None:
    now = datetime(2026, 7, 29, microsecond=123456, tzinfo=timezone.utc)
    repository.append_buffer_message("s1", "work")
    start = Barrier(2)

    def acquire(token: str):
        start.wait(timeout=5)
        return repository.try_acquire_processing_lease(
            "s1",
            now=now,
            lease=ProcessingLease(token=token, expires_at=now + timedelta(seconds=60)),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(acquire, ("winner-a", "winner-b")))
    assert sorted(result.acquired for result in results) == [False, True]
    winner = next(result.lease for result in results if result.acquired)
    assert winner is not None
    assert winner.expires_at == now + timedelta(seconds=60)
    assert repository.claim_buffer_messages("s1", winner.token)

    replacement = ProcessingLease(
        token="replacement", expires_at=now + timedelta(seconds=120)
    )
    assert not repository.try_acquire_processing_lease(
        "s1", now=winner.expires_at - timedelta(microseconds=1), lease=replacement
    ).acquired
    takeover = repository.try_acquire_processing_lease(
        "s1", now=winner.expires_at, lease=replacement
    )
    assert takeover.acquired and takeover.lease == replacement
    assert repository.claim_buffer_messages("s1", replacement.token)
    assert not repository.complete_processing("s1", winner.token, '"stale"').completed
    assert repository.get_buffer_state("s1").processing_lease == replacement
    assert repository.release_processing_lease("s1", replacement.token).released is True
    assert not repository.release_processing_lease("s1", replacement.token).released


def test_processing_lease_requires_recoverable_work() -> None:
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    lease = ProcessingLease(token="owner", expires_at=now + timedelta(minutes=1))
    valid = [{"message": "work", "timestamp": now.isoformat()}]
    rows = ({}, {"messages": "invalid"}, {"processing_payload": {}})
    rows += (
        {"messages": valid, "processing_payload": {}},
        {"processing_payload": valid, "messages": "invalid"},
        {"messages": []},
    )
    for work in rows:
        table = FakeDynamoDBTable()
        table.put_item(Item={"PK": "SESSION#s1", "SK": "BUFFER", **work})
        repository = DynamoDBStateRepository(table=table)
        assert not repository.try_acquire_processing_lease(
            "s1", now=now, lease=lease
        ).acquired
    repository.append_buffer_message("s1", "later")
    assert repository.get_buffer_state("s1").messages[0].message == "later"


def test_owned_response_is_hidden_until_fenced_terminal_transition() -> None:
    """Polling cannot consume response state while a worker still owns it."""
    repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    lease = ProcessingLease(token="owner", expires_at=now + timedelta(seconds=30))
    repository.append_buffer_message("s1", "work")
    assert repository.try_acquire_processing_lease("s1", now=now, lease=lease).acquired
    assert repository.claim_buffer_messages("s1", lease.token)
    repository.set_pending_chat_response("s1", '"early"')

    assert repository.pop_pending_chat_response_if_unowned("s1") is None
    assert repository.get_buffer_state("s1").pending_chat_response == '"early"'
    successor = ProcessingLease(
        token="next", expires_at=lease.expires_at + timedelta(seconds=30)
    )
    assert repository.try_acquire_processing_lease(
        "s1", now=lease.expires_at, lease=successor
    ).acquired
    assert repository.pop_pending_chat_response_if_unowned("s1") is None
    assert repository.complete_processing("s1", successor.token, '"ready"').completed
    assert repository.pop_pending_chat_response_if_unowned("s1") == '"ready"'
    assert repository.pop_pending_chat_response_if_unowned("s1") is None


def test_expired_orphan_response_is_consumed_and_fences_stale_owner() -> None:
    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table)
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    lease = ProcessingLease(token="orphan", expires_at=now + timedelta(seconds=30))
    repository.append_buffer_message("s1", "work")
    assert repository.try_acquire_processing_lease("s1", now=now, lease=lease).acquired
    assert repository.claim_buffer_messages("s1", lease.token)
    table.items[("SESSION#s1", "BUFFER")].pop("processing_payload")
    repository.set_pending_chat_response("s1", '"ready"')

    assert (
        repository.pop_pending_chat_response_if_unowned(
            "s1", now=lease.expires_at - timedelta(microseconds=1)
        )
        is None
    )
    assert (
        repository.pop_pending_chat_response_if_unowned("s1", now=lease.expires_at)
        == '"ready"'
    )
    assert repository.pop_pending_chat_response_if_unowned("s1") is None
    assert not repository.complete_processing("s1", lease.token, '"stale"').completed
    assert repository.get_buffer_state("s1").processing_lease is None


def test_processing_lease_dtos_reject_incoherent_or_mutable_state() -> None:
    now = datetime.now(timezone.utc)
    lease = ProcessingLease(token="owner", expires_at=now)

    with pytest.raises(ValidationError):
        ProcessingLease(token="", expires_at=now)
    with pytest.raises(ValidationError):
        ProcessingLease(token="owner", expires_at=now.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        ProcessingLeaseResult(acquired=True)
    with pytest.raises(ValidationError):
        lease.token = "replacement"


@pytest.mark.parametrize("missing", ["lease_token", "lease_expires_at"])
def test_processing_lease_recovers_malformed_legacy_state(missing: str) -> None:
    table = FakeDynamoDBTable()
    item = {
        "PK": "SESSION#s1",
        "SK": "BUFFER",
        "lease_token": "legacy",
        "lease_expires_at": 9999999999,
    }
    item.pop(missing)
    table.put_item(Item=item)
    repository = DynamoDBStateRepository(table=table)
    repository.append_buffer_message("s1", "work")
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    lease = ProcessingLease(token="new", expires_at=now + timedelta(seconds=60))

    assert repository.try_acquire_processing_lease("s1", now=now, lease=lease).acquired


def test_buffer_state_without_lease_attributes_maps_as_legacy_state() -> None:
    table = FakeDynamoDBTable()
    table.put_item(Item={"PK": "SESSION#s1", "SK": "BUFFER"})

    state = DynamoDBStateRepository(table=table).get_buffer_state("s1")

    assert state.processing_lease is None


def test_processing_lease_translates_only_conditional_errors() -> None:
    class ErrorTable:
        code = "ConditionalCheckFailedException"

        def update_item(self, **kwargs: Any) -> dict[str, Any]:
            raise ClientError({"Error": {"Code": self.code}}, "UpdateItem")

    table = ErrorTable()
    repository = DynamoDBStateRepository(table=table)
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    lease = ProcessingLease(token="token", expires_at=now + timedelta(seconds=60))
    assert not repository.try_acquire_processing_lease(
        "s1", now=now, lease=lease
    ).acquired
    assert not repository.release_processing_lease("s1", "token").released
    assert not repository.complete_processing("s1", "token", '"ready"').completed
    assert repository.pop_pending_chat_response_if_unowned("s1") is None

    table.code = "ProvisionedThroughputExceededException"
    with pytest.raises(ClientError):
        repository.try_acquire_processing_lease("s1", now=now, lease=lease)
    with pytest.raises(ClientError):
        repository.release_processing_lease("s1", "token")
    with pytest.raises(ClientError):
        repository.complete_processing("s1", "token", '"ready"')
    with pytest.raises(ClientError):
        repository.pop_pending_chat_response_if_unowned("s1")


def test_rate_limit_uses_shared_counter(repository: DynamoDBStateRepository) -> None:
    """Rate counters are shared through the repository table."""
    assert repository.check_rate_limit("client-a", limit=2, window_seconds=60).allowed
    assert repository.check_rate_limit("client-a", limit=2, window_seconds=60).allowed

    denied = repository.check_rate_limit("client-a", limit=2, window_seconds=60)

    assert denied.allowed is False
    assert denied.retry_after_seconds > 0
    assert denied.remaining == 0


def test_dynamodb_keys_include_prefix_and_ttl() -> None:
    """DynamoDB items use prefixed PK/SK keys and TTL attributes."""
    table = FakeDynamoDBTable()
    repo = DynamoDBStateRepository(table=table, key_prefix="local-staging")
    repo.bind_owner("s1", "client-a")

    item = table.items[("local-staging#SESSION#s1", "META")]
    assert item["owner"] == "client-a"
    assert isinstance(item["expires_at"], int)
