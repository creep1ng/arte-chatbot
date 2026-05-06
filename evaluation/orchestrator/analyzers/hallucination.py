"""Hallucination analyzer module for the evaluation orchestrator.

Provides metrics for hallucination detection (US-07).
"""

from typing import Any

from evaluation.orchestrator.analyzers.base import BaseAnalyzer


class HallucinationAnalyzer(BaseAnalyzer):
    """Analyzer for hallucination detection metrics (US-07)."""

    @property
    def name(self) -> str:
        return "hallucination"

    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze hallucination rates in responses.

        Args:
            raw_results: List of raw result dictionaries.

        Returns:
            Dictionary with hallucination detection metrics.
        """
        results_with_response = [
            r for r in raw_results if r.get("response") and not r.get("error")
        ]

        if not results_with_response:
            return {
                "total_with_response": 0,
                "hallucination_count": 0,
                "hallucination_rate": 0.0,
            }

        hallucination_count = 0
        hallucination_details = []

        for r in results_with_response:
            response = r.get("response", "")
            sources = r.get("source_documents", [])

            has_hallucination = self._detect_hallucination(response, sources)

            if has_hallucination:
                hallucination_count += 1
                hallucination_details.append({
                    "query_id": r.get("query_id"),
                    "query": r.get("query"),
                })

        total = len(results_with_response)
        rate = (hallucination_count / total * 100) if total > 0 else 0.0

        return {
            "total_with_response": total,
            "hallucination_count": hallucination_count,
            "hallucination_rate": round(rate, 2),
            "details": hallucination_details[:10],
        }

    def _detect_hallucination(self, response: str, sources: list) -> bool:
        """Detect if response contains hallucinated information.

        This is a simplified heuristic-based detection. In production,
        this would use more sophisticated methods (LLM-based evaluation,
        grounding checks, etc.).

        Args:
            response: The chatbot's response text.
            sources: List of source documents used in the response.

        Returns:
            True if hallucination is detected, False otherwise.
        """
        if not sources:
            return True

        response_lower = response.lower()

        hallucination_indicators = [
            "no tengo información",
            "no puedo verificar",
            "no estoy seguro",
            "inventé",
            "fabricado",
        ]

        for indicator in hallucination_indicators:
            if indicator in response_lower:
                return True

        return False

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate summary of hallucination detection metrics."""
        lines = [
            "=== Hallucination Detection (US-07) ===",
            f"Total responses evaluated: {analysis['total_with_response']}",
            f"Hallucinations detected: {analysis['hallucination_count']}",
            f"Hallucination rate: {analysis['hallucination_rate']}%",
        ]
        if analysis.get("details"):
            lines.append("Sample hallucinations:")
            for detail in analysis["details"][:3]:
                lines.append(f"  - {detail['query_id']}: {detail['query'][:50]}...")
        return "\n".join(lines)