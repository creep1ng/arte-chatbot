"""Escalation handler for human agent handoff via Chatwoot.

Orchestrates labeling, status changes, assignment, and user notification
when a conversation needs to be escalated to a human agent.
"""

import logging
from typing import Optional

from backend.app.chatwoot_client import ChatwootClient
from backend.app.config_provider import ConfigProvider
from backend.app.session import SessionManager

logger = logging.getLogger(__name__)

DEFAULT_ESCALATION_MESSAGE = (
    "Entiendo que necesitas asistencia personalizada. "
    "Un agente de ventas te contactará pronto para ayudarte con tu consulta."
)

_INTENT_LABEL_MAP = {
    "escalate_quote": "quote",
    "escalate_technical": "technical",
    "escalate_order": "order",
}


class EscalationHandler:
    """Handles escalation workflows via the Chatwoot Application API.

    Args:
        chatwoot_client: Async client for Chatwoot HTTP operations.
        config_provider: Runtime configuration provider.
        session_manager: Session manager for storing escalation metadata.
    """

    def __init__(
        self,
        chatwoot_client: ChatwootClient,
        config_provider: ConfigProvider,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self._client = chatwoot_client
        self._config = config_provider
        self._session = session_manager

    async def escalate_to_human(
        self, conversation_id: int, reason: str, intent_type: str
    ) -> bool:
        """Escalate a Chatwoot conversation to a human agent.

        Args:
            conversation_id: Chatwoot conversation identifier.
            reason: Human-readable escalation reason for logs/notes.
            intent_type: Intent classifier label that triggered handoff.

        Returns:
            True when the critical handoff actions succeeded, False otherwise.
        """
        del reason
        labels = [self._config.get_label("escalated")]
        intent_label_name = _INTENT_LABEL_MAP.get(intent_type)
        if intent_label_name is not None:
            labels.append(self._config.get_label(intent_label_name))

        for label in labels:
            try:
                await self._client.add_label(conversation_id, label)
            except Exception as exc:
                logger.warning(
                    "Non-critical escalation label failed: conversation_id=%s, label=%s, error=%s",
                    conversation_id,
                    label,
                    exc,
                )

        try:
            await self._client.toggle_status(conversation_id, "open")
            team_id = self._config.get_handoff_target()
            if team_id is not None:
                await self._client.assign_conversation(conversation_id, team_id=team_id)
            await self._client.send_message(conversation_id, DEFAULT_ESCALATION_MESSAGE)
            return True
        except Exception as exc:
            logger.error(
                "Critical escalation action failed: conversation_id=%s, error=%s",
                conversation_id,
                exc,
            )
            return False

    async def handle_escalation(
        self,
        session_id: str,
        conversation_id: int,
        reason: str,
    ) -> None:
        """Execute the full escalation handoff workflow.

        Steps:
            1. Add ``escalated`` label to the conversation.
            2. Toggle conversation status to ``open``.
            3. Assign conversation to the configured handoff team.
            4. Send the default escalation message to the user.
            5. Store the escalation reason in the session manager.

        All Chatwoot API errors are logged but not re-raised so the bot
        does not crash on transient failures.

        Args:
            session_id: Internal session identifier.
            conversation_id: Chatwoot conversation ID.
            reason: Human-readable escalation reason.
        """
        label = self._config.get_label("escalated")
        team_id = self._config.get_handoff_target()

        try:
            await self._client.add_label(conversation_id, label)
        except Exception as exc:
            logger.error(
                "Failed to add escalation label: conversation_id=%s, error=%s",
                conversation_id,
                exc,
            )

        try:
            await self._client.toggle_status(conversation_id, "open")
        except Exception as exc:
            logger.error(
                "Failed to toggle conversation status: conversation_id=%s, error=%s",
                conversation_id,
                exc,
            )

        if team_id is not None:
            try:
                await self._client.assign_conversation(conversation_id, team_id=team_id)
            except Exception as exc:
                logger.error(
                    "Failed to assign conversation: conversation_id=%s, team_id=%s, error=%s",
                    conversation_id,
                    team_id,
                    exc,
                )

        try:
            await self._client.send_message(conversation_id, DEFAULT_ESCALATION_MESSAGE)
        except Exception as exc:
            logger.error(
                "Failed to send escalation message: conversation_id=%s, error=%s",
                conversation_id,
                exc,
            )

        # Store escalation reason in session for audit/debugging
        try:
            if self._session is not None:
                self._session.set_user_profile(session_id, f"escalated:{reason}")
        except Exception as exc:
            logger.error(
                "Failed to store escalation reason: session_id=%s, error=%s",
                session_id,
                exc,
            )

    async def handle_escalation_by_intent(
        self,
        session_id: str,
        conversation_id: int,
        intent_type: str,
    ) -> bool:
        """Map an intent type to a label and trigger escalation.

        Supported intents:
            - ``escalate_quote`` → ``quote`` label
            - ``escalate_technical`` → ``technical`` label
            - ``escalate_order`` → ``order`` label

        Args:
            session_id: Internal session identifier.
            conversation_id: Chatwoot conversation ID.
            intent_type: Intent classification result.

        Returns:
            ``True`` if escalation was triggered, ``False`` for unknown intents.
        """
        label_name = _INTENT_LABEL_MAP.get(intent_type)
        if label_name is None:
            logger.warning(
                "Unknown escalation intent: session_id=%s, intent_type=%s",
                session_id,
                intent_type,
            )
            return False

        label = self._config.get_label(label_name)
        try:
            await self._client.add_label(conversation_id, label)
        except Exception as exc:
            logger.error(
                "Failed to add intent label: conversation_id=%s, label=%s, error=%s",
                conversation_id,
                label,
                exc,
            )

        await self.handle_escalation(session_id, conversation_id, intent_type)
        return True
