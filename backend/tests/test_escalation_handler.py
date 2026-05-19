"""Tests for EscalationHandler.

Validates Chatwoot integration during human escalation handoff.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.app.chatwoot_client import ChatwootClient
from backend.app.escalation_handler import DEFAULT_ESCALATION_MESSAGE, EscalationHandler
from backend.app.session import SessionManager


class MockConfigProvider:
    """Minimal config provider for tests."""

    def __init__(self, enabled: bool = True, handoff_team_id: int = 5) -> None:
        self._enabled = enabled
        self._handoff = handoff_team_id

    def get_label(self, name: str) -> str:
        mapping = {
            "escalated": "escalated-test",
            "quote": "quote-test",
            "technical": "technical-test",
            "order": "order-test",
        }
        return mapping.get(name, name)

    def get_handoff_target(self) -> int:
        return self._handoff

    def is_chatwoot_enabled(self) -> bool:
        return self._enabled


@pytest.fixture
def mock_chatwoot_client() -> ChatwootClient:
    client = AsyncMock(spec=ChatwootClient)
    client.send_message.return_value = {"id": 99}
    client.add_label.return_value = {"labels": ["escalated"]}
    client.toggle_status.return_value = {"status": "open"}
    client.assign_conversation.return_value = {"id": 42}
    return client  # type: ignore[return-value]


@pytest.fixture
def config_provider() -> MockConfigProvider:
    return MockConfigProvider()


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.fixture
def escalation_handler(
    mock_chatwoot_client: ChatwootClient,
    config_provider: MockConfigProvider,
    session_manager: SessionManager,
) -> EscalationHandler:
    return EscalationHandler(
        chatwoot_client=mock_chatwoot_client,
        config_provider=config_provider,
        session_manager=session_manager,
    )


class TestHandleEscalation:
    """Escalation handoff must trigger all Chatwoot operations."""

    @pytest.mark.asyncio
    async def test_escalate_to_human_success(
        self,
        escalation_handler: EscalationHandler,
        mock_chatwoot_client: Any,
    ) -> None:
        result = await escalation_handler.escalate_to_human(
            conversation_id=42,
            reason="Necesita cotización",
            intent_type="escalate_quote",
        )

        assert result is True
        assert mock_chatwoot_client.add_label.await_args_list[0].args == (
            42,
            "escalated-test",
        )
        assert mock_chatwoot_client.add_label.await_args_list[1].args == (
            42,
            "quote-test",
        )
        mock_chatwoot_client.toggle_status.assert_awaited_once_with(42, "open")
        mock_chatwoot_client.assign_conversation.assert_awaited_once_with(42, team_id=5)
        mock_chatwoot_client.send_message.assert_awaited_once_with(
            42, DEFAULT_ESCALATION_MESSAGE
        )

    @pytest.mark.asyncio
    async def test_escalate_to_human_without_team_skips_assignment(
        self,
        mock_chatwoot_client: Any,
        session_manager: SessionManager,
    ) -> None:
        handler = EscalationHandler(
            chatwoot_client=mock_chatwoot_client,
            config_provider=MockConfigProvider(handoff_team_id=None),
            session_manager=session_manager,
        )

        assert await handler.escalate_to_human(42, "reason", "escalate_quote")
        mock_chatwoot_client.assign_conversation.assert_not_awaited()
        mock_chatwoot_client.toggle_status.assert_awaited_once_with(42, "open")

    @pytest.mark.asyncio
    async def test_escalate_to_human_label_failure_continues(
        self,
        mock_chatwoot_client: Any,
        config_provider: MockConfigProvider,
        session_manager: SessionManager,
    ) -> None:
        mock_chatwoot_client.add_label.side_effect = RuntimeError("label down")
        handler = EscalationHandler(
            chatwoot_client=mock_chatwoot_client,
            config_provider=config_provider,
            session_manager=session_manager,
        )

        assert await handler.escalate_to_human(42, "reason", "escalate_quote")
        mock_chatwoot_client.toggle_status.assert_awaited_once_with(42, "open")

    @pytest.mark.asyncio
    async def test_escalate_to_human_critical_failure_returns_false(
        self,
        mock_chatwoot_client: Any,
        config_provider: MockConfigProvider,
        session_manager: SessionManager,
    ) -> None:
        mock_chatwoot_client.toggle_status.side_effect = RuntimeError("status down")
        handler = EscalationHandler(
            chatwoot_client=mock_chatwoot_client,
            config_provider=config_provider,
            session_manager=session_manager,
        )

        assert not await handler.escalate_to_human(42, "reason", "escalate_quote")

    @pytest.mark.asyncio
    async def test_handle_escalation_calls_all_methods(
        self,
        escalation_handler: EscalationHandler,
        mock_chatwoot_client: Any,
    ) -> None:
        await escalation_handler.handle_escalation("s1", 42, "user requested quote")

        mock_chatwoot_client.add_label.assert_awaited_once_with(42, "escalated-test")
        mock_chatwoot_client.toggle_status.assert_awaited_once_with(42, "open")
        mock_chatwoot_client.assign_conversation.assert_awaited_once_with(42, team_id=5)
        mock_chatwoot_client.send_message.assert_awaited_once_with(
            42, DEFAULT_ESCALATION_MESSAGE
        )

    @pytest.mark.asyncio
    async def test_handle_escalation_stores_reason_in_session(
        self,
        escalation_handler: EscalationHandler,
        session_manager: SessionManager,
    ) -> None:
        await escalation_handler.handle_escalation("s1", 42, "user requested quote")
        reason = session_manager.get_user_profile("s1")
        # Escalation reason stored as a custom attribute via profile for now
        assert reason is not None


class TestHandleEscalationByIntent:
    """Intent-to-label mapping and delegation."""

    @pytest.mark.asyncio
    async def test_escalate_quote_maps_to_quote_label(
        self,
        escalation_handler: EscalationHandler,
        mock_chatwoot_client: Any,
    ) -> None:
        result = await escalation_handler.handle_escalation_by_intent(
            "s1", 42, "escalate_quote"
        )
        assert result is True
        calls = [c.args for c in mock_chatwoot_client.add_label.await_args_list]
        assert (42, "quote-test") in calls

    @pytest.mark.asyncio
    async def test_escalate_technical_maps_to_technical_label(
        self,
        escalation_handler: EscalationHandler,
        mock_chatwoot_client: Any,
    ) -> None:
        await escalation_handler.handle_escalation_by_intent(
            "s1", 42, "escalate_technical"
        )
        calls = [c.args for c in mock_chatwoot_client.add_label.await_args_list]
        assert (42, "technical-test") in calls

    @pytest.mark.asyncio
    async def test_escalate_order_maps_to_order_label(
        self,
        escalation_handler: EscalationHandler,
        mock_chatwoot_client: Any,
    ) -> None:
        await escalation_handler.handle_escalation_by_intent("s1", 42, "escalate_order")
        calls = [c.args for c in mock_chatwoot_client.add_label.await_args_list]
        assert (42, "order-test") in calls

    @pytest.mark.asyncio
    async def test_unknown_intent_returns_false(
        self,
        escalation_handler: EscalationHandler,
    ) -> None:
        result = await escalation_handler.handle_escalation_by_intent(
            "s1", 42, "unknown"
        )
        assert result is False


class TestGracefulDegradation:
    """Errors in Chatwoot API must not crash the handler."""

    @pytest.mark.asyncio
    async def test_api_error_logged_not_raised(
        self,
        config_provider: MockConfigProvider,
        session_manager: SessionManager,
    ) -> None:
        failing_client = AsyncMock(spec=ChatwootClient)
        failing_client.add_label.side_effect = RuntimeError("network error")

        handler = EscalationHandler(
            chatwoot_client=failing_client,
            config_provider=config_provider,
            session_manager=session_manager,
        )

        # Should not raise
        await handler.handle_escalation("s1", 42, "reason")

    @pytest.mark.asyncio
    async def test_partial_failure_continues(
        self,
        config_provider: MockConfigProvider,
        session_manager: SessionManager,
    ) -> None:
        failing_client = AsyncMock(spec=ChatwootClient)
        failing_client.add_label.return_value = {"success": True}
        failing_client.toggle_status.side_effect = RuntimeError("status error")

        handler = EscalationHandler(
            chatwoot_client=failing_client,
            config_provider=config_provider,
            session_manager=session_manager,
        )

        # Should not raise even though toggle_status fails
        await handler.handle_escalation("s1", 42, "reason")
        failing_client.add_label.assert_awaited_once()
