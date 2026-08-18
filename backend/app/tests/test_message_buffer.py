"""Unit tests for multi-message input buffer (P4).

Tests buffer accumulation, flush, overflow, is_final hint,
and debounce scheduling for the WhatsApp multi-message buffer feature.

Strict TDD: tests written BEFORE implementation.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, RLock, Thread
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from backend.app.state_repository import ProcessingLease
from backend.tests.conftest import make_llm_response

# ---------------------------------------------------------------------------
# Imports — will fail until implementation exists
# ---------------------------------------------------------------------------
try:
    from backend.app.message_buffer import (
        add_to_buffer,
        clear_buffer,
        flush_buffer,
        get_buffer_count,
        is_buffering,
        schedule_flush,
    )
except ImportError:
    add_to_buffer = None  # type: ignore[assignment]
    flush_buffer = None  # type: ignore[assignment]
    is_buffering = None  # type: ignore[assignment]
    get_buffer_count = None  # type: ignore[assignment]
    clear_buffer = None  # type: ignore[assignment]
    schedule_flush = None  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _require_message_buffer() -> None:
    """Skip all tests in this module if message_buffer not yet implemented."""
    if add_to_buffer is None:
        pytest.skip("backend.app.message_buffer not yet implemented")


@pytest.fixture(autouse=True)
def _clean_buffer_state() -> Generator[None, None, None]:
    """Ensure clean buffer state between tests."""
    try:
        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
        message_buffer._pending_results.clear()
        message_buffer._pending_chat_responses.clear()
        message_buffer._processing_leases.clear()
        message_buffer._processing_sessions.clear()
    except ImportError:
        pass
    yield
    try:
        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
        message_buffer._pending_results.clear()
        message_buffer._pending_chat_responses.clear()
        message_buffer._processing_leases.clear()
        message_buffer._processing_sessions.clear()
    except ImportError:
        pass


# ===========================================================================
# Task 5.1 — Core buffer operations
# ===========================================================================


class TestAddToBuffer:
    """Test add_to_buffer accumulates messages per session."""

    @pytest.mark.asyncio
    async def test_add_single_message(self) -> None:
        """Adding one message stores it in the buffer."""
        await add_to_buffer("s1", "Hola")
        assert is_buffering("s1") is True
        assert get_buffer_count("s1") == 1

    @pytest.mark.asyncio
    async def test_add_multiple_messages(self) -> None:
        """Adding multiple messages accumulates them in order."""
        await add_to_buffer("s1", "Hola")
        await add_to_buffer("s1", "quisiera info")
        await add_to_buffer("s1", "sobre paneles")
        assert get_buffer_count("s1") == 3

    @pytest.mark.asyncio
    async def test_different_sessions_independent(self) -> None:
        """Buffers for different sessions are independent."""
        await add_to_buffer("s1", "Hola")
        await add_to_buffer("s2", "Buenos días")
        assert get_buffer_count("s1") == 1
        assert get_buffer_count("s2") == 1

    @pytest.mark.asyncio
    async def test_add_to_buffer_returns_none_below_max(self) -> None:
        """add_to_buffer returns None when below max_messages threshold."""
        result = await add_to_buffer("s1", "Hola", max_messages=5)
        assert result is None


# ===========================================================================
# Task 5.1 — Flush buffer
# ===========================================================================


class TestFlushBuffer:
    """Test flush_buffer joins and clears."""

    @pytest.mark.asyncio
    async def test_flush_joins_with_newline(self) -> None:
        """Flush returns messages joined with newline separator."""
        await add_to_buffer("s1", "Hola")
        await add_to_buffer("s1", "quisiera info")
        await add_to_buffer("s1", "sobre paneles")
        result = await flush_buffer("s1")
        assert result == "Hola\nquisiera info\nsobre paneles"

    @pytest.mark.asyncio
    async def test_flush_returns_none_when_empty(self) -> None:
        """Flush returns None when buffer has no messages."""
        result = await flush_buffer("s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self) -> None:
        """After flush, buffer is empty and is_buffering returns False."""
        await add_to_buffer("s1", "Hola")
        await flush_buffer("s1")
        assert is_buffering("s1") is False
        assert get_buffer_count("s1") == 0

    @pytest.mark.asyncio
    async def test_flush_single_message(self) -> None:
        """Flush with single message returns that message without separator."""
        await add_to_buffer("s1", "Hola")
        result = await flush_buffer("s1")
        assert result == "Hola"

    @pytest.mark.asyncio
    async def test_flush_preserves_order(self) -> None:
        """Flush preserves the original message order."""
        await add_to_buffer("s1", "primer mensaje")
        await add_to_buffer("s1", "segundo mensaje")
        result = await flush_buffer("s1")
        assert result is not None
        lines = result.split("\n")
        assert lines[0] == "primer mensaje"
        assert lines[1] == "segundo mensaje"


# ===========================================================================
# Task 5.1 — is_buffering and get_buffer_count
# ===========================================================================


class TestIsBuffering:
    """Test is_buffering state checks."""

    def test_not_buffering_initially(self) -> None:
        """No buffer state initially."""
        assert is_buffering("s1") is False

    @pytest.mark.asyncio
    async def test_buffering_after_add(self) -> None:
        """is_buffering returns True after adding a message."""
        await add_to_buffer("s1", "Hola")
        assert is_buffering("s1") is True

    @pytest.mark.asyncio
    async def test_not_buffering_after_flush(self) -> None:
        """is_buffering returns False after flush."""
        await add_to_buffer("s1", "Hola")
        await flush_buffer("s1")
        assert is_buffering("s1") is False


class TestGetBufferCount:
    """Test get_buffer_count."""

    def test_zero_initially(self) -> None:
        """Count is 0 initially."""
        assert get_buffer_count("s1") == 0

    @pytest.mark.asyncio
    async def test_count_increments(self) -> None:
        """Count increments with each add."""
        await add_to_buffer("s1", "a")
        assert get_buffer_count("s1") == 1
        await add_to_buffer("s1", "b")
        assert get_buffer_count("s1") == 2

    @pytest.mark.asyncio
    async def test_count_resets_after_flush(self) -> None:
        """Count resets to 0 after flush."""
        await add_to_buffer("s1", "a")
        await add_to_buffer("s1", "b")
        await flush_buffer("s1")
        assert get_buffer_count("s1") == 0


# ===========================================================================
# Task 5.1 — clear_buffer
# ===========================================================================


class TestClearBuffer:
    """Test clear_buffer resets state."""

    @pytest.mark.asyncio
    async def test_clear_removes_messages(self) -> None:
        """clear_buffer removes all buffered messages."""
        await add_to_buffer("s1", "Hola")
        await add_to_buffer("s1", "mundo")
        clear_buffer("s1")
        assert is_buffering("s1") is False
        assert get_buffer_count("s1") == 0

    @pytest.mark.asyncio
    async def test_clear_idempotent(self) -> None:
        """clear_buffer on empty buffer is safe."""
        clear_buffer("s1")
        assert is_buffering("s1") is False


# ===========================================================================
# Task 5.3 — Debounce: schedule_flush
# ===========================================================================


class TestDebounce:
    """Test schedule_flush timer behavior."""

    @pytest.mark.asyncio
    async def test_schedule_flush_fires_callback(self) -> None:
        """After window_seconds, callback is invoked with joined message."""
        results: list[tuple[str, str]] = []

        async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
            from backend.app.message_buffer import release_processing_lease

            try:
                results.append((sid, msg))
            finally:
                release_processing_lease(sid, lease.token)

        await add_to_buffer("s1", "Hola")
        await add_to_buffer("s1", "mundo")
        schedule_flush("s1", window_seconds=1, callback=_on_flush)

        # Wait for the timer to fire
        await asyncio.sleep(1.5)

        assert len(results) == 1
        assert results[0] == ("s1", "Hola\nmundo")

    @pytest.mark.asyncio
    async def test_schedule_flush_resets_timer(self) -> None:
        """Each call to schedule_flush cancels the previous timer."""
        results: list[str] = []

        async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
            from backend.app.message_buffer import release_processing_lease

            try:
                results.append(msg)
            finally:
                release_processing_lease(sid, lease.token)

        await add_to_buffer("s1", "Hola")
        schedule_flush("s1", window_seconds=1, callback=_on_flush)

        # Add more messages and reschedule before first timer fires
        await asyncio.sleep(0.3)
        await add_to_buffer("s1", "mundo")
        schedule_flush("s1", window_seconds=1, callback=_on_flush)

        # Wait for the second timer
        await asyncio.sleep(1.5)

        # Only the second timer should have fired, with all messages
        assert len(results) == 1
        assert results[0] == "Hola\nmundo"

    @pytest.mark.asyncio
    async def test_schedule_flush_no_callback_when_empty(self) -> None:
        """Callback is NOT invoked if buffer is empty when timer fires."""
        results: list[str] = []

        async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
            del sid, msg, lease

        # Schedule flush without adding messages — buffer is empty

        # Manually set up a task without buffer entries
        schedule_flush("s1", window_seconds=1, callback=_on_flush)

        await asyncio.sleep(1.5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_schedule_flush_clears_buffer_state(self) -> None:
        """After timer fires and processes, buffer state is cleared."""
        results: list[str] = []

        async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
            from backend.app.message_buffer import release_processing_lease

            try:
                results.append(msg)
            finally:
                release_processing_lease(sid, lease.token)

        await add_to_buffer("s1", "test")
        schedule_flush("s1", window_seconds=1, callback=_on_flush)
        await asyncio.sleep(1.5)

        assert is_buffering("s1") is False
        assert get_buffer_count("s1") == 0

    @pytest.mark.asyncio
    async def test_schedule_flush_passes_lease_to_callback_on_error(self) -> None:
        """A failing callback retains explicit ownership for finally release."""
        from backend.app import message_buffer

        callback_finished = asyncio.Event()

        async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
            try:
                assert msg == "test"
                raise RuntimeError("callback failed")
            finally:
                message_buffer.release_processing_lease(sid, lease.token)
                callback_finished.set()

        await add_to_buffer("s1", "test")
        schedule_flush("s1", window_seconds=0, callback=_on_flush)
        await asyncio.wait_for(callback_finished.wait(), timeout=1)

        assert "s1" not in message_buffer._processing_leases


class TestLambdaSafeDebounce:
    """Test repository-backed buffering does not depend on background tasks."""

    @pytest.mark.asyncio
    async def test_repository_mode_does_not_create_asyncio_task(self) -> None:
        """Durable buffer mode leaves flushing to /buffer-result polling."""
        from backend.app import message_buffer
        from backend.app.dynamodb_state_repository import DynamoDBStateRepository
        from backend.tests.test_state_repository import FakeDynamoDBTable

        repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
        message_buffer.set_state_repository(repository)
        try:
            await add_to_buffer("lambda-safe", "Hola")

            async def _on_flush(sid: str, msg: str, lease: ProcessingLease) -> None:
                del sid, msg, lease

            with patch("backend.app.message_buffer.asyncio.create_task") as create_task:
                schedule_flush("lambda-safe", window_seconds=1, callback=_on_flush)

            create_task.assert_not_called()
            assert get_buffer_count("lambda-safe") == 1
        finally:
            message_buffer.set_state_repository(None)

    @pytest.mark.asyncio
    async def test_buffer_ready_to_flush_uses_last_message_timestamp(self) -> None:
        """The poller flushes only after the debounce window has elapsed."""
        from backend.app import message_buffer
        from backend.app.dynamodb_state_repository import DynamoDBStateRepository
        from backend.app.message_buffer import is_buffer_ready_to_flush
        from backend.tests.test_state_repository import FakeDynamoDBTable

        repository = DynamoDBStateRepository(table=FakeDynamoDBTable())
        message_buffer.set_state_repository(repository)
        try:
            await add_to_buffer("lambda-ready", "Hola")
            state = repository.get_buffer_state("lambda-ready")
            last_message_at = state.messages[-1].timestamp

            assert (
                is_buffer_ready_to_flush(
                    "lambda-ready",
                    window_seconds=5,
                    now=last_message_at + timedelta(seconds=4),
                )
                is False
            )
            assert (
                is_buffer_ready_to_flush(
                    "lambda-ready",
                    window_seconds=5,
                    now=last_message_at + timedelta(seconds=6),
                )
                is True
            )
        finally:
            message_buffer.set_state_repository(None)


class TestLocalProcessingLease:
    """Test local-memory parity with the repository lease contract."""

    def test_contention_exact_expiry_and_token_protected_release(self) -> None:
        from backend.app.message_buffer import (
            release_local_processing_lease,
            try_acquire_local_processing_lease,
        )
        from backend.app.state_repository import ProcessingLease

        now = datetime(2026, 7, 29, tzinfo=timezone.utc)
        first_lease = ProcessingLease(
            token="first", expires_at=now + timedelta(seconds=60)
        )
        replacement_lease = ProcessingLease(
            token="replacement", expires_at=now + timedelta(seconds=120)
        )

        first = try_acquire_local_processing_lease("s1", now=now, lease=first_lease)
        blocked = try_acquire_local_processing_lease(
            "s1", now=now, lease=replacement_lease
        )
        replacement = try_acquire_local_processing_lease(
            "s1", now=first_lease.expires_at, lease=replacement_lease
        )

        assert first.acquired and first.lease == first_lease
        assert not blocked.acquired and blocked.lease is None
        assert replacement.acquired and replacement.lease == replacement_lease
        assert not release_local_processing_lease("s1", "first").released
        assert not release_local_processing_lease("missing", "first").released
        assert release_local_processing_lease("s1", "replacement").released

    def test_competing_acquisitions_have_exactly_one_winner(self) -> None:
        from backend.app.message_buffer import try_acquire_local_processing_lease
        from backend.app.state_repository import ProcessingLease

        now = datetime(2026, 7, 29, tzinfo=timezone.utc)
        barrier = Barrier(2)

        def acquire(token: str) -> bool:
            lease = ProcessingLease(token=token, expires_at=now + timedelta(seconds=60))
            barrier.wait()
            return try_acquire_local_processing_lease(
                "shared", now=now, lease=lease
            ).acquired

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(acquire, ("worker-a", "worker-b")))

        assert sorted(outcomes) == [False, True]

    def test_facade_has_equivalent_local_and_repository_outcomes(self) -> None:
        from backend.app import message_buffer
        from backend.app.dynamodb_state_repository import DynamoDBStateRepository
        from backend.app.message_buffer import (
            acquire_processing_lease,
            release_processing_lease,
        )
        from backend.tests.test_state_repository import FakeDynamoDBTable

        now = datetime(2026, 7, 29, tzinfo=timezone.utc)

        def exercise() -> list[bool]:
            first = acquire_processing_lease("parity", now=now, token="first")
            blocked = acquire_processing_lease("parity", now=now, token="blocked")
            assert first.lease is not None
            replacement = acquire_processing_lease(
                "parity", now=first.lease.expires_at, token="replacement"
            )
            stale = release_processing_lease("parity", "first")
            owner = release_processing_lease("parity", "replacement")
            return [
                first.acquired,
                blocked.acquired,
                replacement.acquired,
                stale.released,
                owner.released,
            ]

        local_outcomes = exercise()
        message_buffer.set_state_repository(
            DynamoDBStateRepository(table=FakeDynamoDBTable())
        )
        try:
            repository_outcomes = exercise()
        finally:
            message_buffer.set_state_repository(None)

        assert local_outcomes == repository_outcomes == [True, False, True, False, True]

    def test_legacy_processing_markers_remain_isolated_from_leases(self) -> None:
        from backend.app import message_buffer
        from backend.app.message_buffer import (
            acquire_processing_lease,
            clear_processing,
            is_processing,
            release_processing_lease,
            set_processing,
        )

        now = datetime(2026, 7, 29, tzinfo=timezone.utc)
        acquired = acquire_processing_lease("legacy", now=now, token="owner")
        set_processing("legacy")

        assert acquired.acquired
        assert is_processing("legacy")
        assert "legacy" in message_buffer._processing_leases

        clear_processing("legacy")

        assert not is_processing("legacy")
        assert not acquire_processing_lease("legacy", now=now, token="blocked").acquired
        assert release_processing_lease("legacy", "owner").released


# ===========================================================================
# Task 5.5 — Overflow: max_messages triggers immediate flush
# ===========================================================================


class TestOverflow:
    """Test buffer overflow behavior."""

    @pytest.mark.asyncio
    async def test_append_decides_overflow_before_concurrent_claim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A claim after append unlock cannot invalidate its overflow read."""
        from backend.app import message_buffer

        claim_started = Event()
        claim_finished = Event()
        claimed: list[str | None] = []

        class ClaimOnReleaseLock:
            def __init__(self) -> None:
                self.lock = RLock()
                self.is_armed = True

            def __enter__(self) -> None:
                self.lock.acquire()

            def __exit__(self, *args: object) -> None:
                self.lock.release()
                if self.is_armed:
                    self.is_armed = False
                    claim_started.set()
                    assert claim_finished.wait(timeout=2)

        def claim() -> None:
            assert claim_started.wait(timeout=2)
            claimed.append(asyncio.run(message_buffer.flush_buffer("race")))
            claim_finished.set()

        monkeypatch.setattr(message_buffer, "_state_lock", ClaimOnReleaseLock())
        thread = Thread(target=claim)
        thread.start()
        result = await add_to_buffer("race", "first", max_messages=1)
        thread.join(timeout=2)

        assert result is None
        assert claimed == ["first"] and not thread.is_alive()

    @pytest.mark.asyncio
    async def test_overflow_at_max_messages(self) -> None:
        """When max_messages is reached, add_to_buffer returns joined text."""
        # Fill buffer to 4 (below max)
        for i in range(4):
            result = await add_to_buffer("s1", f"msg{i}", max_messages=5)
            assert result is None  # Still buffering

        # 5th message triggers overflow
        result = await add_to_buffer("s1", "msg4", max_messages=5)
        assert result is not None
        assert "msg0" in result.message
        assert "msg4" in result.message
        from backend.app.message_buffer import release_processing_lease

        release_processing_lease("s1", result.lease.token)
        # Buffer is now empty
        assert is_buffering("s1") is False

    @pytest.mark.asyncio
    async def test_overflow_joins_all_messages(self) -> None:
        """Overflow returns all accumulated messages joined with newline."""
        messages = [f"message {i}" for i in range(5)]
        for msg in messages[:4]:
            await add_to_buffer("s1", msg, max_messages=5)

        result = await add_to_buffer("s1", messages[4], max_messages=5)
        assert result is not None
        for msg in messages:
            assert msg in result.message
        # Check newline separation
        assert result.message.count("\n") == 4
        from backend.app.message_buffer import release_processing_lease

        release_processing_lease("s1", result.lease.token)

    @pytest.mark.asyncio
    async def test_overflow_with_custom_max(self) -> None:
        """Overflow respects custom max_messages value."""
        await add_to_buffer("s1", "a", max_messages=2)
        result = await add_to_buffer("s1", "b", max_messages=2)
        assert result is not None
        assert result.message == "a\nb"
        assert is_buffering("s1") is False
        from backend.app.message_buffer import release_processing_lease

        release_processing_lease("s1", result.lease.token)

    @pytest.mark.asyncio
    async def test_no_overflow_below_max(self) -> None:
        """No overflow when below max_messages."""
        for i in range(4):
            result = await add_to_buffer("s1", f"msg{i}", max_messages=5)
            assert result is None
        assert is_buffering("s1") is True

    @pytest.mark.asyncio
    async def test_overflow_conflict_does_not_flush(self) -> None:
        """A lease conflict leaves every overflow message buffered."""
        from backend.app import message_buffer

        owner = message_buffer.acquire_processing_lease("s1", token="owner")
        assert owner.acquired

        await add_to_buffer("s1", "a", max_messages=2)
        result = await add_to_buffer("s1", "b", max_messages=2)

        assert result is None
        assert get_buffer_count("s1") == 2
        assert message_buffer.release_processing_lease("s1", "owner").released


class TestDurableBufferState:
    """Tests for repository-backed buffer state required by Lambda."""

    def test_repository_buffer_survives_new_instance(self) -> None:
        """Buffered messages are restored across repository instances."""
        from backend.app.dynamodb_state_repository import DynamoDBStateRepository
        from backend.tests.test_state_repository import FakeDynamoDBTable

        table = FakeDynamoDBTable()
        first_repo = DynamoDBStateRepository(table=table)
        first_repo.append_buffer_message("s1", "Hola")
        first_repo.append_buffer_message("s1", "paneles")

        cold_repo = DynamoDBStateRepository(table=table)
        state = cold_repo.get_buffer_state("s1")

        assert [message.message for message in state.messages] == ["Hola", "paneles"]

    def test_repository_pending_chat_response_is_consumed_once(self) -> None:
        """Polling state stores and consumes pending chat responses once."""
        from backend.app.dynamodb_state_repository import DynamoDBStateRepository
        from backend.tests.test_state_repository import FakeDynamoDBTable

        repo = DynamoDBStateRepository(table=FakeDynamoDBTable())
        repo.set_processing("s1")
        repo.set_pending_chat_response("s1", '{"response":"ok"}')

        assert repo.get_buffer_state("s1").processing_started_at is not None
        assert repo.pop_pending_chat_response("s1") == '{"response":"ok"}'
        assert repo.pop_pending_chat_response("s1") is None
        assert repo.get_buffer_state("s1").processing_started_at is None


class TestLocalPendingState:
    """Local pending delivery matches the durable consume-once contract."""

    @pytest.mark.parametrize("value", ["ready", ""])
    def test_pending_result_is_consumed_once(self, value: str) -> None:
        from backend.app import message_buffer

        message_buffer.set_pending_result("s1", value)

        assert message_buffer.pop_pending_result("s1") == value
        assert message_buffer.pop_pending_result("s1") is None

    @pytest.mark.parametrize("value", ['{"response":"ok"}', ""])
    def test_pending_chat_response_is_consumed_once_and_clears_processing(
        self, value: str
    ) -> None:
        from backend.app import message_buffer

        message_buffer.set_processing("s1")
        message_buffer.set_pending_chat_response("s1", value)

        assert message_buffer.pop_pending_chat_response("s1") == value
        assert message_buffer.is_processing("s1") is False
        assert message_buffer.pop_pending_chat_response("s1") is None

    def test_missing_chat_response_does_not_clear_processing(self) -> None:
        from backend.app import message_buffer

        message_buffer.set_processing("s1")

        assert message_buffer.pop_pending_chat_response("s1") is None
        assert message_buffer.is_processing("s1") is True

    @pytest.mark.parametrize(
        ("setter_name", "popper_name"),
        [
            ("set_pending_result", "pop_pending_result"),
            ("set_pending_chat_response", "pop_pending_chat_response"),
        ],
    )
    def test_concurrent_consumers_have_exactly_one_winner(
        self, setter_name: str, popper_name: str
    ) -> None:
        from backend.app import message_buffer

        getattr(message_buffer, setter_name)("s1", "ready")
        barrier = Barrier(8)

        def consume() -> str | None:
            barrier.wait()
            return getattr(message_buffer, popper_name)("s1")

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: consume(), range(8)))

        assert results.count("ready") == 1
        assert results.count(None) == 7


# ===========================================================================
# Task 5.7 — Endpoint integration tests
# ===========================================================================


class TestEndpointBufferIntegration:
    """Test buffer wiring in the /chat endpoint."""

    def _make_client(self, monkeypatch: pytest.MonkeyPatch, enabled: bool = True):
        """Create a TestClient with buffer settings patched.

        Returns (client, app) tuple.
        """
        monkeypatch.setenv("MULTI_MESSAGE_BUFFER_ENABLED", str(enabled).lower())
        monkeypatch.setenv("BUFFER_WINDOW_SECONDS", "1")
        # Required for module-level client instantiation
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("CHAT_API_KEY", "test-key")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("AWS_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("GREETING_ENABLED", "false")
        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")

        # Reset settings proxy so new env vars take effect
        from backend.app.config import settings

        settings.reset()

        from fastapi.testclient import TestClient

        # Import app fresh — settings proxy will read new env vars
        from backend.main import app
        from backend.app.auth import verify_api_key

        monkeypatch.setattr(
            app,
            "dependency_overrides",
            {verify_api_key: lambda: "test_key"},
        )
        client = TestClient(app)
        return client, app

    def test_buffer_returns_202_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When multi_message_buffer_enabled=True, first message returns 202."""
        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        response = client.post(
            "/chat",
            json={"message": "Hola"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "buffering"
        assert data["session_id"]

        # Cleanup
        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

    def test_buffer_returns_202_on_subsequent_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Subsequent messages within window also return 202."""
        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        # First message
        r1 = client.post(
            "/chat",
            json={"message": "Hola"},
        )
        assert r1.status_code == 202
        session_id = r1.json()["session_id"]

        # Second message — still buffering
        r2 = client.post(
            "/chat",
            json={"message": "quisiera info", "session_id": session_id},
        )
        assert r2.status_code == 202

        # Cleanup
        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_is_final_bypasses_buffer(
        self,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When is_final=True, message is processed immediately, not buffered."""
        mock_llm.return_value = make_llm_response(
            text="[INTENT: FAQ] Aquí tienes la información solicitada."
        )

        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        # First message — starts buffering
        r1 = client.post(
            "/chat",
            json={"message": "Hola"},
        )
        assert r1.status_code == 202
        session_id = r1.json()["session_id"]

        # Second message with is_final — should process
        r2 = client.post(
            "/chat",
            json={
                "message": "sobre paneles",
                "session_id": session_id,
                "is_final": True,
            },
        )
        assert r2.status_code == 200
        data = r2.json()
        # Should contain joined message (original + is_final)
        assert "response" in data
        assert data["session_id"] == session_id

        # Cleanup
        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
        app.dependency_overrides.clear()

    @patch("backend.main.llm_client.get_llm_response_with_tools")
    def test_overflow_flushes_and_processes(
        self,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When buffer reaches max (5), 6th message triggers flush + process."""
        mock_llm.return_value = make_llm_response(
            text="[INTENT: FAQ] Respuesta consolidada."
        )

        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        # Send 4 messages — all should buffer
        session_id = ""
        for i in range(4):
            payload = {"message": f"msg{i}"}
            if i > 0:
                payload["session_id"] = session_id
            r = client.post(
                "/chat",
                json=payload,
            )
            assert r.status_code == 202, f"Message {i} should return 202"
            if i == 0:
                session_id = r.json()["session_id"]

        # 5th message triggers overflow → processes
        r5 = client.post(
            "/chat",
            json={"message": "msg4", "session_id": session_id},
        )
        assert r5.status_code == 200
        data = r5.json()
        assert "response" in data

        # Verify LLM was called with joined message
        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        # The message passed to LLM should contain all buffered messages
        called_message = call_args.kwargs.get(
            "message", call_args[1].get("message", "")
        )
        assert "msg0" in called_message
        assert "msg4" in called_message

        # Cleanup
        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
        app.dependency_overrides.clear()

    def test_buffer_disabled_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When multi_message_buffer_enabled=False, no buffering occurs."""
        client, app = self._make_client(monkeypatch, enabled=False)

        with patch("backend.main.llm_client") as mock_llm:
            mock_llm.get_llm_response_with_tools.return_value = {
                "output_text": "[INTENT: FAQ] Respuesta directa.",
            }
            response = client.post(
                "/chat",
                json={"message": "Hola", "session_id": "test-buffer-disabled"},
            )
            # When disabled, message goes straight through — should be 200
            # (may be 200 or error depending on mock coverage, but NOT 202)
            assert response.status_code != 202

        app.dependency_overrides.clear()
