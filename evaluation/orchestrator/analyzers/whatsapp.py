"""WhatsApp analyzer module for the evaluation orchestrator.

Provides WhatsApp-specific metrics for the conversational channel:
- Formatting compliance (no forbidden markdown in responses)
- Message split quality (responses split into correct number of messages)
- Greeting coverage (first-contact sessions include a greeting)
- Multi-message coherence (joined responses are coherent)
- Buffer accuracy (multi-input messages correctly buffered and joined)
"""

import re
from typing import Any

from evaluation.orchestrator.analyzers.base import BaseAnalyzer

# Default forbidden markdown patterns that should not appear in WhatsApp responses.
# WhatsApp supports *bold*, _italic_, ~strikethrough~, and `monospace` only.
# These patterns represent standard markdown that renders poorly in WhatsApp.
DEFAULT_FORBIDDEN_PATTERNS: list[str] = [
    r"\*\*[^*]+\*\*",        # Bold with double asterisks: **text**
    r"__[^_]+__",             # Bold with double underscores: __text__
    r"~~[^~]+~~",             # Strikethrough with double tildes: ~~text~~
    r"```[\s\S]+?```",        # Fenced code blocks: ```text```
    r"^#{1,6}\s+.+",          # Markdown headers: # text
    r"^\s*[-*+]\s+.+",        # Unordered list items at line start
    r"^\s*\d+\.\s+.+",        # Ordered list items at line start
    r">\s+.+",                # Blockquotes at line start
    r"\[.+?\]\(https?://\S+\)",  # Markdown links: [text](url)
]

# Greeting patterns (Spanish) that indicate a proper first-contact greeting.
GREETING_PATTERNS: list[str] = [
    r"\bhola\b",
    r"\bbuen[oa]s?\s+(d[ií]as|tardes|noches)\b",
    r"\bbienvenid[oa]s?\b",
    r"\bsaludos\b",
    r"\bestimad[oa]\b",
]

# Thresholds for each metric (percentage).
METRIC_THRESHOLDS: dict[str, float] = {
    "wa_formatting_compliance": 98.0,
    "wa_message_split_quality": 85.0,
    "wa_greeting_coverage": 100.0,
    "wa_multi_message_coherence": 90.0,
    "wa_buffer_accuracy": 95.0,
}


class WhatsAppAnalyzer(BaseAnalyzer):
    """Analyzer for WhatsApp-specific conversational metrics.

    Processes only dataset entries that contain WhatsApp-specific fields
    (``input_messages`` or ``expected_greeting``). All metrics are ``wa_``
    prefixed for future multi-channel support.
    """

    @property
    def name(self) -> str:
        return "whatsapp"

    def _is_whatsapp_entry(self, result: dict[str, Any]) -> bool:
        """Detect if a result is a WhatsApp-specific dataset entry.

        An entry is WhatsApp-specific if it has ``input_messages`` (list)
        or ``expected_greeting`` (bool) fields.
        """
        has_input_messages = bool(result.get("input_messages"))
        has_greeting_field = result.get("expected_greeting") is not None
        return has_input_messages or has_greeting_field

    def _get_forbidden_patterns(
        self, result: dict[str, Any]
    ) -> list[str]:
        """Get merged forbidden patterns (defaults + per-entry)."""
        custom = result.get("forbidden_patterns", [])
        return DEFAULT_FORBIDDEN_PATTERNS + custom

    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze WhatsApp-specific metrics from raw results.

        Only processes entries detected as WhatsApp-specific. Returns
        zero-valued metrics when no WhatsApp entries are found.

        Args:
            raw_results: List of raw result dictionaries.

        Returns:
            Dictionary with ``wa_``-prefixed metrics and metadata.
        """
        wa_results = [r for r in raw_results if self._is_whatsapp_entry(r)]

        if not wa_results:
            return {
                "total_whatsapp_entries": 0,
                "successful_entries": 0,
                "wa_formatting_compliance": 0.0,
                "wa_message_split_quality": 0.0,
                "wa_greeting_coverage": 0.0,
                "wa_multi_message_coherence": 0.0,
                "wa_buffer_accuracy": 0.0,
            }

        successful = [r for r in wa_results if not r.get("error")]

        formatting = self._compute_formatting_compliance(successful)
        splitting = self._compute_message_split_quality(wa_results)
        greeting = self._compute_greeting_coverage(wa_results)
        coherence = self._compute_multi_message_coherence(wa_results)
        buffer_acc = self._compute_buffer_accuracy(wa_results)

        return {
            "total_whatsapp_entries": len(wa_results),
            "successful_entries": len(successful),
            "wa_formatting_compliance": formatting,
            "wa_message_split_quality": splitting,
            "wa_greeting_coverage": greeting,
            "wa_multi_message_coherence": coherence,
            "wa_buffer_accuracy": buffer_acc,
        }

    # ------------------------------------------------------------------
    # Metric computations
    # ------------------------------------------------------------------

    def _compute_formatting_compliance(
        self, results: list[dict[str, Any]]
    ) -> float:
        """Compute the formatting compliance rate.

        Formula: 1 - (count responses with forbidden markdown / total responses).

        A response is non-compliant if it matches ANY forbidden pattern
        (default patterns merged with per-entry ``forbidden_patterns``).
        """
        if not results:
            return 100.0

        violation_count = 0
        for r in results:
            response = r.get("response", "")
            patterns = self._get_forbidden_patterns(r)

            for pattern in patterns:
                if re.search(pattern, response, re.MULTILINE):
                    violation_count += 1
                    break  # Count at most one violation per response

        return round((1 - violation_count / len(results)) * 100, 2)

    def _compute_message_split_quality(
        self, results: list[dict[str, Any]]
    ) -> float:
        """Compute message split quality rate.

        Compares actual message count (split by double-newline or ``---``
        separators) against ``expected_message_count`` from the dataset.
        Only evaluates entries that have ``expected_message_count`` set.
        """
        split_eligible = [
            r for r in results if r.get("expected_message_count")
        ]

        if not split_eligible:
            return 100.0

        correct = 0
        for r in split_eligible:
            response = r.get("response", "")
            expected = r.get("expected_message_count", 1)
            actual = self._count_response_messages(response)

            if actual == expected:
                correct += 1

        return round(correct / len(split_eligible) * 100, 2)

    def _compute_greeting_coverage(
        self, results: list[dict[str, Any]]
    ) -> float:
        """Compute greeting coverage for first-contact sessions.

        Checks if responses marked with ``expected_greeting: true`` contain
        a recognizable greeting pattern.
        """
        greeting_expected = [
            r for r in results if r.get("expected_greeting") is True
        ]

        if not greeting_expected:
            return 100.0

        with_greeting = 0
        for r in greeting_expected:
            response = r.get("response", "")
            if self._contains_greeting(response):
                with_greeting += 1

        return round(with_greeting / len(greeting_expected) * 100, 2)

    def _compute_multi_message_coherence(
        self, results: list[dict[str, Any]]
    ) -> float:
        """Compute multi-message coherence rate.

        For entries with ``input_messages``, checks that the response is
        coherent: non-empty, addresses the query, and is not fragmented
        into disconnected fragments.
        """
        multi_input = [r for r in results if r.get("input_messages")]

        if not multi_input:
            return 100.0

        coherent = 0
        for r in multi_input:
            if r.get("error"):
                continue
            response = r.get("response", "")
            if self._is_coherent_response(response, r):
                coherent += 1

        return round(coherent / len(multi_input) * 100, 2)

    def _compute_buffer_accuracy(
        self, results: list[dict[str, Any]]
    ) -> float:
        """Compute buffer accuracy rate.

        For entries with ``input_messages``, verifies the system correctly
        buffered multiple messages and produced a meaningful combined response.
        """
        multi_input = [r for r in results if r.get("input_messages")]

        if not multi_input:
            return 100.0

        correct = 0
        for r in multi_input:
            if r.get("error"):
                continue
            response = r.get("response", "")
            input_msgs = r.get("input_messages", [])
            if self._is_correctly_buffered(response, input_msgs):
                correct += 1

        return round(correct / len(multi_input) * 100, 2)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_response_messages(response: str) -> int:
        """Count the number of logical messages in a response.

        Messages are split by double-newline boundaries or explicit
        ``---`` separators. Returns at least 1.
        """
        if not response or not response.strip():
            return 0

        # Split by double+ newlines or explicit separator lines
        parts = re.split(r"\n\n+|^---\s*$", response.strip(), flags=re.MULTILINE)
        non_empty = [p.strip() for p in parts if p.strip()]
        return max(len(non_empty), 1)

    @staticmethod
    def _contains_greeting(response: str) -> bool:
        """Check if a response contains a recognizable greeting."""
        if not response:
            return False
        return any(
            re.search(pattern, response, re.IGNORECASE)
            for pattern in GREETING_PATTERNS
        )

    @staticmethod
    def _is_coherent_response(
        response: str, result: dict[str, Any]
    ) -> bool:
        """Heuristic check for response coherence.

        A coherent response is non-empty, has reasonable length, and does
        not contain obvious signs of fragmentation or error.
        """
        if not response or len(response.strip()) < 10:
            return False

        # Response should not be just an error or acknowledgment
        lower = response.lower()
        incoherent_signals = [
            "error",
            "no entiendo",
            "no puedo responder",
        ]
        for signal in incoherent_signals:
            if lower.strip() == signal:
                return False

        return True

    @staticmethod
    def _is_correctly_buffered(
        response: str, input_messages: list[str]
    ) -> bool:
        """Heuristic check for correct buffering and joining.

        A correctly buffered response is non-empty, has no errors, and
        addresses content from the multi-message input.
        """
        if not response or not response.strip():
            return False

        if not input_messages:
            return False

        # Minimum quality: response exists, is non-trivial, and
        # input_messages were successfully consumed (non-empty list).
        return len(response.strip()) > 10 and len(input_messages) > 0

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate a human-readable summary of WhatsApp metrics."""
        if analysis.get("total_whatsapp_entries", 0) == 0:
            return "=== WhatsApp Metrics ===\nNo WhatsApp-specific entries found in dataset"

        lines = [
            "=== WhatsApp Metrics ===",
            f"Total WhatsApp entries: {analysis['total_whatsapp_entries']}",
            f"Successful: {analysis['successful_entries']}",
            "",
        ]

        for metric, threshold in METRIC_THRESHOLDS.items():
            value = analysis.get(metric, 0.0)
            status = "✓" if value >= threshold else "✗"
            lines.append(
                f"  {status} {metric}: {value:.2f}% (threshold: ≥{threshold}%)"
            )

        return "\n".join(lines)
