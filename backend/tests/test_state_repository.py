"""Tests for Lambda-safe state repository contracts and DynamoDB behavior."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Barrier, RLock
from typing import Any

import pytest
from botocore.exceptions import ClientError

from backend.app.dynamodb_state_repository import DynamoDBStateRepository
from backend.app.state_repository import (
    ChatTurn,
    OwnershipConflictError,
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
        if ReturnValues not in (None, "ALL_NEW"):
            raise ValueError(f"Unsupported return values: {ReturnValues}")

        key = (Key["PK"], Key["SK"])
        names = ExpressionAttributeNames or {}
        expression = " ".join(UpdateExpression.split())

        with self._lock:
            item = deepcopy(
                self.items.get(key, {"PK": Key["PK"], "SK": Key["SK"]})
            )
            self._evaluate_condition(
                item, ConditionExpression, names, ExpressionAttributeValues
            )
            self._apply_update(item, expression, names, ExpressionAttributeValues)
            self.items[key] = deepcopy(item)
            return {"Attributes": deepcopy(item)} if ReturnValues == "ALL_NEW" else {}

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
        if expression != "attribute_not_exists(#owner) OR #owner = :owner":
            raise ValueError(f"Unsupported condition expression: {expression}")

        owner_name = names.get("#owner")
        if owner_name != "owner":
            raise ValueError("Unsupported owner attribute mapping")
        current_owner = item.get(owner_name)
        if current_owner is not None and current_owner != values[":owner"]:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "owner mismatch",
                    }
                },
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
