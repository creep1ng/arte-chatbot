"""Intent analyzer module for the evaluation orchestrator.

Provides metrics for intent classification accuracy (US-05).
"""

from typing import Any

from evaluation.orchestrator.analyzers.base import BaseAnalyzer


class IntentAnalyzer(BaseAnalyzer):
    """Analyzer for intent classification metrics (US-05)."""

    INTENT_TYPES = {
        "FAQ",
        "product_info",
        "escalate_quote",
        "escalate_technical",
        "escalate_order",
    }

    @property
    def name(self) -> str:
        return "intent"

    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze intent classification accuracy.

        Args:
            raw_results: List of raw result dictionaries.

        Returns:
            Dictionary with intent classification metrics.
        """
        results_with_intent = [
            r for r in raw_results if r.get("expected_intent_type")
        ]

        if not results_with_intent:
            return {
                "total_with_intent": 0,
                "correct": 0,
                "accuracy": 0.0,
                "by_type": {},
            }

        correct = 0
        by_type: dict[str, dict[str, int]] = {}

        for r in results_with_intent:
            expected = r.get("expected_intent_type", "")
            if not expected:
                continue

            detected = self._extract_intent_type(r.get("response", ""))
            is_correct = self._is_intent_match(expected, detected)

            if is_correct:
                correct += 1

            if expected not in by_type:
                by_type[expected] = {"correct": 0, "total": 0}
            by_type[expected]["total"] += 1
            if is_correct:
                by_type[expected]["correct"] += 1

        total = len(results_with_intent)
        accuracy = (correct / total * 100) if total > 0 else 0.0

        type_accuracy = {}
        for intent_type, stats in by_type.items():
            type_accuracy[intent_type] = (
                (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
            )

        return {
            "total_with_intent": total,
            "correct": correct,
            "accuracy": round(accuracy, 2),
            "by_type": type_accuracy,
        }

    def _extract_intent_type(self, response: str) -> str:
        """Extract intent type from response text.

        This is a simplified implementation. In production, this would
        use LLM-based extraction or structured outputs.
        """
        response_lower = response.lower()

        if any(kw in response_lower for kw in ["cotización", "presupuesto", "precio"]):
            return "escalate_quote"
        if any(kw in response_lower for kw in ["técnico", "error", "revis", "problema"]):
            return "escalate_technical"
        if any(kw in response_lower for kw in ["pedido", "comprar", "adquirir"]):
            return "escalate_order"
        if any(kw in response_lower for kw in ["paneles", "inversor", "especificacion"]):
            return "product_info"

        return "FAQ"

    def _is_intent_match(self, expected: str, detected: str) -> bool:
        """Check if detected intent matches expected."""
        return expected == detected

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate summary of intent classification metrics."""
        lines = [
            "=== Intent Classification (US-05) ===",
            f"Total queries with intent: {analysis['total_with_intent']}",
            f"Correct: {analysis['correct']}",
            f"Accuracy: {analysis['accuracy']}%",
        ]
        if analysis.get("by_type"):
            lines.append("By intent type:")
            for intent_type, acc in analysis["by_type"].items():
                lines.append(f"  - {intent_type}: {acc}%")
        return "\n".join(lines)