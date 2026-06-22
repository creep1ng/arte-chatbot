"""Greeting module for WhatsApp first-contact experience (P3).

Provides time-of-day greeting detection, first-contact detection,
and greeting prepend logic gated by configuration.

Dependencies:
- backend.app.config.settings (greeting_enabled, greeting_timezone)
- backend.app.session.session_manager (get_history)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config import settings
from backend.app.session import session_manager


_GREETING_TEMPLATE = (
    "{greeting}! Soy el asistente virtual de Arte Soluciones Energéticas. "
    "Puedo ayudarte con información sobre paneles solares, inversores, "
    "baterías y más. ¿En qué puedo ayudarte hoy?"
)


def _get_time_greeting(timezone_str: str) -> str:
    """Return time-of-day greeting string based on current hour in the given timezone.

    Args:
        timezone_str: IANA timezone string (e.g., "America/Bogota").

    Returns:
        One of "Buenos días", "Buenas tardes", or "Buenas noches".

    Raises:
        KeyError: If timezone_str is not a valid IANA timezone.
    """
    tz = ZoneInfo(timezone_str)
    hour = datetime.now(tz).hour
    if 6 <= hour < 12:
        return "Buenos días"
    elif 12 <= hour < 19:
        return "Buenas tardes"
    else:
        return "Buenas noches"


def is_first_contact(session_id: str) -> bool:
    """Check if this session has no conversation history.

    Args:
        session_id: The session identifier to check.

    Returns:
        True if the session has no prior turns, False otherwise.
    """
    return len(session_manager.get_history(session_id)) == 0


def maybe_prepend_greeting(
    session_id: str,
    response_text: str,
    intent_type: str,
    escalate: bool,
) -> str:
    """Prepend a greeting to the response if conditions are met.

    The greeting is prepended ONLY when ALL of the following are true:
    - greeting_enabled setting is True
    - escalate is False, except first-contact quote escalation
    - intent_type is not "fuera_de_dominio"
    - This is the first contact for the session

    Args:
        session_id: The session identifier.
        response_text: The LLM response text.
        intent_type: The classified intent type.
        escalate: Whether this is an escalation response.

    Returns:
        The response text, possibly with greeting prepended.
    """
    if not settings.greeting_enabled:
        return response_text
    if intent_type == "fuera_de_dominio":
        return response_text
    if escalate and intent_type != "escalate_quote":
        return response_text
    if not is_first_contact(session_id):
        return response_text

    greeting_base = _get_time_greeting(settings.greeting_timezone)
    greeting = _GREETING_TEMPLATE.format(greeting=greeting_base)
    return f"{greeting}\n\n{response_text}"
