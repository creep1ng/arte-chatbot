"""Conservative byte guard for File Input requests."""

import logging

logger = logging.getLogger(__name__)


class ContextBudgetError(ValueError):
    """Raised before a File Input request that cannot fit its budget."""


def validate_file_input_size(
    *,
    file_size_bytes: int,
    max_file_size_bytes: int,
) -> None:
    """Reject files above the configured pre-upload byte ceiling."""
    is_accepted = file_size_bytes <= max_file_size_bytes
    reason = "accepted" if is_accepted else "file_size_exceeds_limit"
    logger.info(
        "File Input byte guard: file_size_bytes=%d max_file_size_bytes=%d "
        "is_accepted=%s reason=%s",
        file_size_bytes,
        max_file_size_bytes,
        is_accepted,
        reason,
    )
    if not is_accepted:
        raise ContextBudgetError(
            "File Input request rejected by context budget: "
            "file_size_exceeds_limit"
        )
