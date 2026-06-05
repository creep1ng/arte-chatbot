"""Admin dashboard metrics endpoints."""

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import DashboardMetrics
from backend.app.config import settings
from backend.app.conversation_logger import ConversationLogEntry
from backend.app.s3_client import S3Client
from backend.app.session import session_manager

logger = logging.getLogger(__name__)

dashboard_router = APIRouter()
s3_client = S3Client()
MAX_LOG_OBJECTS = 1000


def _parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO 8601 timestamp from conversation logs.

    Args:
        value: Timestamp string, usually ending in ``Z``.

    Returns:
        Timezone-aware datetime, or None if parsing fails.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _load_recent_log_entries() -> list[ConversationLogEntry]:
    """Load recent conversation log entries from S3 for dashboard metrics.

    The MVP intentionally performs a bounded scan over the conversations prefix.
    This keeps Slice 3 simple and safe; larger installations should replace this
    with precomputed aggregates or S3 inventory/Athena.
    """
    prefix = f"{settings.conversation_log_prefix}/"
    objects = await s3_client.list_objects(prefix=prefix)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    entries: list[ConversationLogEntry] = []
    for obj in objects[:MAX_LOG_OBJECTS]:
        key = obj.get("Key", "")
        if not key.endswith(".json"):
            continue
        try:
            data = await asyncio.to_thread(s3_client.download_pdf, key)
            entry = ConversationLogEntry.model_validate_json(data)
        except Exception:
            logger.debug("Skipping unreadable conversation log: %s", key)
            continue

        timestamp = _parse_timestamp(entry.timestamp)
        if timestamp is None or timestamp < cutoff:
            continue
        entries.append(entry)

    return entries


def _aggregate_log_metrics(
    entries: list[ConversationLogEntry],
) -> tuple[float, dict[str, int]]:
    """Aggregate escalation rate and intent distribution from log entries."""
    if not entries:
        return (
            session_manager.get_escalation_rate(),
            session_manager.get_intent_distribution(),
        )

    escalated_count = sum(1 for entry in entries if entry.escalate)
    intent_distribution = Counter(entry.intent_type for entry in entries)
    return escalated_count / len(entries), dict(intent_distribution)


@dashboard_router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> DashboardMetrics:
    """Return aggregated operational metrics for the admin dashboard.

    Returns:
        DashboardMetrics with active sessions, token totals, escalation rate,
        and intent distribution.
    """
    token_totals = session_manager.get_all_token_totals()
    try:
        entries = await _load_recent_log_entries()
        escalation_rate, intent_distribution = _aggregate_log_metrics(entries)
    except Exception as e:
        logger.error("Failed to aggregate dashboard logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate dashboard metrics",
        ) from e

    return DashboardMetrics(
        active_sessions=session_manager.get_session_count(),
        total_input_tokens=token_totals.input_tokens,
        total_output_tokens=token_totals.output_tokens,
        total_tokens=token_totals.total_tokens,
        escalation_rate=escalation_rate,
        intent_distribution=intent_distribution,
    )
