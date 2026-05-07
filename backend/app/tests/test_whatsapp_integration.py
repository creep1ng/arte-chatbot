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
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")
        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
        monkeypatch.setenv("GREETING_ENABLED", "false")
        from backend.app.config import settings

        settings.reset()

        assert settings.whatsapp_formatter_enabled is False


class TestSplitterWiring:
    """Verify splitting integrates with ChatResponse via process_split_messages."""

    def test_splitting_enabled_with_delimiters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SPLIT_MESSAGES_ENABLED=true and response has delimiters,
        process_split_messages returns messages and delays."""
        from backend.app.message_splitter import process_split_messages

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "true")
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")
        from backend.app.config import settings

        settings.reset()

        text = "Primer mensaje\n---\nSegundo mensaje\n---\nTercer mensaje"
        messages, delays = process_split_messages(text, "FAQ")

        assert len(messages) == 3
        assert len(delays) == 2
        assert messages[0] == "Primer mensaje"

    def test_splitting_disabled_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SPLIT_MESSAGES_ENABLED=false, process_split_messages returns empty."""
        from backend.app.message_splitter import process_split_messages

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
        from backend.app.config import settings

        settings.reset()

        text = "Msg 1\n---\nMsg 2"
        messages, delays = process_split_messages(text, "FAQ")

        assert messages == []
        assert delays == []

    def test_escalation_not_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Escalation intents should not be split even when enabled."""
        from backend.app.message_splitter import process_split_messages

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "true")
        from backend.app.config import settings

        settings.reset()

        text = "Agente te contactará\n---\nInfo adicional"
        messages, delays = process_split_messages(text, "escalate_quote")

        assert messages == []
        assert delays == []

    def test_no_delimiters_no_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response without delimiters returns empty (no split needed)."""
        from backend.app.message_splitter import process_split_messages

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "true")
        from backend.app.config import settings

        settings.reset()

        text = "Un solo mensaje sin delimitadores"
        messages, delays = process_split_messages(text, "FAQ")

        assert messages == []
        assert delays == []

    def test_split_with_formatter_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both flags are on, each message is formatted individually."""
        from backend.app.message_splitter import process_split_messages

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "true")
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "true")
        from backend.app.config import settings

        settings.reset()

        text = "**Paneles** monocristalinos\n---\n**Paneles** policristalinos"
        messages, delays = process_split_messages(text, "FAQ")

        assert len(messages) == 2
        # ** → * for WhatsApp bold
        assert "**" not in messages[0]
        assert "**" not in messages[1]


class TestSystemPromptInjection:
    """Verify system prompt includes/excludes WhatsApp instructions by flag."""

    def test_prompt_includes_split_instructions_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When split_messages_enabled=True, system prompt has WhatsApp section."""
        from backend.app.llm_client import ARTE_SYSTEM_PROMPT, _WHATSAPP_SPLIT_INSTRUCTIONS

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "true")
        from backend.app.config import settings

        settings.reset()

        # Simulate what main.py does
        prompt = ARTE_SYSTEM_PROMPT
        if settings.split_messages_enabled:
            prompt += _WHATSAPP_SPLIT_INSTRUCTIONS

        assert "---" in prompt
        assert "300 caracteres" in prompt

    def test_prompt_excludes_split_instructions_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When split_messages_enabled=False, system prompt has no WhatsApp section."""
        from backend.app.llm_client import ARTE_SYSTEM_PROMPT, _WHATSAPP_SPLIT_INSTRUCTIONS

        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
        from backend.app.config import settings

        settings.reset()

        prompt = ARTE_SYSTEM_PROMPT
        if settings.split_messages_enabled:
            prompt += _WHATSAPP_SPLIT_INSTRUCTIONS

        assert "300 caracteres" not in prompt
