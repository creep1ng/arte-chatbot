"""Mock data generator for evaluation reports.

Generates simulated evaluation data for testing the quality report
notebook when real S3 data is not available.
"""

import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np


def generate_harness_results(
    sprint: str,
    num_queries: int = 50,
    base_latency: float = 2500.0,
    latency_std: float = 800.0,
    escalation_rate: float = 0.15,
    error_rate: float = 0.05,
    git_commit: str = "abc1234",
) -> dict:
    """Generate mock harness evaluation results.

    Args:
        sprint: Sprint identifier (e.g., "sprint_2", "sprint_5").
        num_queries: Number of queries to simulate.
        base_latency: Base average latency in ms.
        latency_std: Standard deviation of latency.
        escalation_rate: Expected escalation rate (0-1).
        error_rate: Error rate (0-1).
        git_commit: Git commit hash.

    Returns:
        Dictionary with mock harness results.
    """
    random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))
    np.random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))

    timestamps = [
        (datetime.now(timezone.utc) - timedelta(hours=num_queries - i)).isoformat()
        for i in range(num_queries)
    ]

    results = []
    escalated_count = 0
    expected_escalated = int(num_queries * escalation_rate)
    should_escalate_indices = random.sample(
        range(num_queries), min(expected_escalated, num_queries)
    )

    query_templates = [
        ("¿Cuánto cuesta un panel solar de 500W?", "info_precio", False),
        ("Necesito instalar paneles en mi casa de 100m2", "asesoramiento", True),
        ("¿Qué garantías tiene el panel?", "info_garantia", False),
        ("Tengo un problema con mi inversor", "soporte_tecnico", True),
        (
            "¿Cuántos paneles necesito para una casa de 3 habitaciones?",
            "asesoramiento",
            True,
        ),
        ("¿El panel de 550W es más eficiente que el de 500W?", "info_tecnica", False),
        ("Quiero una cotización para un proyecto comercial", "cotizacion", True),
        ("¿Cómo funciona el net metering?", "info_general", False),
        ("Mi inversor muestra error E01", "soporte_tecnico", True),
        (
            "¿Qué diferencia hay entre panel monocristalino y policristalino?",
            "info_tecnica",
            False,
        ),
    ]

    for i in range(num_queries):
        template = query_templates[i % len(query_templates)]
        query_id = f"q{i + 1:03d}"

        latency = max(100, np.random.normal(base_latency, latency_std))
        has_error = random.random() < error_rate

        if has_error:
            escalated = False
            should_escalate = template[2]
            response = ""
            error = "Connection timeout" if random.random() < 0.5 else "HTTP 500"
            session_id = ""
        else:
            error = ""
            should_escalate = template[2]
            escalated = should_escalate and (
                i in should_escalate_indices or random.random() < 0.7
            )
            escalated_count += 1 if escalated else 0

            response_templates = {
                "info_precio": f"El panel solar de {500 + (i % 5) * 50}W tiene un precio aproximado de ${350 + (i % 3) * 50} USD. ¿Te gustaría una cotización más detallada?",
                "asesoramiento": "Para tu proyecto, recomendaría una evaluación técnica in situ. ¿Podemos escalar tu consulta a nuestro equipo de ventas?",
                "info_garantia": f"El panel incluye garantía de {10 + (i % 5)} años contra defectos de fabricación y {25 + (i % 5)} años de garantía de rendimiento.",
                "soporte_tecnico": "Entiendo el problema. Voy a escalar tu caso a nuestro equipo técnico para un diagnóstico más detallado.",
                "info_tecnica": f"El panel de {500 + (i % 5) * 50}W tiene una eficiencia del {19 + (i % 3) * 0.5}%, con células de {i % 2 + 5}Bus.",
                "cotizacion": "Para un proyecto comercial necesito conocer más detalles. ¿Podemos agendar una llamada con nuestro equipo de ventas?",
                "info_general": "El net metering te permite inyectar el excedente de energía a la red y recibir créditos en tu factura.",
            }
            response = response_templates.get(
                template[1],
                "Gracias por tu consulta. ¿Hay algo más en lo que pueda ayudarte?",
            )
            session_id = f"sess_{random.randint(10000, 99999)}"

        result = {
            "query_id": query_id,
            "query": template[0],
            "expected_intent": template[1],
            "should_escalate": should_escalate,
            "response": response,
            "session_id": session_id,
            "latency_ms": round(latency, 2),
            "escalated": escalated,
            "error": error,
            "timestamp": timestamps[i],
            "num_sources": random.randint(0, 3) if not error else 0,
            "source_documents": [
                f"raw/paneles/modelo_{j}.pdf" for j in range(random.randint(0, 3))
            ],
        }
        results.append(result)

    total_queries = len(results)
    successful = sum(1 for r in results if not r["error"])
    failed = total_queries - successful
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    actual_escalations = sum(1 for r in results if r["escalated"])
    correct_escalations = sum(
        1 for r in results if r["should_escalate"] == r["escalated"]
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "git_branch": "main",
        "sprint": sprint,
        "total_queries": total_queries,
        "successful": successful,
        "failed": failed,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "min_latency_ms": round(min(latencies), 2) if latencies else 0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0,
        "p50_latency_ms": round(
            sorted(latencies)[len(latencies) // 2] if latencies else 0, 2
        ),
        "p95_latency_ms": round(
            sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 2
        ),
        "p99_latency_ms": round(
            sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0, 2
        ),
        "escalation_rate_percent": round((actual_escalations / total_queries * 100), 2),
        "escalation_accuracy_percent": round(
            (correct_escalations / total_queries * 100), 2
        ),
        "results": results,
    }


def generate_hallucination_results(sprint: str, base_rate: float = 0.25) -> dict:
    """Generate mock hallucination check results.

    Args:
        sprint: Sprint identifier.
        base_rate: Base hallucination rate (0-1).

    Returns:
        Dictionary with mock hallucination results.
    """
    random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))
    np.random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))

    total_queries = 50
    hallucination_count = int(total_queries * base_rate)
    hallucination_rate = round((hallucination_count / total_queries * 100), 2)

    suspicious_templates = [
        {
            "query_id": f"q{j + 1:03d}",
            "query": "Pregunta técnica simulada",
            "response": f"El panel tiene una eficiencia del {15 + j}% cuando debería ser menor...",
            "reason": "numerical hallucination detected",
            "suspicious_values": [f"{15 + j}%"],
            "num_sources": 0,
        }
        for j in range(min(hallucination_count, 5))
    ]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sprint": sprint,
        "total_queries": total_queries,
        "hallucination_count": hallucination_count,
        "hallucination_rate_percent": hallucination_rate,
        "average_num_sources": round(random.uniform(0.8, 1.5), 2),
        "suspicious_queries": suspicious_templates,
        "criteria": [
            "num_sources == 0",
            "numerical values in response not found in source_documents",
        ],
    }


def generate_human_eval_results(sprint: str, base_score: float = 3.0) -> dict:
    """Generate mock human evaluation results.

    Args:
        sprint: Sprint identifier.
        base_score: Base average score (1-5).

    Returns:
        Dictionary with mock human evaluation results.
    """
    random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))
    np.random.seed(int.from_bytes(sprint.encode(), "little") % (2**32))

    num_conversations = 20
    dimension_names = [
        "accuracy",
        "completeness",
        "escalation_appropriateness",
        "question_qualification",
        "tone_and_professionalism",
        "safety_and_compliance",
    ]

    weights = {
        "accuracy": 0.25,
        "completeness": 0.20,
        "escalation_appropriateness": 0.20,
        "question_qualification": 0.15,
        "tone_and_professionalism": 0.10,
        "safety_and_compliance": 0.10,
    }

    results = []
    dimension_totals = {d: 0.0 for d in dimension_names}
    escalation_correct = 0

    for i in range(num_conversations):
        scores = {}
        for dim in dimension_names:
            score = round(
                random.uniform(max(1, base_score - 1), min(5, base_score + 1)), 1
            )
            scores[dim] = score
            dimension_totals[dim] += score

        correct = random.random() < (0.75 + (5 - base_score) * 0.05)
        escalation_correct += 1 if correct else 0

        results.append(
            {
                "conversation_id": f"conv_{i + 1:03d}",
                "scores": scores,
                "escalation_given": "escalate_technical"
                if scores["escalation_appropriateness"] < 3
                else "no_escalate",
                "escalation_expected": "escalate_technical"
                if random.random() < 0.4
                else "no_escalate",
                "escalation_correct": correct,
                "comments": "",
            }
        )

    dim_averages = {
        d: round(dimension_totals[d] / num_conversations, 2) for d in dimension_names
    }
    weighted_total = sum(dim_averages[d] * weights[d] for d in dimension_names)

    return {
        "version": "1.0",
        "evaluation_date": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "sprint": sprint,
        "total_conversations": num_conversations,
        "results": results,
        "summary": {
            "dimension_averages": dim_averages,
            "weighted_total_score": round(weighted_total, 2),
            "passing": weighted_total >= 3.5,
            "escalation_accuracy_percent": round(
                (escalation_correct / num_conversations * 100), 1
            ),
            "escalation_accuracy_target": "≥ 90%",
        },
    }


def generate_quality_report_data(sprint: str) -> dict:
    """Generate complete mock quality report data for a sprint.

    Args:
        sprint: Sprint identifier.

    Returns:
        Dictionary with all evaluation metrics for the sprint.
    """
    is_baseline = "2" in sprint

    if is_baseline:
        base_latency = 3200.0
        base_hallucination_rate = 0.35
        base_score = 2.8
    else:
        base_latency = 1800.0
        base_hallucination_rate = 0.12
        base_score = 4.2

    return {
        "sprint": sprint,
        "is_baseline": is_baseline,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "harness": generate_harness_results(sprint, base_latency=base_latency),
        "hallucination": generate_hallucination_results(
            sprint, base_rate=base_hallucination_rate
        ),
        "human_eval": generate_human_eval_results(sprint, base_score=base_score),
    }


def list_mock_sprints() -> list[str]:
    """List available mock sprints from local files.

    Returns:
        List of sprint identifiers that have mock data files.
    """
    mock_dir = Path("evaluation/mock_data")
    if not mock_dir.exists():
        return []
    return sorted(
        [
            f.stem.replace("mock_quality_report_", "")
            for f in mock_dir.glob("mock_quality_report_*.json")
        ]
    )


def save_mock_data(
    output_dir: Path, sprints: list[str] | None = None
) -> dict[str, Path]:
    """Generate and save mock data for multiple sprints.

    Args:
        output_dir: Directory to save mock data files.
        sprints: List of sprint identifiers. Defaults to ["sprint_2", "sprint_5"].

    Returns:
        Dictionary mapping sprint names to output file paths.
    """
    if sprints is None:
        sprints = ["sprint_2", "sprint_5"]

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    for sprint in sprints:
        data = generate_quality_report_data(sprint)
        output_path = output_dir / f"mock_quality_report_{sprint}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        paths[sprint] = output_path
        print(f"Generated mock data for {sprint}: {output_path}")

    return paths


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate mock evaluation data for testing"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/mock_data"),
        help="Directory to save mock data files",
    )
    parser.add_argument(
        "--sprints",
        nargs="+",
        default=["sprint_2", "sprint_5"],
        help="Sprint identifiers to generate data for",
    )

    args = parser.parse_args()
    save_mock_data(args.output_dir, args.sprints)
