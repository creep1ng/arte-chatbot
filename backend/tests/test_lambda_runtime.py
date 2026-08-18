"""Tests for the Lambda/Mangum runtime adapter."""

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Optional

import pytest

from backend.app.auth import verify_api_key
from backend.app.config import settings
from backend.tests.conftest import make_llm_response


class LambdaContext:
    """Minimal Lambda context accepted by Mangum during tests."""

    function_name = "arte-chatbot-test"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    memory_limit_in_mb = 512
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/arte-chatbot-test"
    log_stream_name = "test-stream"

    def get_remaining_time_in_millis(self) -> int:
        """Return a stable timeout budget for the adapter."""
        return 30_000


class FakeLLMClient:
    """LLM test double that returns a normal chat response without tool calls."""

    model = "test-model"

    def get_llm_response_with_tools(self, **_: Any) -> Any:
        """Return a simple FAQ response."""
        return make_llm_response(text="[INTENT: FAQ] Lambda response")


class UnusedClient:
    """Dependency placeholder for code paths not reached by these tests."""


def _http_api_v2_event(
    method: str,
    path: str,
    *,
    body: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    raw_body = json.dumps(body) if body is not None else None
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("content-type", "application/json")
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": request_headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "test-api",
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "example",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "test-request",
            "routeKey": f"{method} {path}",
            "stage": "$default",
            "time": "21/Jun/2026:19:00:00 +0000",
            "timeEpoch": 1_782_069_600_000,
        },
        "isBase64Encoded": False,
        "body": raw_body,
    }


def _decode_response_body(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("body") or "{}"
    if response.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _restore_event_loop(previous_loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Restore a usable event loop after tests that intentionally clear it."""
    current_loop: Optional[asyncio.AbstractEventLoop]
    try:
        current_loop = asyncio.get_event_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is not None and current_loop is not previous_loop:
        current_loop.close()

    asyncio.set_event_loop(previous_loop or asyncio.new_event_loop())


@pytest.fixture(autouse=True)
def _lambda_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_API_KEY", "lambda-test-key")
    monkeypatch.setenv("GREETING_ENABLED", "false")
    monkeypatch.setenv("MULTI_MESSAGE_BUFFER_ENABLED", "false")
    monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
    monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")
    settings.reset()

    from backend.main import app

    monkeypatch.setattr(app, "dependency_overrides", {})
    yield
    settings.reset()


def test_mangum_health_http_api_event() -> None:
    """HTTP API events reach /health through the Lambda handler."""
    from backend.main import handler

    response = handler(_http_api_v2_event("GET", "/health"), LambdaContext())

    assert response["statusCode"] == 200
    assert _decode_response_body(response)["status"] == "healthy"


def test_mangum_handler_recovers_when_current_event_loop_is_missing() -> None:
    """Lambda handler creates an event loop if another test cleared it."""
    from backend.main import handler

    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    asyncio.set_event_loop(None)

    try:
        response = handler(_http_api_v2_event("GET", "/health"), LambdaContext())
    finally:
        _restore_event_loop(previous_loop)

    assert response["statusCode"] == 200
    assert _decode_response_body(response)["status"] == "healthy"


def test_mangum_chat_rejects_missing_api_key_before_processing() -> None:
    """Unauthorized /chat requests are rejected by FastAPI auth in Lambda."""
    from backend.main import handler

    response = handler(
        _http_api_v2_event("POST", "/chat", body={"message": "Hola"}),
        LambdaContext(),
    )

    assert response["statusCode"] == 401
    assert _decode_response_body(response)["detail"] == "Missing API key"


def test_mangum_chat_http_api_event() -> None:
    """Authenticated /chat requests work through Mangum HTTP API events."""
    from backend.main import (
        app,
        get_file_inputs_client,
        get_llm_client,
        get_s3_client,
        handler,
    )

    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    app.dependency_overrides[get_s3_client] = lambda: UnusedClient()
    app.dependency_overrides[get_file_inputs_client] = lambda: UnusedClient()

    response = handler(
        _http_api_v2_event(
            "POST",
            "/chat",
            body={"message": "Hola"},
            headers={"x-api-key": "lambda-test-key"},
        ),
        LambdaContext(),
    )

    body = _decode_response_body(response)
    assert response["statusCode"] == 200
    assert body["response"] == "Lambda response"
    assert body["session_id"]


def test_chat_processes_owned_batch_from_stale_precount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrent overflow result is processed even after a zero pre-count."""
    from backend.app.message_buffer import OwnedBufferedMessage
    from backend.app.state_repository import ProcessingLease
    from backend.main import ChatResponse, handler

    monkeypatch.setenv("MULTI_MESSAGE_BUFFER_ENABLED", "true")
    settings.reset()
    lease = ProcessingLease(
        token="concurrent-overflow",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    owned = OwnedBufferedMessage(message="first\nsecond", lease=lease)
    processed: list[str] = []
    released: list[str] = []

    async def overflow(*_: Any, **__: Any) -> OwnedBufferedMessage:
        return owned

    async def process(**kwargs: Any) -> ChatResponse:
        processed.append(kwargs["message"])
        return ChatResponse(response="processed", session_id=kwargs["session_id"])

    def reject_schedule(*_: Any, **__: Any) -> None:
        pytest.fail("owned batches must not schedule a second flush")

    monkeypatch.setattr("backend.main.get_buffer_count", lambda _: 0)
    monkeypatch.setattr("backend.main.add_to_buffer", overflow)
    monkeypatch.setattr("backend.main.schedule_flush", reject_schedule)
    monkeypatch.setattr("backend.main._process_chat_message", process)
    monkeypatch.setattr(
        "backend.main.release_processing_lease",
        lambda _session_id, token: released.append(token),
    )

    response = handler(
        _http_api_v2_event(
            "POST",
            "/chat",
            body={"message": "second"},
            headers={"x-api-key": "lambda-test-key"},
        ),
        LambdaContext(),
    )

    assert response["statusCode"] == 200
    assert processed == ["first\nsecond"]
    assert released == [lease.token]


def test_mangum_buffer_result_http_api_event() -> None:
    """Buffered polling responses are returned through Mangum."""
    from backend.app.message_buffer import set_pending_chat_response
    from backend.app.session import session_manager
    from backend.main import handler

    session_manager.bind_session("lambda-buffer-session", "lambda-principal")
    set_pending_chat_response("lambda-buffer-session", '{"response":"ready"}')

    from backend.app.auth import api_key_principal

    session_manager.bind_session(
        "lambda-buffer-session", api_key_principal("lambda-test-key")
    )

    response = handler(
        _http_api_v2_event(
            "GET",
            "/buffer-result/lambda-buffer-session",
            headers={"x-api-key": "lambda-test-key"},
        ),
        LambdaContext(),
    )

    body = _decode_response_body(response)
    assert response["statusCode"] == 200
    assert body["status"] == "ready"
    assert body["result"] == '{"response":"ready"}'


def test_buffer_result_processes_due_repository_buffer_without_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lambda-safe polling processes durable buffers after the debounce window."""
    from fastapi.testclient import TestClient

    from backend.app import message_buffer
    from backend.app.auth import api_key_principal
    from backend.app.dynamodb_state_repository import DynamoDBStateRepository
    from backend.app.session import session_manager
    from backend.main import ChatResponse, app
    from backend.tests.test_state_repository import FakeDynamoDBTable

    monkeypatch.setenv("BUFFER_WINDOW_SECONDS", "1")
    settings.reset()

    table = FakeDynamoDBTable()
    repository = DynamoDBStateRepository(table=table)
    session_id = "durable-buffer-session"
    principal = api_key_principal("lambda-test-key")

    session_manager.set_state_repository(repository)
    message_buffer.set_state_repository(repository)
    repository.bind_owner(session_id, principal)
    repository.append_buffer_message(session_id, "Hola")
    repository.append_buffer_message(session_id, "paneles")
    buffer_item = table.items[("SESSION#durable-buffer-session", "BUFFER")]
    old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    for message in buffer_item["messages"]:
        message["timestamp"] = old_timestamp

    async def fake_process_chat_message(**kwargs: Any) -> ChatResponse:
        assert kwargs["session_id"] == session_id
        assert kwargs["message"] == "Hola\npaneles"
        return ChatResponse(response="poll ready", session_id=session_id)

    monkeypatch.setattr(
        "backend.main._process_chat_message",
        fake_process_chat_message,
    )

    try:
        client = TestClient(app)
        response = client.get(
            f"/buffer-result/{session_id}",
            headers={"x-api-key": "lambda-test-key"},
        )
    finally:
        session_manager.set_state_repository(None)
        message_buffer.set_state_repository(None)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ready"
    assert '"response":"poll ready"' in body["result"]
    assert repository.get_buffer_state(session_id).messages == []


@pytest.mark.asyncio
async def test_two_due_buffer_pollers_run_one_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A processing lease makes competing Lambda pollers return one result."""
    from backend.app import message_buffer
    from backend.app.auth import api_key_principal
    from backend.app.dynamodb_state_repository import DynamoDBStateRepository
    from backend.app.session import session_manager
    from backend.main import ChatResponse, get_buffer_result
    from backend.tests.test_state_repository import FakeDynamoDBTable

    monkeypatch.setenv("BUFFER_WINDOW_SECONDS", "1")
    settings.reset()
    repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
    session_id = "competing-pollers"
    principal = api_key_principal("lambda-test-key")
    processor_started = asyncio.Event()
    finish_processing = asyncio.Event()
    processor_calls = 0

    session_manager.set_state_repository(repository)
    message_buffer.set_state_repository(repository)
    repository.bind_owner(session_id, principal)
    repository.append_buffer_message(session_id, "Hola")
    state = repository.get_buffer_state(session_id)
    old_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
    table_item = repository._table.items[(f"SESSION#{session_id}", "BUFFER")]
    table_item["messages"][-1]["timestamp"] = old_timestamp.isoformat()

    async def fake_process_chat_message(**_: Any) -> ChatResponse:
        nonlocal processor_calls
        processor_calls += 1
        processor_started.set()
        await finish_processing.wait()
        return ChatResponse(response="ready", session_id=session_id)

    monkeypatch.setattr("backend.main._process_chat_message", fake_process_chat_message)
    try:
        owner_poll = asyncio.create_task(
            get_buffer_result(session_id, "lambda-test-key")
        )
        await processor_started.wait()
        competing_poll = await get_buffer_result(session_id, "lambda-test-key")
        finish_processing.set()
        owner_result = await owner_poll
    finally:
        session_manager.set_state_repository(None)
        message_buffer.set_state_repository(None)

    assert state.messages
    assert competing_poll.status == "pending"
    assert owner_result.status == "ready"
    assert processor_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_buffer_callback_always_releases_its_lease(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    """Callback errors and cancellation cannot leak processing ownership."""
    from backend.app import message_buffer
    from backend.main import _on_buffer_window_expired

    session_id = f"callback-{error_type.__name__}"
    acquired = message_buffer.acquire_processing_lease(session_id)
    assert acquired.lease is not None

    async def fail_processing(**_: Any) -> None:
        raise error_type("processing interrupted")

    monkeypatch.setattr("backend.main._process_chat_message", fail_processing)
    if issubclass(error_type, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await _on_buffer_window_expired(session_id, "Hola", acquired.lease)
    else:
        await _on_buffer_window_expired(session_id, "Hola", acquired.lease)

    assert not message_buffer.has_active_processing_lease(session_id)


def test_auth_override_is_not_required_for_lambda_auth() -> None:
    """The runtime tests exercise real API-key auth, not dependency overrides."""
    from backend.main import app

    assert verify_api_key not in app.dependency_overrides
