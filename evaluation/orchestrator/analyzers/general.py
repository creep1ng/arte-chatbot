"""General analyzer module for the evaluation orchestrator.

Provides general metrics: latency, success rate, error distribution.
"""

from typing import Any

from evaluation.orchestrator.analyzers.base import BaseAnalyzer


class GeneralAnalyzer(BaseAnalyzer):
    """Analyzer for general performance metrics."""

    @property
    def name(self) -> str:
        return "general"

    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze general performance metrics.

        Args:
            raw_results: List of raw result dictionaries.

        Returns:
            Dictionary with general metrics (latency, success, errors).
        """
        if not raw_results:
            return {
                "total_queries": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0,
            }

        total = len(raw_results)
        successful = sum(1 for r in raw_results if not r.get("error"))
        failed = total - successful

        latencies = [r["latency_ms"] for r in raw_results if r.get("latency_ms", 0) > 0]

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        min_latency = min(latencies) if latencies else 0.0
        max_latency = max(latencies) if latencies else 0.0

        errors = [r["error"] for r in raw_results if r.get("error")]
        error_types: dict[str, int] = {}
        for err in errors:
            err_key = err.split(":")[0] if err else "Unknown"
            error_types[err_key] = error_types.get(err_key, 0) + 1

        return {
            "total_queries": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "error_count": len(errors),
            "error_types": error_types,
        }

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate summary of general metrics."""
        lines = [
            "=== General Metrics ===",
            f"Total queries: {analysis['total_queries']}",
            f"Successful: {analysis['successful']} ({analysis['success_rate']:.1f}%)",
            f"Failed: {analysis['failed']}",
            f"Latency - Avg: {analysis['avg_latency_ms']}ms, "
            f"Min: {analysis['min_latency_ms']}ms, Max: {analysis['max_latency_ms']}ms",
        ]
        if analysis.get("error_count", 0) > 0:
            lines.append(f"Errors: {analysis['error_count']}")
            for err_type, count in analysis.get("error_types", {}).items():
                lines.append(f"  - {err_type}: {count}")
        return "\n".join(lines)