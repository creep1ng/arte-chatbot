"""Integration tests for WhatsApp schema extensions and formatting wiring.

Tests backward compatibility of ChatResponse extensions and
feature-flag-gated formatting behavior.
"""

import pytest

from pydantic import ValidationError


class TestChatResponseSchema:
    """Verify ChatResponse new fields have correct defaults and backward compat."""

    def test_messages_defaults_to_empty_list(self) -> None:
        """ChatResponse.messages must default to empty list."""
        from backend.main import ChatResponse

        resp = ChatResponse(
            response="test",
            session_id="s1",
        )
        assert resp.messages == []

    def test_delays_ms_defaults_to_empty_list(self) -> None:
        """ChatResponse.delays_ms must default to empty list."""
        from backend.main import ChatResponse

        resp = ChatResponse(
            response="test",
            session_id="s1",
        )
        assert resp.delays_ms == []

    def test_backward_compat_existing_fields(self) -> None:
        """All existing ChatResponse fields still work with new fields defaulted."""
        from backend.main import ChatResponse
        from backend.app.schemas import SourceDocument

        resp = ChatResponse(
            response="Hola",
            escalate=False,
            intent_type="FAQ",
            reason=None,
            session_id="s1",
            source_documents=[SourceDocument(ruta="test.pdf")],
            num_sources=1,
            user_profile="principiante",
        )
        assert resp.response == "Hola"
        assert resp.escalate is False
        assert resp.intent_type == "FAQ"
        assert resp.session_id == "s1"
        assert resp.num_sources == 1
        assert resp.user_profile == "principiante"
        # New fields default
        assert resp.messages == []
        assert resp.delays_ms == []

    def test_messages_can_be_populated(self) -> None:
        """ChatResponse.messages can be populated with split messages."""
        from backend.main import ChatResponse

        resp = ChatResponse(
            response="msg1\n\nmsg2",
            session_id="s1",
            messages=["msg1", "msg2"],
            delays_ms=[3500],
        )
        assert resp.messages == ["msg1", "msg2"]
        assert resp.delays_ms == [3500]


class TestChatRequestSchema:
    """Verify ChatRequest new is_final field."""

    def test_is_final_defaults_to_none(self) -> None:
        """ChatRequest.is_final must default to None."""
        from backend.main import ChatRequest

        req = ChatRequest(message="hola")
        assert req.is_final is None

    def test_is_final_can_be_set(self) -> None:
        """ChatRequest.is_final can be set to True."""
        from backend.main import ChatRequest

        req = ChatRequest(message="hola", is_final=True)
        assert req.is_final is True

    def test_backward_compat_existing_fields(self) -> None:
        """Existing ChatRequest fields still work."""
        from backend.main import ChatRequest

        req = ChatRequest(message="test", session_id="s1")
        assert req.message == "test"
        assert req.session_id == "s1"
        assert req.is_final is None


class TestBufferingResponseSchema:
    """Verify BufferingResponse model exists and works."""

    def test_buffering_response_default_values(self) -> None:
        """BufferingResponse has correct defaults."""
        from backend.main import BufferingResponse

        resp = BufferingResponse(session_id="s1")
        assert resp.status == "buffering"
        assert resp.session_id == "s1"

    def test_buffering_response_custom_status(self) -> None:
        """BufferingResponse status can be overridden."""
        from backend.main import BufferingResponse

        resp = BufferingResponse(status="done", session_id="s1")
        assert resp.status == "done"


class TestFormatterWiring:
    """Verify formatting is applied/skipped based on feature flag.

    These tests verify the integration between the config flag and the
    formatter function — that the formatter is called when enabled and
    skipped when disabled.
    """

    def test_formatting_applied_when_flag_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When WHATSAPP_FORMATTER_ENABLED=true, format_for_whatsapp is applied."""
        from backend.app.whatsapp_formatter import format_for_whatsapp

        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "true")
        from backend.app.config import settings

        settings.reset()

        assert settings.whatsapp_formatter_enabled is True

        # Simulate the formatting that would happen in the endpoint
        raw_response = "**Los paneles** son `eficientes`."
        if settings.whatsapp_formatter_enabled:
            result = format_for_whatsapp(raw_response)
        else:
            result = raw_response

        # After formatting: **bold** → *bold*, `code` → code
        assert "*" in result
        assert "**" not in result
        assert "`" not in result
        assert "eficientes" in result

    def test_formatting_skipped_when_flag_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When WHATSAPP_FORMATTER_ENABLED=false, response passes through unchanged."""
        from backend.app.whatsapp_formatter import format_for_whatsapp

        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")
        from backend.app.config import settings

        settings.reset()

        assert settings.whatsapp_formatter_enabled is False

        raw_response = "**Los paneles** son `eficientes`."
        if settings.whatsapp_formatter_enabled:
            result = format_for_whatsapp(raw_response)
        else:
            result = raw_response

        # Without formatting: markdown markers remain
        assert result == raw_response

    def test_formatting_default_flag_is_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """By default (no env var set), formatting is disabled."""
        monkeypatch.delenv("WHATSAPP_FORMATTER_ENABLED", raising=False)
        from backend.app.config import settings

        settings.reset()

        assert settings.whatsapp_formatter_enabled is False
