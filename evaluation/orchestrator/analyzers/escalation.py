"""Escalation analyzer module for the evaluation orchestrator.

Provides metrics for escalation detection accuracy (US-10).
"""

from typing import Any

from evaluation.orchestrator.analyzers.base import BaseAnalyzer


class EscalationAnalyzer(BaseAnalyzer):
    """Analyzer for escalation detection metrics (US-10)."""

    @property
    def name(self) -> str:
        return "escalation"

    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze escalation detection accuracy.

        Args:
            raw_results: List of raw result dictionaries.

        Returns:
            Dictionary with escalation detection metrics (FP/FN rates).
        """
        results_with_escalation = [
            r for r in raw_results if r.get("should_escalate") is not None
        ]

        if not results_with_escalation:
            return {
                "total_with_escalation": 0,
                "true_positives": 0,
                "true_negatives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
            }

        tp = 0
        tn = 0
        fp = 0
        fn = 0

        for r in results_with_escalation:
            expected = r.get("should_escalate", False)
            actual = r.get("escalated", False)

            if expected and actual:
                tp += 1
            elif not expected and not actual:
                tn += 1
            elif not expected and actual:
                fp += 1
            else:
                fn += 1

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return {
            "total_with_escalation": len(results_with_escalation),
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision * 100, 2),
            "recall": round(recall * 100, 2),
            "f1_score": round(f1 * 100, 2),
        }

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate summary of escalation detection metrics."""
        lines = [
            "=== Escalation Detection (US-10) ===",
            f"Total queries: {analysis['total_with_escalation']}",
            f"True Positives: {analysis['true_positives']}",
            f"True Negatives: {analysis['true_negatives']}",
            f"False Positives: {analysis['false_positives']}",
            f"False Negatives: {analysis['false_negatives']}",
            f"Precision: {analysis['precision']}%",
            f"Recall: {analysis['recall']}%",
            f"F1 Score: {analysis['f1_score']}%",
        ]
        return "\n".join(lines)