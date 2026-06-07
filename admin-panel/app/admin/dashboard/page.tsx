"use client";

import { EscalationRateCard, IntentPieChart, StatsCards } from "@/components/dashboard-stats";
import { useDashboardMetrics } from "@/lib/api";

export default function DashboardPage() {
  const { data: metrics, isError, isLoading, error } = useDashboardMetrics();

  if (isLoading) {
    return (
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-sm text-muted-foreground">Cargando métricas…</p>
      </section>
    );
  }

  if (isError || !metrics) {
    const message = error instanceof Error ? error.message : "Error inesperado";
    return (
      <section className="rounded-[2rem] border border-destructive/30 bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-destructive">
          Error
        </p>
        <h1 className="mt-3 font-display text-3xl font-black text-primary">
          No se pudo cargar el dashboard
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">{message}</p>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          Métricas operativas
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          Dashboard administrativo
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Visión rápida de sesiones, consumo de tokens, intenciones detectadas y
          escalamiento humano del chatbot.
        </p>
      </section>

      <StatsCards metrics={metrics} />

      <div className="grid gap-6 xl:grid-cols-2">
        <IntentPieChart metrics={metrics} />
        <EscalationRateCard metrics={metrics} />
      </div>
    </div>
  );
}
