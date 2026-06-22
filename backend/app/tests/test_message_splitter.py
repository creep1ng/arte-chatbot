"""Tests for prompt-based message splitting.

The LLM writes messages separated by `---` delimiters. The backend splits
on those delimiters, validates per-message character limits by intent,
and optionally regenerates overflow segments via LLM.
"""

from unittest.mock import patch, MagicMock

from backend.app.message_splitter import (
    split_response,
    get_max_chars_for_intent,
    should_split_intent,
    build_regeneration_prompt,
    process_split_messages,
)


# ─────────────────────────────────────────────
# split_response
# ─────────────────────────────────────────────


class TestSplitResponse:
    """Tests for the core split logic on `---` delimiters."""

    def test_single_delimiter_splits_into_two(self):
        text = "Primer mensaje\n---\nSegundo mensaje"
        assert split_response(text) == ["Primer mensaje", "Segundo mensaje"]

    def test_multiple_delimiters(self):
        text = "A\n---\nB\n---\nC\n---\nD"
        assert split_response(text) == ["A", "B", "C", "D"]

    def test_no_delimiter_returns_single_item(self):
        text = "Solo un mensaje sin delimitador"
        assert split_response(text) == ["Solo un mensaje sin delimitador"]

    def test_whitespace_around_delimiters_stripped(self):
        text = "  Hola  \n---\n  Mundo  "
        assert split_response(text) == ["Hola", "Mundo"]

    def test_empty_segments_dropped(self):
        text = "Hola\n---\n\n---\nMundo"
        result = split_response(text)
        assert result == ["Hola", "Mundo"]

    def test_delimiter_with_surrounding_blank_lines(self):
        text = "Mensaje 1\n\n---\n\nMensaje 2"
        result = split_response(text)
        assert result == ["Mensaje 1", "Mensaje 2"]

    def test_empty_string_returns_empty_list(self):
        assert split_response("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert split_response("   \n  ") == []

    def test_preserves_multiline_within_segment(self):
        text = "Línea 1\nLínea 2\nLínea 3\n---\nOtro mensaje"
        result = split_response(text)
        assert result == ["Línea 1\nLínea 2\nLínea 3", "Otro mensaje"]

    def test_delimiter_must_be_on_own_line(self):
        # "---" embedded in text should NOT split
        text = "Tengo 3 paneles---de 400W"
        result = split_response(text)
        assert result == ["Tengo 3 paneles---de 400W"]


# ─────────────────────────────────────────────
# get_max_chars_for_intent
# ─────────────────────────────────────────────


class TestGetMaxCharsForIntent:
    """Tests for per-intent character limits."""

    def test_faq_returns_300(self):
        assert get_max_chars_for_intent("FAQ") == 300

    def test_product_info_returns_800(self):
        assert get_max_chars_for_intent("product_info") == 800

    def test_escalation_returns_none(self):
        assert get_max_chars_for_intent("escalate_quote") is None

    def test_fuera_de_dominio_returns_none(self):
        assert get_max_chars_for_intent("fuera_de_dominio") is None

    def test_unknown_intent_returns_none(self):
        assert get_max_chars_for_intent("unknown_intent") is None


# ─────────────────────────────────────────────
# should_split_intent
# ─────────────────────────────────────────────


class TestShouldSplitIntent:
    """Tests for determining which intents should trigger splitting."""

    def test_faq_should_split(self):
        assert should_split_intent("FAQ") is True

    def test_product_info_should_split(self):
        assert should_split_intent("product_info") is True

    def test_escalation_should_not_split(self):
        assert should_split_intent("escalate_quote") is False

    def test_fuera_de_dominio_should_not_split(self):
        assert should_split_intent("fuera_de_dominio") is False


# ─────────────────────────────────────────────
# build_regeneration_prompt
# ─────────────────────────────────────────────


class TestBuildRegenerationPrompt:
    """Tests for regeneration prompt construction."""

    def test_contains_original_text(self):
        prompt = build_regeneration_prompt("Texto largo aquí", 300)
        assert "Texto largo aquí" in prompt

    def test_contains_max_chars(self):
        prompt = build_regeneration_prompt("x" * 400, 300)
        assert "300" in prompt

    def test_contains_current_length(self):
        prompt = build_regeneration_prompt("x" * 400, 300)
        assert "400" in prompt


# ─────────────────────────────────────────────
# process_split_messages (integration)
# ─────────────────────────────────────────────


class TestProcessSplitMessages:
    """Tests for the full split processing pipeline."""

    @patch("backend.app.message_splitter.settings")
    def test_splitting_disabled_returns_single_message(self, mock_settings):
        mock_settings.split_messages_enabled = False
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        messages, delays = process_split_messages(
            "Mensaje largo", "FAQ", llm_regenerate_fn=None
        )
        assert messages == []
        assert delays == []

    @patch("backend.app.message_splitter.settings")
    def test_escalation_intent_returns_empty_messages(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        messages, delays = process_split_messages(
            "Un agente te contactará", "escalate_quote", llm_regenerate_fn=None
        )
        assert messages == []
        assert delays == []

    @patch("backend.app.message_splitter.settings")
    def test_no_delimiters_returns_empty_messages(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        messages, delays = process_split_messages(
            "Solo un mensaje", "FAQ", llm_regenerate_fn=None
        )
        # No delimiters → treated as single message → no split
        assert messages == []
        assert delays == []

    @patch("backend.app.message_splitter.settings")
    def test_valid_split_returns_messages_and_delays(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        text = "Mensaje 1\n---\nMensaje 2\n---\nMensaje 3"
        messages, delays = process_split_messages(text, "FAQ", llm_regenerate_fn=None)
        assert len(messages) == 3
        assert len(delays) == 2
        assert all(3000 <= d <= 5000 for d in delays)

    @patch("backend.app.message_splitter.settings")
    def test_overflow_triggers_regeneration(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        long_msg = "x" * 400
        text = f"Mensaje corto\n---\n{long_msg}"
        mock_regenerate = MagicMock(return_value="Mensaje acortado")

        messages, delays = process_split_messages(
            text, "FAQ", llm_regenerate_fn=mock_regenerate
        )
        assert messages[0] == "Mensaje corto"
        assert messages[1] == "Mensaje acortado"
        mock_regenerate.assert_called_once()

    @patch("backend.app.message_splitter.settings")
    def test_formatter_applied_per_message(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = True
        mock_settings.msg_delay_min_ms = 3000
        mock_settings.msg_delay_max_ms = 5000

        text = "**Bold text**\n---\n**More bold**"
        messages, delays = process_split_messages(text, "FAQ", llm_regenerate_fn=None)
        # WhatsApp formatter converts ** → *
        assert all("*Bold" in m or "*More" in m for m in messages)

    @patch("backend.app.message_splitter.settings")
    def test_delays_within_configured_range(self, mock_settings):
        mock_settings.split_messages_enabled = True
        mock_settings.whatsapp_formatter_enabled = False
        mock_settings.msg_delay_min_ms = 4000
        mock_settings.msg_delay_max_ms = 6000

        text = "A\n---\nB\n---\nC"
        messages, delays = process_split_messages(text, "FAQ", llm_regenerate_fn=None)
        assert all(4000 <= d <= 6000 for d in delays)
