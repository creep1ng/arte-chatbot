"""
Unit tests for the llm_client.py module.

Tests the LLM client for OpenAI Responses API integration with tool calling support.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
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
        assert client.model == "gpt-4o"

    def test_llm_client_custom_model(self) -> None:
        """Test LLMClient accepts custom model."""
        client = LLMClient(model="gpt-4")
        assert client.model == "gpt-4"


class TestLLMClientWithTools:
    """Tests for get_llm_response_with_tools method."""

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_tools_returns_tool_calls(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools returns dict with tool_calls when LLM invokes tool."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        tool_call = MagicMock()
        tool_call.id = "call_abc123"
        tool_call.function.name = "leer_ficha_tecnica"
        tool_call.function.arguments = {
            "ruta_s3": "paneles/jinko-tiger-pro-460w.pdf",
            "categoria": "paneles",
        }

        message = MagicMock()
        message.content = ""
        message.tool_calls = [tool_call]

        mock_choice = MagicMock()
        mock_choice.message = message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = client.get_llm_response_with_tools(
            message="Dime las especificaciones del panel Jinko Tiger Pro 460W",
            session_id="test-session-123",
        )

        assert "output_text" in result
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "leer_ficha_tecnica"

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_tools_no_tool_calls(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_tools returns dict without tool_calls for normal messages."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        message = MagicMock()
        message.content = "Hola, soy el asistente de Arte Soluciones Energéticas."
        message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = client.get_llm_response_with_tools(
            message="Hola",
            session_id="test-session-123",
        )

        assert "output_text" in result
        assert result["tool_calls"] == []
        assert (
            result["output_text"]
            == "Hola, soy el asistente de Arte Soluciones Energéticas."
        )

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_tools_uses_tools_parameter(
        self, mock_openai_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        message = MagicMock()
        message.content = "Test"
        message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        client.get_llm_response_with_tools(
            message="Test",
            session_id="test-session",
        )

        # Verify tools parameter was passed
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 2
        tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
        assert "leer_ficha_tecnica" in tool_names
        assert "buscar_producto" in tool_names

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_tools_uses_instructions(
        self, mock_openai_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        message = MagicMock()
        message.content = "Test"
        message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        client.get_llm_response_with_tools(
            message="Test",
            session_id="test-session",
        )

        # Verify instructions parameter was passed
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == ARTE_SYSTEM_PROMPT

    def test_get_llm_response_with_tools_raises_without_api_key(self) -> None:
        """Test get_llm_response_with_tools raises error without API key."""
        client = LLMClient(api_key="")

        with pytest.raises(LLMServiceError) as exc_info:
            client.get_llm_response_with_tools(
                message="Test",
                session_id="test-session",
            )

        assert "Missing OpenAI API key" in str(exc_info.value)


class TestLLMClientWithFile:
    """Tests for get_llm_response_with_file method."""

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_file_sends_message(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_file sends message with file_id to OpenAI."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock response
        mock_message = MagicMock()
        mock_message.content = "El panel tiene una potencia de 460W..."

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        result = client.get_llm_response_with_file(
            message="¿Cuáles son las especificaciones de este panel?",
            file_id="file-abc123",
            session_id="test-session-123",
        )

        assert result == "El panel tiene una potencia de 460W..."

        # Verify the call was made with correct parameters
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "messages" in call_kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        user_message = messages[1]
        assert user_message["role"] == "user"
        assert isinstance(user_message["content"], list)
        file_item = user_message["content"][0]
        assert file_item["type"] == "input_file"
        assert file_item["file_id"] == "file-abc123"
        text_item = user_message["content"][1]
        assert text_item["type"] == "input_text"

    @patch("backend.app.llm_client.OpenAI")
    def test_get_llm_response_with_file_uses_datasheet_prompt(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test get_llm_response_with_file uses DATASHEET_SYSTEM_PROMPT."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = "Test"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(api_key="sk-test-key")
        client.get_llm_response_with_file(
            message="Test",
            file_id="file-abc123",
            session_id="test-session",
        )

        # Verify the instructions parameter used
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert "ficha técnica" in messages[0]["content"].lower()

    def test_get_llm_response_with_file_raises_without_api_key(self) -> None:
        """Test get_llm_response_with_file raises error without API key."""
        client = LLMClient(api_key="")

        with pytest.raises(LLMServiceError) as exc_info:
            client.get_llm_response_with_file(
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

    @patch("backend.app.llm_client.OpenAI")
    def test_openai_client_property_lazy_init(
        self, mock_openai_class: MagicMock
    ) -> None:
        """Test that OpenAI client is not initialized until accessed."""
        client = LLMClient(api_key="sk-test-key")

        # Client should not be initialized yet
        assert client._openai_client is None

        # Access the openai_client property
        _ = client.openai_client

        # Now it should be initialized
        assert client._openai_client is not None
        mock_openai_class.assert_called_once_with(api_key="sk-test-key")
