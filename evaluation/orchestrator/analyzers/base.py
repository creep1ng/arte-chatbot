"""Base analyzer module for the evaluation orchestrator.

Defines the interface for all analyzers that process evaluation results.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseAnalyzer(ABC):
    """Abstract base class for all analyzers.

    Analyzers take raw evaluation results and produce metrics/reports
    for a specific aspect of the chatbot's performance.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the analyzer name."""
        pass

    @abstractmethod
    def analyze(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze raw results and return metrics.

        Args:
            raw_results: List of raw result dictionaries from query execution.

        Returns:
            Dictionary containing analysis metrics and any relevant data.
        """
        pass

    def summarize(self, analysis: dict[str, Any]) -> str:
        """Generate a human-readable summary of the analysis.

        Args:
            analysis: The analysis dictionary returned by analyze().

        Returns:
            String containing a formatted summary of the analysis.
        """
        return f"{self.name}: Analysis complete"