"""Prompt-based message splitting for WhatsApp conversational responses.

The LLM is instructed (via system prompt) to separate messages with `---`
delimiters. This module splits the response on those delimiters, validates
per-message character limits by intent, and optionally regenerates overflow
segments via a provided LLM callback.

No tool calls are involved — splitting is deterministic backend processing
over the LLM's markdown output.
"""

import logging
import random
from typing import Callable, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Delimiter: a line containing only `---` (with optional surrounding whitespace)
_DELIMITER_LINE = "---"

# Intents that should NOT trigger splitting
_NO_SPLIT_INTENTS = {
    "escalate_quote",
    "escalate_technical",
    "escalate_order",
    "fuera_de_dominio",
}

# Per-intent character limits for split messages
_INTENT_MAX_CHARS: dict[str, int] = {
    "FAQ": 300,
    "product_info": 800,
}


def split_response(text: str) -> list[str]:
    """Split response text on `---` delimiters.

    The delimiter must be on its own line (with optional surrounding whitespace).
    Embedded `---` within text (e.g., "3 paneles---de 400W") is NOT split.

    Args:
        text: Raw LLM response text.

    Returns:
        List of non-empty, stripped message segments.
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    segments: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        if line.strip() == _DELIMITER_LINE:
            # Found a delimiter — flush current segment
            segment = "\n".join(current_lines).strip()
            if segment:
                segments.append(segment)
            current_lines = []
        else:
            current_lines.append(line)

    # Flush remaining lines
    segment = "\n".join(current_lines).strip()
    if segment:
        segments.append(segment)

    return segments


def get_max_chars_for_intent(intent_type: str) -> Optional[int]:
    """Return the max character limit per message for a given intent.

    Args:
        intent_type: The classified intent type.

    Returns:
        Max characters, or None if no limit (escalation/out-of-domain).
    """
    return _INTENT_MAX_CHARS.get(intent_type)


def should_split_intent(intent_type: str) -> bool:
    """Determine if a given intent should trigger message splitting.

    Args:
        intent_type: The classified intent type.

    Returns:
        True if messages should be split for this intent.
    """
    return intent_type not in _NO_SPLIT_INTENTS


def build_regeneration_prompt(segment: str, max_chars: int) -> str:
    """Build a prompt to ask the LLM to shorten an over-length segment.

    Args:
        segment: The message text that exceeds the limit.
        max_chars: The target character limit.

    Returns:
        Prompt string for the LLM.
    """
    current_len = len(segment)
    return (
        f"El siguiente mensaje es demasiado largo ({current_len} caracteres). "
        f"Acórtalo a {max_chars} caracteres o menos manteniendo el contenido "
        f"esencial. Responde SOLO con el mensaje acortado, sin explicaciones:\n\n"
        f"{segment}"
    )


def process_split_messages(
    text: str,
    intent_type: str,
    llm_regenerate_fn: Optional[Callable[[str], str]] = None,
) -> tuple[list[str], list[int]]:
    """Process a response through the splitting pipeline.

    Args:
        text: The full LLM response text (already intent-extracted).
        intent_type: The classified intent type.
        llm_regenerate_fn: Optional callback to regenerate an over-length
            segment. Receives the regeneration prompt, returns shortened text.

    Returns:
        Tuple of (messages, delays_ms). If splitting is not applicable,
        returns ([], []).
    """
    if not settings.split_messages_enabled:
        return [], []

    if not should_split_intent(intent_type):
        return [], []

    segments = split_response(text)

    # No delimiters found → single message, no split needed
    if len(segments) <= 1:
        return [], []

    max_chars = get_max_chars_for_intent(intent_type)

    # Validate and regenerate over-length segments
    if max_chars is not None and llm_regenerate_fn is not None:
        for i, segment in enumerate(segments):
            if len(segment) > max_chars:
                logger.info(
                    "Segment %d exceeds limit (%d > %d chars), regenerating",
                    i,
                    len(segment),
                    max_chars,
                )
                prompt = build_regeneration_prompt(segment, max_chars)
                regenerated = llm_regenerate_fn(prompt)
                if regenerated and len(regenerated.strip()) > 0:
                    segments[i] = regenerated.strip()

    # Apply WhatsApp formatting per-segment if enabled
    if settings.whatsapp_formatter_enabled:
        from backend.app.whatsapp_formatter import format_for_whatsapp

        segments = [format_for_whatsapp(s) for s in segments]

    # Generate random delays within configured range
    min_delay = settings.msg_delay_min_ms
    max_delay = settings.msg_delay_max_ms
    delays = [random.randint(min_delay, max_delay) for _ in range(len(segments) - 1)]

    return segments, delays
