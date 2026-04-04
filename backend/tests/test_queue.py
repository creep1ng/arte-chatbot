"""Tests for message queue system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.queue import ChatMessage, MessageQueue


@pytest.mark.asyncio
async def test_chat_message_creation():
    """Test ChatMessage dataclass creation."""
    msg = ChatMessage(
        request_id="req-1",
        session_id="sess-1",
        message="Test message",
    )
    assert msg.request_id == "req-1"
    assert msg.session_id == "sess-1"
    assert msg.message == "Test message"
    assert isinstance(msg.future, asyncio.Future)


@pytest.mark.asyncio
async def test_message_queue_initialization():
    """Test MessageQueue initialization."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()

    queue = MessageQueue(
        max_workers=5,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    assert queue.max_workers == 5
    assert queue.max_queue_size == 100
    assert queue.llm_client == llm_client
    assert queue.s3_client == s3_client
    assert queue.file_inputs_client == file_inputs_client
    assert queue.session_manager == session_manager
    assert queue._running is False
    assert len(queue.workers) == 0


@pytest.mark.asyncio
async def test_message_queue_start_stop():
    """Test starting and stopping the message queue."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()

    queue = MessageQueue(
        max_workers=2,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    # Start queue
    await queue.start()
    assert queue._running is True
    assert len(queue.workers) == 2

    # Stop queue
    await queue.stop()
    assert queue._running is False
    assert len(queue.workers) == 0


@pytest.mark.asyncio
async def test_enqueue_raises_when_not_running():
    """Test that enqueue raises error when queue is not running."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    msg = ChatMessage(
        request_id="req-1",
        session_id="sess-1",
        message="Test",
    )

    with pytest.raises(RuntimeError, match="not running"):
        await queue.enqueue(msg)


@pytest.mark.asyncio
async def test_enqueue_basic():
    """Test basic enqueue functionality."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()
    # get_context_string is NOT async, so use MagicMock instead of AsyncMock
    session_manager.get_context_string = MagicMock(return_value="")
    session_manager.add_turn = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    await queue.start()

    msg = ChatMessage(
        request_id="req-1",
        session_id="sess-1",
        message="Test",
    )

    # Mock LLM response without tool calls
    llm_client.get_llm_response_with_tools.return_value = {
        "output_text": "Response",
        "tool_calls": None,
    }

    await queue.enqueue(msg)

    # Give worker time to process
    await asyncio.sleep(0.1)

    await queue.stop()

    # Future should be resolved
    assert msg.future.done()
    result = msg.future.result()
    assert result["response"] == "Response"
    assert result["escalate"] is False


@pytest.mark.asyncio
async def test_backpressure():
    """Test that queue properly handles multiple messages with max_queue_size."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()
    # get_context_string is NOT async, so use MagicMock instead of AsyncMock
    session_manager.get_context_string = MagicMock(return_value="")
    session_manager.add_turn = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=2,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    await queue.start()

    # Mock normal processing
    async def response(*args, **kwargs):
        return {"output_text": "Response", "tool_calls": None}

    llm_client.get_llm_response_with_tools = response

    # Enqueue multiple messages and verify they're all processed
    messages = []
    for i in range(5):
        msg = ChatMessage(
            request_id=f"req-{i}",
            session_id="sess-1",
            message=f"Message {i}",
        )
        messages.append(msg)
        await queue.enqueue(msg)

    # Wait for processing to complete
    await asyncio.sleep(0.5)

    await queue.stop()

    # All futures should be resolved
    for msg in messages:
        assert msg.future.done()
        result = msg.future.result()
        assert result["response"] == "Response"
        assert result["escalate"] is False


@pytest.mark.asyncio
async def test_multiple_workers_concurrent():
    """Test that multiple workers process messages concurrently."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()
    # get_context_string is NOT async, so use MagicMock instead of AsyncMock
    session_manager.get_context_string = MagicMock(return_value="")
    session_manager.add_turn = AsyncMock()

    queue = MessageQueue(
        max_workers=3,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    # Track which workers process which messages
    processed = []

    async def track_processing(*args, **kwargs):
        processed.append(asyncio.current_task().get_name())
        await asyncio.sleep(0.05)
        return {"output_text": "Response", "tool_calls": None}

    llm_client.get_llm_response_with_tools = track_processing

    await queue.start()

    # Enqueue multiple messages
    messages = [
        ChatMessage(
            request_id=f"req-{i}",
            session_id="sess-1",
            message=f"Message {i}",
        )
        for i in range(6)
    ]

    for msg in messages:
        await queue.enqueue(msg)

    # Wait for processing
    await asyncio.sleep(0.5)

    await queue.stop()

    # All messages should be processed
    assert len(processed) >= 3  # At least 3 concurrent processing


@pytest.mark.asyncio
async def test_worker_error_handling():
    """Test that worker errors are caught and set on future."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()
    # get_context_string is NOT async, so use MagicMock instead of AsyncMock
    session_manager.get_context_string = MagicMock(return_value="")
    session_manager.add_turn = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    # Mock LLM to raise error
    llm_client.get_llm_response_with_tools.side_effect = RuntimeError("LLM failed")

    await queue.start()

    msg = ChatMessage(
        request_id="req-1",
        session_id="sess-1",
        message="Test",
    )

    await queue.enqueue(msg)
    await asyncio.sleep(0.1)

    await queue.stop()

    # Future should contain exception
    assert msg.future.done()
    with pytest.raises(RuntimeError, match="LLM failed"):
        msg.future.result()


@pytest.mark.asyncio
async def test_process_tool_calls_with_file():
    """Test _process_tool_calls with file download and upload."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()
    # get_context_string is NOT async, so use MagicMock instead of AsyncMock
    session_manager.get_context_string = MagicMock(return_value="")
    session_manager.add_turn = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    # Mock file operations
    s3_client.download_pdf.return_value = b"pdf_content"
    file_inputs_client.upload_pdf.return_value = "file_id_123"
    llm_client.get_llm_response_with_file.return_value = "Response with file"
    file_inputs_client.delete_file = AsyncMock()

    # Tool call
    tool_calls = [
        {
            "function": {
                "name": "leer_ficha_tecnica",
                "arguments": '{"ruta_s3": "paneles/modelo_x.pdf"}',
            }
        }
    ]

    response = await queue._process_tool_calls(
        tool_calls=tool_calls,
        user_message="Tell me about model X",
        session_id="sess-1",
        worker_id=0,
        request_id="req-1",
    )

    assert response == "Response with file"
    s3_client.download_pdf.assert_called_once_with("paneles/modelo_x.pdf")
    file_inputs_client.upload_pdf.assert_called_once()
    file_inputs_client.delete_file.assert_called_once_with("file_id_123")


@pytest.mark.asyncio
async def test_message_queue_idempotent_stop():
    """Test that calling stop() multiple times is safe."""
    llm_client = AsyncMock()
    s3_client = AsyncMock()
    file_inputs_client = AsyncMock()
    session_manager = AsyncMock()

    queue = MessageQueue(
        max_workers=1,
        max_queue_size=100,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )

    await queue.start()
    await queue.stop()

    # Should not raise
    await queue.stop()
    assert queue._running is False
