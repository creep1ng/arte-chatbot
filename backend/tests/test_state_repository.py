"""Tests for Lambda-safe state repository contracts and DynamoDB behavior."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Barrier, Event, RLock, Thread, current_thread
from typing import Any, Callable

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
        if KeyConditionExpression != "PK = :pk AND begins_with(SK, :prefix)":
            raise NotImplementedError(KeyConditionExpression)
        with self._lock:
            self.query_calls.append(
                {
                    "ScanIndexForward": ScanIndexForward,
                    "Limit": Limit,
                    "ExclusiveStartKey": ExclusiveStartKey,
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
            page_limit = min(Limit or self.query_page_size, self.query_page_size)
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
        ExpressionAttributeValues: dict[str, Any] | None = None,
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        key = (Key["PK"], Key["SK"])
        names = ExpressionAttributeNames or {}
        ExpressionAttributeValues = ExpressionAttributeValues or {}
        with self._lock:
            item = deepcopy(self.items.get(key, {"PK": Key["PK"], "SK": Key["SK"]}))
            old_item = deepcopy(item)

            if ConditionExpression == "attribute_type(#pending, :string_type)":
                pending_attribute = names["#pending"]
                if ExpressionAttributeValues[":string_type"] != "S" or not isinstance(
                    item.get(pending_attribute), str
                ):
                    self._raise_conditional_failure("pending value is not a string")
            elif ConditionExpression and "owner" in names.values():
                current_owner = item.get("owner")
                new_owner = ExpressionAttributeValues[":owner"]
                if current_owner is not None and current_owner != new_owner:
                    self._raise_conditional_failure("owner mismatch")
            elif ConditionExpression is not None:
                raise NotImplementedError(ConditionExpression)

            if UpdateExpression.startswith("REMOVE "):
                for placeholder in UpdateExpression.removeprefix("REMOVE ").split(", "):
                    item.pop(names.get(placeholder, placeholder), None)
            elif "ADD" in UpdateExpression:
                counter = "count" if "#count" in UpdateExpression else "input_tokens"
                item[counter] = int(item.get(counter, 0)) + int(
                    ExpressionAttributeValues.get(
                        ":one", ExpressionAttributeValues.get(":input", 0)
                    )
                )
                if ":output" in ExpressionAttributeValues:
                    item["output_tokens"] = int(item.get("output_tokens", 0)) + int(
                        ExpressionAttributeValues[":output"]
                    )
                    item["total_tokens"] = int(item.get("total_tokens", 0)) + int(
                        ExpressionAttributeValues[":total"]
                    )
                if ":started" in ExpressionAttributeValues:
                    item["window_started_at"] = ExpressionAttributeValues[":started"]
                    item["window_seconds"] = ExpressionAttributeValues[":window"]
                item["expires_at"] = ExpressionAttributeValues[":ttl"]
            elif UpdateExpression.startswith("SET "):
                set_expression = UpdateExpression.removeprefix("SET ")
                remove_expression: str | None = None
                if " REMOVE " in set_expression:
                    set_expression, remove_expression = set_expression.split(
                        " REMOVE ", maxsplit=1
                    )
                assignments = set_expression.split(", ")
                for assignment in assignments:
                    attribute, value_name = assignment.split(" = ")
                    item[names.get(attribute, attribute)] = deepcopy(
                        ExpressionAttributeValues[value_name]
                    )
                if remove_expression is not None:
                    for placeholder in remove_expression.split(", "):
                        item.pop(names.get(placeholder, placeholder), None)
            else:
                raise NotImplementedError(UpdateExpression)

            self.items[key] = item
            if ReturnValues == "ALL_OLD":
                return {"Attributes": old_item}
            if ReturnValues in (None, "ALL_NEW"):
                return {"Attributes": deepcopy(item)}
            raise NotImplementedError(ReturnValues)

    @staticmethod
    def _raise_conditional_failure(message: str) -> None:
        raise ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": message,
                }
            },
            "UpdateItem",
        )


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

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        update_expression = str(kwargs["UpdateExpression"])
        is_processing_update = (
            update_expression.startswith("SET processing_started_at")
            or "REMOVE processing_started_at" in update_expression
        )
        if current_thread().name == "processing-race" and is_processing_update:
            self.processing_mutation_started.set()
            assert self.allow_processing_mutation.wait(timeout=2)
        return super().update_item(**kwargs)


class MessageInterleavingTable(ProcessingInterleavingTable):
    """Pause a message mutation after its read or before its field update."""

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        update_expression = str(kwargs["UpdateExpression"])
        if (
            current_thread().name == "processing-race"
            and update_expression.startswith("SET messages = :messages")
        ):
            self.processing_mutation_started.set()
            assert self.allow_processing_mutation.wait(timeout=2)
        return super().update_item(**kwargs)


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
