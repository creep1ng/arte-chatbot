"""
Unit tests for the llm_client.py module.

Tests the LLM client for OpenAI Responses API integration with tool calling support.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.app.llm_client import (
    LLMClient,
    LLMServiceError,
    ARTE_SYSTEM_PROMPT,
    DATASHEET_SYSTEM_PROMPT,
)
from backend.app import llm_client as llm_client_module


class TestLLMClientInitialization:
    """Tests for LLMClient initialization."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}, clear=True)
    def test_llm_client_default_env_vars(self) -> None:
        """Test LLMClient initialization with default env vars."""
        client = LLMClient()
        assert client.api_key == "sk-test-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_llm_client_explicit_api_key(self) -> None:
        """Test LLMClient initialization with explicit API key."""
        client = LLMClient(api_key="sk-explicit-key")
        assert client.api_key == "sk-explicit-key"

    def test_llm_client_default_model(self) -> None:
        """Test LLMClient uses default model."""
        client = LLMClient()
        assert client.model == "gpt-5.4-nano"

    def test_llm_client_custom_model(self) -> None:
        """Test LLMClient accepts custom model."""
        client = LLMClient(model="gpt-4")
        assert client.model == "gpt-4"


class TestLLMClientWithTools:
    """Tests for get_llm_response_with_tools method."""

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_tools_returns_tool_calls(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools returns dict with tool_calls when LLM invokes tool."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_function_call = MagicMock()
        mock_function_call.type = "function_call"
        mock_function_call.call_id = "call_abc123"
        mock_function_call.name = "leer_ficha_tecnica"
        mock_function_call.arguments = '{"ruta_s3": "paneles/jinko-tiger-pro-460w.pdf", "categoria": "paneles", "fabricante": "Jinko", "modelo": "Tiger Pro 460W"}'

        mock_response = MagicMock()
        mock_response.output_text = ""
        mock_response.output = [mock_function_call]
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = await client.get_llm_response_with_tools(
            message="Dime las especificaciones del panel Jinko Tiger Pro 460W",
            session_id="test-session-123",
        )

        assert "output_text" in result
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "leer_ficha_tecnica"

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_tools_no_tool_calls(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools returns dict without tool_calls for normal messages."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.type = "message"
        mock_message.content = [
            MagicMock(text="Hola, soy el asistente de Arte Soluciones Energéticas.")
        ]

        mock_response = MagicMock()
        mock_response.output_text = (
            "Hola, soy el asistente de Arte Soluciones Energéticas."
        )
        mock_response.output = [mock_message]
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = await client.get_llm_response_with_tools(
            message="Hola",
            session_id="test-session-123",
        )

        assert "output_text" in result
        assert "tool_calls" not in result
        assert (
            result["output_text"]
            == "Hola, soy el asistente de Arte Soluciones Energéticas."
        )

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_tools_uses_tools_parameter(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools passes tools to OpenAI API."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.type = "message"
        mock_message.content = [MagicMock(text="Test")]

        mock_response = MagicMock()
        mock_response.output_text = "Test"
        mock_response.output = [mock_message]
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        await client.get_llm_response_with_tools(
            message="Test",
            session_id="test-session",
        )

        call_kwargs = mock_client.responses.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "leer_ficha_tecnica"

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_tools_uses_instructions(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools passes instructions parameter."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.type = "message"
        mock_message.content = [MagicMock(text="Test")]

        mock_response = MagicMock()
        mock_response.output_text = "Test"
        mock_response.output = [mock_message]
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        await client.get_llm_response_with_tools(
            message="Test",
            session_id="test-session",
        )

        call_kwargs = mock_client.responses.create.call_args.kwargs
        assert "instructions" in call_kwargs
        assert call_kwargs["instructions"] == ARTE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_get_llm_response_with_tools_raises_without_api_key(self) -> None:
        """Test get_llm_response_with_tools raises error without API key."""
        client = LLMClient(api_key="")

        with pytest.raises(LLMServiceError) as exc_info:
            await client.get_llm_response_with_tools(
                message="Test",
                session_id="test-session",
            )

        assert "Missing OpenAI API key" in str(exc_info.value)


class TestLLMClientWithFile:
    """Tests for get_llm_response_with_file method."""

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_file_sends_message(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_file sends message with file_id to OpenAI."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.output_text = "El panel tiene una potencia de 460W..."
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = await client.get_llm_response_with_file(
            message="¿Cuáles son las especificaciones de este panel?",
            file_id="file-abc123",
            session_id="test-session-123",
        )

        assert result == "El panel tiene una potencia de 460W..."

        call_kwargs = mock_client.responses.create.call_args.kwargs
        assert "input" in call_kwargs
        input_data = call_kwargs["input"]

        user_message = input_data[0]
        assert user_message["role"] == "user"
        assert isinstance(user_message["content"], list)
        file_item = user_message["content"][0]
        assert file_item["type"] == "input_file"
        assert file_item["file_id"] == "file-abc123"
        text_item = user_message["content"][1]
        assert text_item["type"] == "input_text"

    @pytest.mark.asyncio
    @patch("backend.app.llm_client.AsyncOpenAI")
    async def test_get_llm_response_with_file_uses_datasheet_prompt(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_file uses DATASHEET_SYSTEM_PROMPT."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.output_text = "Test"
        mock_client.responses.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        await client.get_llm_response_with_file(
            message="Test",
            file_id="file-abc123",
            session_id="test-session",
        )

        call_kwargs = mock_client.responses.create.call_args.kwargs
        assert "instructions" in call_kwargs
        assert "ficha técnica" in call_kwargs["instructions"].lower()

    @pytest.mark.asyncio
    async def test_get_llm_response_with_file_raises_without_api_key(self) -> None:
        """Test get_llm_response_with_file raises error without API key."""
        client = LLMClient(api_key="")

        with pytest.raises(LLMServiceError) as exc_info:
            await client.get_llm_response_with_file(
                message="Test",
                file_id="file-abc123",
                session_id="test-session",
            )

        assert "Missing OpenAI API key" in str(exc_info.value)


class TestSystemPrompts:
    """Tests for system prompt constants."""

    def test_datasheet_system_prompt_exists(self) -> None:
        """Test DATASHEET_SYSTEM_PROMPT constant exists and is not empty."""
        assert hasattr(llm_client_module, "DATASHEET_SYSTEM_PROMPT")
        assert DATASHEET_SYSTEM_PROMPT is not None
        assert len(DATASHEET_SYSTEM_PROMPT) > 0

    def test_datasheet_system_prompt_content(self) -> None:
        """Test DATASHEET_SYSTEM_PROMPT contains relevant content."""
        assert "ficha técnica" in DATASHEET_SYSTEM_PROMPT.lower()
        assert "responde" in DATASHEET_SYSTEM_PROMPT.lower()

    def test_arte_system_prompt_exists(self) -> None:
        """Test ARTE_SYSTEM_PROMPT constant exists."""
        assert hasattr(llm_client_module, "ARTE_SYSTEM_PROMPT")
        assert ARTE_SYSTEM_PROMPT is not None
        assert len(ARTE_SYSTEM_PROMPT) > 0

    def test_arte_system_prompt_contains_tool_instructions(self) -> None:
        """Test updated ARTE_SYSTEM_PROMPT contains tool instructions."""
        assert (
            "leer_ficha_tecnica" in ARTE_SYSTEM_PROMPT.lower()
            or "herramienta" in ARTE_SYSTEM_PROMPT.lower()
        )

    def test_arte_system_prompt_contains_s3_path_convention(self) -> None:
        """Test ARTE_SYSTEM_PROMPT contains S3 path convention."""
        assert (
            "s3" in ARTE_SYSTEM_PROMPT.lower() or "ruta" in ARTE_SYSTEM_PROMPT.lower()
        )


class TestLLMServiceError:
    """Tests for LLMServiceError exception."""

    def test_llm_service_error_is_exception(self) -> None:
        """Test LLMServiceError inherits from Exception."""
        error = LLMServiceError("Test error")
        assert isinstance(error, Exception)

    def test_llm_service_error_message(self) -> None:
        """Test LLMServiceError preserves error message."""
        error = LLMServiceError("Custom error message")
        assert str(error) == "Custom error message"


class TestLLMClientLazyInitialization:
    """Tests for lazy client initialization."""

    @patch("backend.app.llm_client.AsyncOpenAI")
    def test_openai_client_property_lazy_init(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test that AsyncOpenAI client is not initialized until accessed."""
        client = LLMClient(api_key="sk-test-key")

        assert client._openai_client is None

        _ = client.openai_client

        assert client._openai_client is not None
        mock_openai_class.assert_called_once_with(api_key="sk-test-key")
