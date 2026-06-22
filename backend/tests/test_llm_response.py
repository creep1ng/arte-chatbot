"""Unit tests for the LLMResponse model in schemas.py."""

from backend.app.schemas import LLMResponse


class TestLLMResponseModel:
    """Tests for LLMResponse Pydantic model."""

    def test_llm_response_with_all_fields(self) -> None:
        """Test LLMResponse stores all fields correctly."""
        resp = LLMResponse(
            text="Hello world",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "test", "arguments": "{}"},
                }
            ],
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        assert resp.text == "Hello world"
        assert len(resp.tool_calls) == 1
        assert resp.input_tokens == 100
        assert resp.output_tokens == 50
        assert resp.total_tokens == 150

    def test_llm_response_defaults(self) -> None:
        """Test LLMResponse defaults are zero/empty."""
        resp = LLMResponse()
        assert resp.text == ""
        assert resp.tool_calls == []
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0
        assert resp.total_tokens == 0

    def test_llm_response_model_dump(self) -> None:
        """Test model_dump() includes all fields."""
        resp = LLMResponse(
            text="test",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        data = resp.model_dump()
        assert data["text"] == "test"
        assert data["tool_calls"] == []
        assert data["input_tokens"] == 10
        assert data["output_tokens"] == 5
        assert data["total_tokens"] == 15

    def test_llm_response_tool_calls_default_factory(self) -> None:
        """Test that tool_calls uses default_factory (each instance independent)."""
        resp1 = LLMResponse()
        resp2 = LLMResponse()
        resp1.tool_calls.append({"id": "x"})
        assert resp2.tool_calls == []

    def test_llm_response_text_only(self) -> None:
        """Test creating LLMResponse with only text field."""
        resp = LLMResponse(text="Simple response")
        assert resp.text == "Simple response"
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0
        assert resp.total_tokens == 0
