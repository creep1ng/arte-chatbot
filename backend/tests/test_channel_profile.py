"""Tests for ChannelProfile Pydantic model and utilities.

Validates defaults, field constraints, and the prompt-suffix helper.
"""

import pytest
from pydantic import ValidationError

from backend.app.channel_profile import ChannelProfile, get_default_channel_profile


class TestChannelProfile:
    """ChannelProfile must expose safe defaults and enforce constraints."""

    def test_defaults(self) -> None:
        profile = ChannelProfile(inbox_id="1")
        assert profile.channel_type == "web"
        assert profile.system_prompt_suffix is None
        assert profile.message_formatter == "standard"
        assert profile.buffer_window_seconds == 5
        assert profile.enable_tool_calling is True
        assert profile.max_turns == 20
        assert profile.custom_attributes == {}

    def test_custom_attributes_default_factory(self) -> None:
        """Each instance must get its own dict to avoid shared mutable state."""
        a = ChannelProfile(inbox_id="1")
        b = ChannelProfile(inbox_id="2")
        a.custom_attributes["foo"] = "bar"
        assert "foo" not in b.custom_attributes

    def test_buffer_window_seconds_too_low(self) -> None:
        with pytest.raises(ValidationError):
            ChannelProfile(inbox_id="1", buffer_window_seconds=0)

    def test_buffer_window_seconds_negative(self) -> None:
        with pytest.raises(ValidationError):
            ChannelProfile(inbox_id="1", buffer_window_seconds=-1)

    def test_buffer_window_seconds_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ChannelProfile(inbox_id="1", buffer_window_seconds=61)

    def test_buffer_window_seconds_boundary_low(self) -> None:
        profile = ChannelProfile(inbox_id="1", buffer_window_seconds=1)
        assert profile.buffer_window_seconds == 1

    def test_buffer_window_seconds_boundary_high(self) -> None:
        profile = ChannelProfile(inbox_id="1", buffer_window_seconds=60)
        assert profile.buffer_window_seconds == 60

    def test_all_channel_types_accepted(self) -> None:
        for ct in ("whatsapp", "web", "email", "api"):
            profile = ChannelProfile(inbox_id="1", channel_type=ct)
            assert profile.channel_type == ct

    def test_invalid_channel_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChannelProfile(inbox_id="1", channel_type="sms")

    def test_invalid_message_formatter_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChannelProfile(inbox_id="1", message_formatter="fancy")

    def test_apply_to_system_prompt_no_suffix(self) -> None:
        base = "You are a helpful assistant."
        profile = ChannelProfile(inbox_id="1")
        assert profile.apply_to_system_prompt(base) == base

    def test_apply_to_system_prompt_with_suffix(self) -> None:
        base = "You are a helpful assistant."
        profile = ChannelProfile(inbox_id="1", system_prompt_suffix="Be concise.")
        result = profile.apply_to_system_prompt(base)
        assert result == "You are a helpful assistant.\n\nBe concise."

    def test_apply_to_system_prompt_empty_suffix_ignored(self) -> None:
        base = "You are a helpful assistant."
        profile = ChannelProfile(inbox_id="1", system_prompt_suffix="")
        assert profile.apply_to_system_prompt(base) == base


class TestGetDefaultChannelProfile:
    """Factory must return a fully populated default profile."""

    def test_returns_channel_profile(self) -> None:
        profile = get_default_channel_profile()
        assert isinstance(profile, ChannelProfile)

    def test_has_expected_defaults(self) -> None:
        profile = get_default_channel_profile()
        assert profile.inbox_id == "default"
        assert profile.channel_type == "web"
        assert profile.buffer_window_seconds == 5
        assert profile.enable_tool_calling is True
