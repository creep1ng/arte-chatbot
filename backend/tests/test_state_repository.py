"""Tests for Lambda-safe state repository contracts and DynamoDB behavior."""

from datetime import datetime, timezone
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

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def get_item(self, Key: dict[str, str]) -> dict[str, Any]:
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": item.copy()} if item else {}

    def put_item(self, Item: dict[str, Any]) -> None:
        self.items[(Item["PK"], Item["SK"])] = Item.copy()

    def query(
        self,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ScanIndexForward: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        del KeyConditionExpression
        prefix = ExpressionAttributeValues[":prefix"]
        pk = ExpressionAttributeValues[":pk"]
        items = [
            item.copy()
            for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and item_sk.startswith(prefix)
        ]
        return {"Items": sorted(items, key=lambda item: item["SK"])}

    def update_item(
        self,
        Key: dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, Any],
        ExpressionAttributeNames: dict[str, str] | None = None,
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
    ) -> dict[str, Any]:
        del ReturnValues
        key = (Key["PK"], Key["SK"])
        item = self.items.setdefault(key, {"PK": Key["PK"], "SK": Key["SK"]})
        names = ExpressionAttributeNames or {}

        if ConditionExpression and "owner" in names.values():
            current_owner = item.get("owner")
            new_owner = ExpressionAttributeValues[":owner"]
            if current_owner is not None and current_owner != new_owner:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ConditionalCheckFailedException",
                            "Message": "owner mismatch",
                        }
                    },
                    "UpdateItem",
                )

        if "ADD" in UpdateExpression:
            item["count" if "#count" in UpdateExpression else "input_tokens"] = int(
                item.get("count" if "#count" in UpdateExpression else "input_tokens", 0)
            ) + int(
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
        else:
            if ":owner" in ExpressionAttributeValues:
                item["owner"] = ExpressionAttributeValues[":owner"]
            if ":profile" in ExpressionAttributeValues:
                item["profile"] = ExpressionAttributeValues[":profile"]
            if ":ttl" in ExpressionAttributeValues:
                item["expires_at"] = ExpressionAttributeValues[":ttl"]

        return {"Attributes": item.copy()}


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


def test_chatwoot_conversation_mapping_survives_repository_instances() -> None:
    """Chatwoot conversation/session mappings are durable and bidirectional."""
    table = FakeDynamoDBTable()
    first_repo = DynamoDBStateRepository(table=table, key_prefix="prod")
    first_repo.map_chatwoot_conversation("42", "session-42", account_id=7)

    cold_start_repo = DynamoDBStateRepository(table=table, key_prefix="prod")

    assert cold_start_repo.get_chatwoot_session_id("42", account_id=7) == "session-42"
    assert cold_start_repo.get_chatwoot_conversation_id("session-42") == "42"


def test_chatwoot_message_idempotency_key_is_durable() -> None:
    """Processed Chatwoot message IDs are persisted for webhook retries."""
    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table)

    assert repository.has_processed_chatwoot_message("101") is False
    assert repository.mark_chatwoot_message_processed("101") is True
    assert repository.has_processed_chatwoot_message("101") is True
    assert repository.mark_chatwoot_message_processed("101") is False
