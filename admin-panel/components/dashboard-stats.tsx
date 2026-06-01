"use client";

import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  Bar,
  BarChart,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowUpRight, Gauge, MessageCircle, Zap } from "lucide-react";

import type { DashboardMetrics } from "@/lib/types";

const CHART_COLORS = ["#105349", "#f17923", "#d5aa35", "#3d7c71", "#8c4a1b"];

interface StatsCardsProps {
  metrics: DashboardMetrics;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("es-MX").format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

export function StatsCards({ metrics }: StatsCardsProps) {
  const cards = [
    {
      label: "Sesiones activas",
      value: formatNumber(metrics.active_sessions),
      icon: Activity,
    },
    {
      label: "Total tokens",
      value: formatNumber(metrics.total_tokens),
      icon: Zap,
    },
    {
      label: "Input tokens",
      value: formatNumber(metrics.total_input_tokens),
      icon: MessageCircle,
    },
    {
      label: "Output tokens",
      value: formatNumber(metrics.total_output_tokens),
      icon: ArrowUpRight,
    },
    {
      label: "Escalation rate",
      value: formatPercent(metrics.escalation_rate),
      icon: Gauge,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <article
            className="rounded-2xl border bg-card/95 p-5 shadow-sm"
            key={card.label}
          >
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-semibold text-muted-foreground">
                {card.label}
              </p>
              <span className="rounded-xl bg-secondary p-2 text-primary">
                <Icon className="h-4 w-4" />
              </span>
            </div>
            <p className="mt-4 font-display text-3xl font-black text-primary">
              {card.value}
            </p>
          </article>
        );
      })}
    </div>
  );
}

export function IntentPieChart({ metrics }: StatsCardsProps) {
  const data = Object.entries(metrics.intent_distribution).map(
    ([name, value]) => ({ name, value }),
  );

  return (
    <section className="rounded-[1.5rem] border bg-card/95 p-6 shadow-sm">
      <div className="mb-6">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
          Intenciones
        </p>
        <h2 className="mt-2 font-display text-2xl font-black text-primary">
          Distribución por intención
        </h2>
      </div>
      {data.length === 0 ? (
        <p className="rounded-xl bg-muted p-6 text-center text-sm text-muted-foreground">
          Aún no hay intenciones registradas para graficar.
        </p>
      ) : (
        <div className="h-80" data-testid="intent-pie-chart">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                innerRadius={64}
                outerRadius={112}
                paddingAngle={3}
              >
                {data.map((entry, index) => (
                  <Cell
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                    key={entry.name}
                  />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

export function EscalationRateCard({ metrics }: StatsCardsProps) {
  const percentage = Math.round(metrics.escalation_rate * 100);
  const data = [
    { name: "Escaladas", value: percentage },
    { name: "Automatizadas", value: Math.max(0, 100 - percentage) },
  ];

  return (
    <section className="rounded-[1.5rem] border bg-card/95 p-6 shadow-sm">
      <div className="mb-6">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
          Escalamiento
        </p>
        <h2 className="mt-2 font-display text-2xl font-black text-primary">
          Tasa agregada
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          El backend de Slice 3 expone una tasa agregada, no una serie temporal;
          por eso este panel usa una barra comparativa en vez de una línea.
        </p>
      </div>
      <div className="mb-6">
        <p className="font-display text-5xl font-black text-primary">
          {formatPercent(metrics.escalation_rate)}
        </p>
        <p className="text-sm text-muted-foreground">
          Conversaciones que requieren agente humano
        </p>
      </div>
      <div className="h-56" data-testid="escalation-rate-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis type="category" dataKey="name" width={110} />
            <Tooltip formatter={(value) => `${value}%`} />
            <Bar dataKey="value" radius={[0, 12, 12, 0]} fill="#105349" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
