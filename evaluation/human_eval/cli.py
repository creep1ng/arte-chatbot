#!/usr/bin/env python3
"""
Herramienta CLI para evaluación humana del chatbot Arte.
Permite a los evaluadores calificar las respuestas del chatbot usando el dataset y rúbrica definidos.
"""
import json
import sys
from pathlib import Path
from typing import Optional

import click


class HumanEvalCLI:
    """CLI para evaluación humana del chatbot."""

    def __init__(self, dataset_path: Path, rubric_path: Path):
        """Inicializar con rutas a dataset y rúbrica."""
        self.dataset_path = dataset_path
        self.rubric_path = rubric_path
        self.dataset = self._load_json(dataset_path)
        self.rubric = self._load_json(rubric_path)
        self.current_index = 0
        self.scores: list[dict] = []

    def _load_json(self, path: Path) -> dict:
        """Cargar archivo JSON."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_results(self, output_path: Path) -> None:
        """Guardar resultados de evaluación."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": "1.0",
                    "evaluation_date": self._get_timestamp(),
                    "total_conversations": len(self.scores),
                    "results": self.scores,
                    "summary": self._calculate_summary(),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    def _get_timestamp(self) -> str:
        """Obtener timestamp actual."""
        from datetime import datetime

        return datetime.now().isoformat()

    def _calculate_summary(self) -> dict:
        """Calcular resumen de puntuaciones."""
        if not self.scores:
            return {}

        dimensions = self.rubric["evaluation_dimensions"]
        weights = {d["name"]: d["weight"] for d in dimensions}

        # Calcular promedio por dimensión
        dim_averages = {}
        for dim in weights:
            scores = [s["scores"].get(dim, 0) for s in self.scores if dim in s["scores"]]
            if scores:
                dim_averages[dim] = sum(scores) / len(scores)

        # Calcular puntuación ponderada total
        weighted_total = sum(
            dim_averages.get(dim, 0) * weight for dim, weight in weights.items()
        )

        # Calcular precisión de escalamiento
        escalation_correct = sum(
            1 for s in self.scores if s.get("escalation_correct", False)
        )
        escalation_accuracy = (
            (escalation_correct / len(self.scores) * 100) if self.scores else 0
        )

        return {
            "dimension_averages": dim_averages,
            "weighted_total_score": round(weighted_total, 2),
            "passing": weighted_total >= self.rubric["scoring_guidelines"]["passing_threshold"],
            "escalation_accuracy_percent": round(escalation_accuracy, 1),
            "escalation_accuracy_target": self.rubric["scoring_guidelines"]["escalation_accuracy_target"],
        }

    def display_conversation(self, conv: dict) -> None:
        """Mostrar conversación actual."""
        click.echo("\n" + "=" * 60)
        click.echo(f"CONVERSACIÓN {self.current_index + 1}/{len(self.dataset['conversations'])}")
        click.echo(f"ID: {conv['id']}")
        click.echo("=" * 60)

        # Metadatos
        click.echo(f"\n📋 Dominio: {conv['domain']}")
        click.echo(f"⚡ Dificultad: {conv['difficulty']}")
        click.echo(f"🔄 Escalamiento esperado: {conv['escalation_classification']}")

        # Turns de la conversación
        for i, turn in enumerate(conv["turns"]):
            role = "👤 Usuario" if turn["role"] == "user" else "🤖 Asistente"
            click.echo(f"\n{role}:")
            click.echo(f"  {turn['content']}")

        # Respuesta esperada
        click.echo(f"\n📝 Respuesta esperada:")
        click.echo(f"  {conv['expected_response']}")

        if conv.get("notes"):
            click.echo(f"\n📌 Notas del evaluador:")
            click.echo(f"  {conv['notes']}")

    def evaluate_conversation(self) -> dict:
        """Evaluar una conversación."""
        conv = self.dataset["conversations"][self.current_index]

        scores = {}

        # Evaluar cada dimensión
        for dim in self.rubric["evaluation_dimensions"]:
            click.echo(f"\n--- {dim['display_name']} ---")
            click.echo(f"{dim['description']}")

            # Mostrar niveles
            for level in dim["levels"]:
                click.echo(f"  [{level['score']}] {level['label']}: {level['description']}")

            # Solicitar puntuación
            while True:
                try:
                    score = int(
                        click.prompt(
                            f"\nPuntuación (1-5)",
                            type=int,
                            default=3,
                        )
                    )
                    if 1 <= score <= 5:
                        scores[dim["name"]] = score
                        break
                    click.echo("⚠️  Por favor ingrese un valor entre 1 y 5")
                except ValueError:
                    click.echo("⚠️  Por favor ingrese un valor numérico válido")

        # Evaluar escalamiento
        click.echo(f"\n--- Escalamiento ---")
        click.echo(f"Clasificación esperada: {conv['escalation_classification']}")

        user_escalation = click.prompt(
            "Clasificación dada por el chatbot (no_escalate/escalate_sales/escalate_technical)",
            type=str,
            default=conv["escalation_classification"],
        )

        escalation_correct = user_escalation == conv["escalation_classification"]

        if escalation_correct:
            click.echo("✅ ¡Correcto!")
        else:
            click.echo(f"❌ Incorrecto. Esperado: {conv['escalation_classification']}")

        # Comentarios adicionales
        comments = click.prompt(
            "Comentarios adicionales (opcional)",
            type=str,
            default="",
        )

        return {
            "conversation_id": conv["id"],
            "scores": scores,
            "escalation_given": user_escalation,
            "escalation_expected": conv["escalation_classification"],
            "escalation_correct": escalation_correct,
            "comments": comments,
        }

    def run(self) -> None:
        """Ejecutar evaluación."""
        click.echo("🔍 Evaluación Humana del Chatbot Arte")
        click.echo("=" * 40)

        total = len(self.dataset["conversations"])

        for i, conv in enumerate(self.dataset["conversations"]):
            self.current_index = i
            self.display_conversation(conv)

            if click.confirm("\n¿Evaluar esta conversación?"):
                result = self.evaluate_conversation()
                self.scores.append(result)
                click.echo("\n✅ Conversación evaluada")

            if i < total - 1:
                if not click.confirm("\n¿Continuar con la siguiente conversación?"):
                    break

        # Mostrar resumen
        click.echo("\n" + "=" * 60)
        click.echo("📊 RESUMEN DE EVALUACIÓN")
        click.echo("=" * 60)

        summary = self._calculate_summary()

        if summary:
            click.echo(f"\nPuntuación total ponderada: {summary['weighted_total_score']}/5")
            click.echo(f"¿Aprobado?: {'✅ Sí' if summary['passing'] else '❌ No'}")
            click.echo(f"\nPrecisión de escalamiento: {summary['escalation_accuracy_percent']}%")
            click.echo(f"Objetivo: {summary['escalation_accuracy_target']}")

            click.echo("\n📈 Puntuaciones por dimensión:")
            for dim, avg in summary["dimension_averages"].items():
                click.echo(f"  - {dim}: {avg:.2f}/5")

        # Guardar resultados
        if self.scores:
            output_path = self.dataset_path.parent / "evaluation_results.json"
            self._save_results(output_path)
            click.echo(f"\n💾 Resultados guardados en: {output_path}")


@click.command()
@click.option(
    "--dataset",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    default="evaluation/human_eval/dataset.json",
    help="Ruta al archivo de dataset",
)
@click.option(
    "--rubric",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    default="evaluation/human_eval/rubric.json",
    help="Ruta al archivo de rúbrica",
)
def main(dataset: Path, rubric: Path) -> None:
    """Herramienta de evaluación humana para el chatbot Arte."""
    cli = HumanEvalCLI(dataset, rubric)
    cli.run()


if __name__ == "__main__":
    main()
