"""Pure quality-policy evaluation for harness result rows."""

import json
import operator
import re
from pathlib import Path
from typing import Any, Callable

QUALITY_PASS = 0
QUALITY_FAILURE = 1
INFRASTRUCTURE_FAILURE = 2

HALLUCINATION_DETECTOR = "unsupported_technical_numeric_claims_v1"
_TECHNICAL_VALUE_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:kwh|kw|w|v|a|ah|%|°c)(?=\s|[.,;:!?)]|$)",
    re.IGNORECASE,
)
_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "<": operator.lt,
    ">": operator.gt,
    "==": operator.eq,
}
_METRICS = (
    "failed_query_rate_percent",
    "escalation_accuracy_percent",
    "hallucination_rate_percent",
    "p95_latency_ms",
)


class QualityConfigurationError(ValueError):
    pass


def load_policy(path: Path) -> dict[str, Any]:
    """Load and validate a committed quality policy."""
    try:
        with path.open(encoding="utf-8") as policy_file:
            policy = json.load(policy_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityConfigurationError(
            f"Cannot load quality policy {path}: {exc}"
        ) from exc

    validate_policy(policy)
    return policy


def validate_policy(policy: Any) -> None:
    """Validate required policy metadata and check definitions."""
    if not isinstance(policy, dict):
        raise QualityConfigurationError("Quality policy must be a JSON object")
    if policy.get("schema_version") != 1:
        raise QualityConfigurationError("Policy schema_version must be 1")
    for field in ("version", "status"):
        if not isinstance(policy.get(field), str) or not policy[field]:
            raise QualityConfigurationError(
                f"Policy {field} must be a non-empty string"
            )

    detector = policy.get("hallucination_detector", {})
    if not isinstance(detector, dict):
        raise QualityConfigurationError("Hallucination detector must be an object")
    if detector.get("name") != HALLUCINATION_DETECTOR:
        raise QualityConfigurationError(
            f"Unsupported hallucination detector: {detector.get('name')!r}"
        )

    checks = policy.get("checks")
    if not isinstance(checks, list) or not checks:
        raise QualityConfigurationError("Policy checks must be a non-empty list")

    seen: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise QualityConfigurationError("Each policy check must be an object")
        metric = check.get("metric")
        if not isinstance(metric, str) or metric not in _METRICS:
            raise QualityConfigurationError(f"Unsupported policy metric: {metric!r}")
        if metric in seen:
            raise QualityConfigurationError(f"Duplicate policy metric: {metric}")
        seen.add(metric)
        if check.get("operator") not in _OPERATORS:
            raise QualityConfigurationError(
                f"Unsupported operator for {metric}: {check.get('operator')!r}"
            )
        threshold = check.get("threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise QualityConfigurationError(f"Threshold for {metric} must be numeric")
        if not isinstance(check.get("required"), bool):
            raise QualityConfigurationError(
                f"Required flag for {metric} must be boolean"
            )

    if missing := set(_METRICS) - seen:
        raise QualityConfigurationError(
            f"Policy is missing checks: {', '.join(sorted(missing))}"
        )


def normalize_source_documents(source_documents: Any) -> str:
    """Serialize heterogeneous source metadata deterministically for reports."""
    if source_documents in (None, ""):
        return ""
    if isinstance(source_documents, str):
        return source_documents
    return json.dumps(source_documents, ensure_ascii=False, sort_keys=True)


def _source_support(source_documents: Any, num_sources: int) -> tuple[bool, str]:
    """Return whether source references exist and any inspectable source text."""
    if not source_documents:
        return num_sources > 0, ""

    if isinstance(source_documents, dict):
        source_documents = [source_documents]

    keys = ("content", "contenido", "contenido_relevante", "text")
    parts = [
        value
        for source in source_documents
        if isinstance(source, dict)
        for key in keys
        if isinstance((value := source.get(key)), str) and value.strip()
    ]
    return True, " ".join(parts)


def _technical_values(text: str) -> set[str]:
    return {
        claim.lower().replace(",", ".")
        for claim in _TECHNICAL_VALUE_PATTERN.findall(text)
    }


def has_unsupported_technical_numeric_claim(result: dict[str, Any]) -> bool:
    """Detect unsupported technical numeric claims without flagging normal prose."""
    claims = _technical_values(str(result.get("response", "")))
    if not claims:
        return False

    raw_num_sources = result.get("num_sources", 0)
    try:
        num_sources = int(raw_num_sources)
    except (TypeError, ValueError):
        num_sources = 0

    has_sources, source_text = _source_support(
        result.get("source_documents", []), num_sources
    )
    if not has_sources:
        return True
    if not source_text:
        return False

    return not claims.issubset(_technical_values(source_text))


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, (95 * len(values) + 99) // 100 - 1)]


def _percent(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 2) if denominator else None


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, float | None]:
    """Calculate gate metrics exclusively from raw result rows."""
    if not results:
        return dict.fromkeys(_METRICS)

    successful = [result for result in results if not result.get("error")]
    correct = sum(
        result.get("should_escalate", False) == result.get("escalated", False)
        for result in successful
    )
    hallucinations = sum(map(has_unsupported_technical_numeric_claim, successful))
    latencies = [
        float(value)
        for result in successful
        if isinstance((value := result.get("latency_ms")), (int, float))
        and not isinstance(value, bool)
        and value >= 0
    ]

    return {
        "failed_query_rate_percent": _percent(
            len(results) - len(successful), len(results)
        ),
        "escalation_accuracy_percent": _percent(correct, len(successful)),
        "hallucination_rate_percent": _percent(hallucinations, len(successful)),
        "p95_latency_ms": round(p95, 2)
        if (p95 := _p95(latencies)) is not None
        else None,
    }


def evaluate_quality(
    metrics: dict[str, float | None], policy: dict[str, Any]
) -> list[dict[str, Any]]:
    """Evaluate calculated metrics against explicit policy operators."""
    checks: list[dict[str, Any]] = []
    for definition in policy["checks"]:
        metric = definition["metric"]
        observed = metrics.get(metric)
        passed = observed is not None and _OPERATORS[definition["operator"]](
            observed, float(definition["threshold"])
        )
        checks.append(
            {
                "metric": metric,
                "observed": observed,
                "operator": definition["operator"],
                "threshold": definition["threshold"],
                "required": definition["required"],
                "status": "pass"
                if passed
                else "fail"
                if observed is not None
                else "unavailable",
            }
        )
    return checks


def build_quality_gate(
    results: list[dict[str, Any]], policy: dict[str, Any]
) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Build metrics and a structured quality gate from raw results."""
    metrics = calculate_metrics(results)
    checks = evaluate_quality(metrics, policy)
    infrastructure_errors = [
        {
            "query_id": result.get("query_id", "unknown"),
            "error": str(result["error"]),
        }
        for result in results
        if result.get("error")
    ]
    infrastructure_errors.extend(
        {
            "metric": check["metric"],
            "error": "Required metric is unavailable from raw results",
        }
        for check in checks
        if check["required"] and check["status"] == "unavailable"
    )
    return metrics, {
        "policy_version": policy["version"],
        "policy_status": policy["status"],
        "hallucination_detector": policy["hallucination_detector"]["name"],
        "checks": checks,
        "quality_failures": [
            check for check in checks if check["required"] and check["status"] == "fail"
        ],
        "infrastructure_errors": infrastructure_errors,
    }


def quality_exit_code(quality_gate: dict[str, Any]) -> int:
    """Map gate outcomes to stable process exit codes."""
    if quality_gate["infrastructure_errors"]:
        return INFRASTRUCTURE_FAILURE
    if quality_gate["quality_failures"]:
        return QUALITY_FAILURE
    return QUALITY_PASS
