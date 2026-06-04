"""Tests for WhatsApp-related configuration settings.

Validates that all 8 new WhatsApp settings fields exist with correct defaults,
that the model validator catches min > max delays, and that invalid timezones
are rejected.
"""

import pytest


def _reset_settings() -> None:
    """Import and reset the settings proxy so next access reads fresh env."""
    from backend.app.config import settings

    settings.reset()


class TestWhatsAppConfigDefaults:
    """Verify all 8 new settings fields exist with correct defaults."""

    def test_whatsapp_formatter_enabled_default_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WHATSAPP_FORMATTER_ENABLED defaults to False."""
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "false")
        _reset_settings()
        from backend.app.config import settings

        assert settings.whatsapp_formatter_enabled is False

    def test_split_messages_enabled_default_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SPLIT_MESSAGES_ENABLED defaults to False."""
        monkeypatch.setenv("SPLIT_MESSAGES_ENABLED", "false")
        _reset_settings()
        from backend.app.config import settings

        assert settings.split_messages_enabled is False

    def test_msg_delay_min_ms_default_3000(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MSG_DELAY_MIN_MS defaults to 3000."""
        _reset_settings()
        from backend.app.config import settings

        assert settings.msg_delay_min_ms == 3000

    def test_msg_delay_max_ms_default_5000(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MSG_DELAY_MAX_MS defaults to 5000."""
        _reset_settings()
        from backend.app.config import settings

        assert settings.msg_delay_max_ms == 5000

    def test_greeting_enabled_default_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GREETING_ENABLED defaults to False."""
        monkeypatch.setenv("GREETING_ENABLED", "false")
        _reset_settings()
        from backend.app.config import settings

        assert settings.greeting_enabled is False

    def test_greeting_timezone_default_america_bogota(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GREETING_TIMEZONE defaults to America/Bogota."""
        _reset_settings()
        from backend.app.config import settings

        assert settings.greeting_timezone == "America/Bogota"

    def test_multi_message_buffer_enabled_default_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MULTI_MESSAGE_BUFFER_ENABLED defaults to False."""
        _reset_settings()
        from backend.app.config import settings

        assert settings.multi_message_buffer_enabled is False

    def test_buffer_window_seconds_default_5(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUFFER_WINDOW_SECONDS defaults to 5."""
        _reset_settings()
        from backend.app.config import settings

        assert settings.buffer_window_seconds == 5


class TestWhatsAppConfigValidation:
    """Verify model validators for delay and timezone constraints."""

    def test_min_delay_greater_than_max_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """msg_delay_min_ms > msg_delay_max_ms must raise a validation error."""
        monkeypatch.setenv("MSG_DELAY_MIN_MS", "8000")
        monkeypatch.setenv("MSG_DELAY_MAX_MS", "3000")
        _reset_settings()
        from backend.app.config import Settings

        with pytest.raises(ValueError):
            Settings()

    def test_min_delay_equal_to_max_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """msg_delay_min_ms == msg_delay_max_ms should be valid."""
        monkeypatch.setenv("MSG_DELAY_MIN_MS", "4000")
        monkeypatch.setenv("MSG_DELAY_MAX_MS", "4000")
        _reset_settings()
        from backend.app.config import Settings

        s = Settings()
        assert s.msg_delay_min_ms == 4000
        assert s.msg_delay_max_ms == 4000

    def test_invalid_timezone_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An invalid IANA timezone must raise a validation error."""
        monkeypatch.setenv("GREETING_TIMEZONE", "Invalid/Timezone")
        _reset_settings()
        from backend.app.config import Settings

        with pytest.raises(ValueError):
            Settings()

    def test_valid_timezone_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid IANA timezone should be accepted."""
        monkeypatch.setenv("GREETING_TIMEZONE", "America/Mexico_City")
        _reset_settings()
        from backend.app.config import Settings

        s = Settings()
        assert s.greeting_timezone == "America/Mexico_City"

    def test_env_override_whatsapp_formatter_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WHATSAPP_FORMATTER_ENABLED can be set via env var."""
        monkeypatch.setenv("WHATSAPP_FORMATTER_ENABLED", "true")
        _reset_settings()
        from backend.app.config import settings

        assert settings.whatsapp_formatter_enabled is True

    def test_env_override_buffer_window_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUFFER_WINDOW_SECONDS can be set via env var."""
        monkeypatch.setenv("BUFFER_WINDOW_SECONDS", "10")
        _reset_settings()
        from backend.app.config import settings

        assert settings.buffer_window_seconds == 10

    def test_buffer_window_seconds_accepts_large_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUFFER_WINDOW_SECONDS accepts values > 15 (no artificial limit)."""
        monkeypatch.setenv("BUFFER_WINDOW_SECONDS", "30")
        _reset_settings()
        from backend.app.config import settings

        assert settings.buffer_window_seconds == 30
