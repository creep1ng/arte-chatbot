import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError

from backend.app.auth import verify_api_key
from backend.app.llm_client import LLMServiceError
from backend.app.request_deadline import RequestDeadline, RequestDeadlineExceeded
from backend.app.state_repository import ProcessingLease
import backend.main as backend_main
from backend.tests.conftest import make_llm_response

app = backend_main.app
client = TestClient(app)
LLM_CALL = "backend.main.llm_client.get_llm_response_with_tools"


def _deadline(*, clock=time.monotonic, total=0.08, cleanup=0.03) -> RequestDeadline:
    return RequestDeadline.from_budget(total, 0.01, cleanup, 0.001, clock=clock)


def _tool_call() -> dict[str, object]:
    function = {
        "name": "buscar_producto",
        "arguments": json.dumps({"categoria": "paneles"}),
    }
    return {"id": "1", "function": function}


def _sdk_timeout(**_: object) -> None:
    time.sleep(0.005)
    raise LLMServiceError("SDK timeout") from APITimeoutError(MagicMock())


def _post(deadline: RequestDeadline, llm: object) -> tuple[object, MagicMock]:
    with (
        patch("backend.main._request_deadline", return_value=deadline),
        patch(LLM_CALL, side_effect=llm) as call,
    ):
        return client.post("/chat", json={"message": "paneles"}), call


@pytest.fixture(autouse=True)
def _authenticated() -> None:
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[verify_api_key] = lambda: "deadline-key"
    yield
    app.dependency_overrides = previous


def test_slow_first_call_returns_controlled_response_before_hard_at() -> None:
    deadline = _deadline(total=0.5, cleanup=0.2)
    response, _ = _post(deadline, _sdk_timeout)
    assert time.monotonic() < deadline.hard_at
    assert response.json()["intent_type"] == "request_timeout"
    assert response.json()["source_documents"] == []


def test_completed_iteration_refuses_the_next() -> None:
    now = [0.0]

    def complete_tool(**_: object) -> str:
        now[0] = 0.05
        return "done"

    with patch(
        "backend.main._process_buscar_producto", side_effect=complete_tool
    ) as tool:
        response, llm = _post(
            _deadline(clock=lambda: now[0]),
            lambda **_: make_llm_response(
                text="", tool_calls=[_tool_call()], input_tokens=7
            ),
        )
    data = response.json()
    assert (data["intent_type"], data["input_tokens"]) == ("request_timeout", 7)
    assert llm.call_count == tool.call_count == 1 and data["source_documents"] == []


def test_slow_product_tool_propagates_allocation_and_degrades() -> None:
    seen: list[float] = []

    def slow_catalog(*, timeout_seconds: float) -> None:
        seen.append(timeout_seconds)
        time.sleep(timeout_seconds + 0.001)

    with patch("backend.main.get_catalog", side_effect=slow_catalog):
        response, _ = _post(
            _deadline(total=0.5, cleanup=0.2),
            lambda **_: make_llm_response(text="", tool_calls=[_tool_call()]),
        )
    assert response.json()["intent_type"] == "request_timeout"
    assert 0 < seen[0] <= 0.3


@pytest.mark.parametrize("operation", ["s3_download", "file_upload", "file_llm"])
@pytest.mark.asyncio
async def test_slow_datasheet_paths_are_wall_clock_bounded(operation: str) -> None:
    with pytest.raises(RequestDeadlineExceeded) as raised:
        await backend_main._bounded(_deadline(), operation, lambda: time.sleep(0.041))
    assert raised.value.operation == operation


@pytest.mark.parametrize(
    "effect,outcome",
    [(None, "success"), (RuntimeError("private"), "failure"), ("slow", "timeout")],
)
@pytest.mark.asyncio
async def test_cleanup_outcomes_are_bounded_and_observable(
    effect: object, outcome: str, caplog: pytest.LogCaptureFixture
) -> None:
    side_effect = (
        (lambda *args, **kwargs: time.sleep(0.04)) if effect == "slow" else effect
    )
    delete = MagicMock(side_effect=side_effect)
    started = time.monotonic()
    await backend_main._cleanup_file(
        MagicMock(delete_file=delete), "secret-file", _deadline(), "request-1"
    )
    assert 0 < delete.call_args.kwargs["timeout_seconds"] == pytest.approx(0.03)
    assert time.monotonic() - started < 0.04 and f"outcome={outcome}" in caplog.text
    assert "secret-file" not in caplog.text and "private" not in caplog.text


@pytest.mark.asyncio
async def test_buffered_path_stores_controlled_timeout() -> None:
    lease = ProcessingLease(token="lease", expires_at=datetime.now(timezone.utc) + timedelta(seconds=1))  # fmt: skip
    stored = MagicMock()
    deadline = _deadline(total=0.5, cleanup=0.2)
    with (
        patch("backend.main._request_deadline", return_value=deadline),
        patch(LLM_CALL, side_effect=_sdk_timeout),
        patch("backend.main.set_pending_chat_response", stored),
        patch("backend.main.release_processing_lease"),
    ):
        await backend_main._on_buffer_window_expired("buffer-session", "paneles", lease)
    data = json.loads(stored.call_args.args[1])
    outcome = data["intent_type"], data["escalate"], data["input_tokens"]
    assert outcome == ("request_timeout", True, 0)
    assert data["source_documents"] == [] and data["num_sources"] == 0


def test_lambda_cap_local_fallback_and_auth_short_circuit() -> None:
    context = MagicMock()
    context.get_remaining_time_in_millis.return_value = 8_000
    lambda_deadline, local_deadline = (
        backend_main._request_deadline({"aws.context": context}),
        backend_main._request_deadline(),
    )
    assert lambda_deadline.hard_at - lambda_deadline.started_at == pytest.approx(6.0)
    assert local_deadline.hard_at - local_deadline.started_at == pytest.approx(23.0)
    app.dependency_overrides.pop(verify_api_key)
    with patch("backend.main._request_deadline") as builder:
        response = client.post("/chat", json={"message": "paneles"})
    assert response.status_code in {401, 403}
    builder.assert_not_called()
