from copy import deepcopy

import pytest

from evaluation.harness.quality import (
    HALLUCINATION_DETECTOR,
    INFRASTRUCTURE_FAILURE,
    QUALITY_FAILURE,
    QUALITY_PASS,
    build_quality_gate,
    calculate_metrics,
    evaluate_quality,
    quality_exit_code,
)

POLICY = {
    "version": "test",
    "status": "test",
    "hallucination_detector": {"name": HALLUCINATION_DETECTOR},
    "checks": [
        {"metric": metric, "operator": operator, "threshold": limit, "required": True}
        for metric, operator, limit in (
            ("failed_query_rate_percent", "<=", 5),
            ("escalation_accuracy_percent", ">=", 90),
            ("hallucination_rate_percent", "<=", 20),
            ("p95_latency_ms", "<=", 5000),
        )
    ],
}


def _metrics(**overrides: float) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {
        "failed_query_rate_percent": 0.0,
        "escalation_accuracy_percent": 100.0,
        "hallucination_rate_percent": 0.0,
        "p95_latency_ms": 100.0,
    }
    metrics.update(overrides)
    return metrics


def _result(**overrides: object) -> dict[str, object]:
    result = dict(
        response="Hola",
        source_documents=[],
        num_sources=0,
        latency_ms=100.0,
        should_escalate=False,
        escalated=False,
        error="",
    )
    result.update(overrides)
    return result


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        (_metrics(), QUALITY_PASS),
        (
            _metrics(
                failed_query_rate_percent=5,
                escalation_accuracy_percent=90,
                hallucination_rate_percent=20,
                p95_latency_ms=5000,
            ),
            QUALITY_PASS,
        ),
        (_metrics(escalation_accuracy_percent=89.99), QUALITY_FAILURE),
    ],
    ids=("safe", "inclusive-boundary", "required-failure"),
)
def test_required_quality_checks(
    metrics: dict[str, float | None], expected: int
) -> None:
    checks = evaluate_quality(metrics, POLICY)
    gate = {
        "infrastructure_errors": [],
        "quality_failures": [check for check in checks if check["status"] == "fail"],
    }
    assert quality_exit_code(gate) == expected


def test_metrics_recomputed_from_raw_rows() -> None:
    results = [
        _result(
            response=response,
            latency_ms=latency,
            should_escalate=escalated,
            escalated=escalated,
        )
        for response, latency, escalated in (
            ("El panel entrega 500 W.", 100.0, False),
            ("Hola, podemos ayudarte.", 200.0, True),
        )
    ]

    metrics = calculate_metrics(results)

    assert metrics == {
        "failed_query_rate_percent": 0.0,
        "escalation_accuracy_percent": 100.0,
        "hallucination_rate_percent": 50.0,
        "p95_latency_ms": 200.0,
    }


def test_advisory_failure_does_not_fail_gate() -> None:
    policy = deepcopy(POLICY)
    policy["checks"][1]["required"] = False
    _, gate = build_quality_gate([_result(query_id="q1", should_escalate=True)], policy)

    assert gate["checks"][1]["status"] == "fail"
    assert quality_exit_code(gate) == QUALITY_PASS


def test_infrastructure_errors_are_distinct_and_take_precedence() -> None:
    _, gate = build_quality_gate(
        [{"query_id": "q1", "error": "Connection error", "latency_ms": 0}],
        POLICY,
    )

    assert gate["quality_failures"][0]["metric"] == "failed_query_rate_percent"
    assert gate["infrastructure_errors"][0] == {
        "query_id": "q1",
        "error": "Connection error",
    }
    assert quality_exit_code(gate) == INFRASTRUCTURE_FAILURE
