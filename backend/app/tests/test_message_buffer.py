"""Unit tests for multi-message input buffer (P4).

Tests buffer accumulation, flush, overflow, is_final hint,
and debounce scheduling for the WhatsApp multi-message buffer feature.

Strict TDD: tests written BEFORE implementation.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

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
def _clean_buffer_state() -> None:
    """Ensure clean buffer state between tests."""
    try:
        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
    except ImportError:
        pass
    yield
    try:
        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()
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

        async def _on_flush(sid: str, msg: str) -> None:
            results.append((sid, msg))

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

        async def _on_flush(sid: str, msg: str) -> None:
            results.append(msg)

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

        async def _on_flush(sid: str, msg: str) -> None:
            results.append(msg)

        # Schedule flush without adding messages — buffer is empty
        from backend.app import message_buffer

        # Manually set up a task without buffer entries
        schedule_flush("s1", window_seconds=1, callback=_on_flush)

        await asyncio.sleep(1.5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_schedule_flush_clears_buffer_state(self) -> None:
        """After timer fires and processes, buffer state is cleared."""
        results: list[str] = []

        async def _on_flush(sid: str, msg: str) -> None:
            results.append(msg)

        await add_to_buffer("s1", "test")
        schedule_flush("s1", window_seconds=1, callback=_on_flush)
        await asyncio.sleep(1.5)

        assert is_buffering("s1") is False
        assert get_buffer_count("s1") == 0


# ===========================================================================
# Task 5.5 — Overflow: max_messages triggers immediate flush
# ===========================================================================


class TestOverflow:
    """Test buffer overflow behavior."""

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
        assert "msg0" in result
        assert "msg4" in result
        # Buffer is now empty
        assert is_buffering("s1") is False

    @pytest.mark.asyncio
    async def test_overflow_joins_all_messages(self) -> None:
        """Overflow returns all accumulated messages joined with newline."""
        messages = [f"message {i}" for i in range(5)]
        for msg in messages[:4]:
            await add_to_buffer("s1", msg, max_messages=5)

        result = await add_to_buffer("s1", messages[4], max_messages=5)
        for msg in messages:
            assert msg in result
        # Check newline separation
        assert result.count("\n") == 4

    @pytest.mark.asyncio
    async def test_overflow_with_custom_max(self) -> None:
        """Overflow respects custom max_messages value."""
        await add_to_buffer("s1", "a", max_messages=2)
        result = await add_to_buffer("s1", "b", max_messages=2)
        assert result == "a\nb"
        assert is_buffering("s1") is False

    @pytest.mark.asyncio
    async def test_no_overflow_below_max(self) -> None:
        """No overflow when below max_messages."""
        for i in range(4):
            result = await add_to_buffer("s1", f"msg{i}", max_messages=5)
            assert result is None
        assert is_buffering("s1") is True


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

        app.dependency_overrides[verify_api_key] = lambda: "test_key"
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
            json={"message": "Hola", "session_id": "test-buffer-1"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "buffering"
        assert data["session_id"] == "test-buffer-1"

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
            json={"message": "Hola", "session_id": "test-buffer-2"},
        )
        assert r1.status_code == 202

        # Second message — still buffering
        r2 = client.post(
            "/chat",
            json={"message": "quisiera info", "session_id": "test-buffer-2"},
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
        mock_llm.return_value = {
            "output_text": "[INTENT: FAQ] Aquí tienes la información solicitada.",
        }

        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        # First message — starts buffering
        r1 = client.post(
            "/chat",
            json={"message": "Hola", "session_id": "test-buffer-3"},
        )
        assert r1.status_code == 202

        # Second message with is_final — should process
        r2 = client.post(
            "/chat",
            json={
                "message": "sobre paneles",
                "session_id": "test-buffer-3",
                "is_final": True,
            },
        )
        assert r2.status_code == 200
        data = r2.json()
        # Should contain joined message (original + is_final)
        assert "response" in data
        assert data["session_id"] == "test-buffer-3"

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
        mock_llm.return_value = {
            "output_text": "[INTENT: FAQ] Respuesta consolidada.",
        }

        client, app = self._make_client(monkeypatch, enabled=True)

        from backend.app import message_buffer

        message_buffer._buffer.clear()
        message_buffer._buffer_tasks.clear()

        session_id = "test-buffer-overflow"

        # Send 4 messages — all should buffer
        for i in range(4):
            r = client.post(
                "/chat",
                json={"message": f"msg{i}", "session_id": session_id},
            )
            assert r.status_code == 202, f"Message {i} should return 202"

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
        called_message = call_args.kwargs.get("message", call_args[1].get("message", ""))
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
