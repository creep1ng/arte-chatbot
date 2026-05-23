"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/data-table";
import { LogDetailDrawer } from "@/components/log-detail-drawer";
import { LogFilterBar } from "@/components/log-filter-bar";
import { Button } from "@/components/ui/button";
import { useLogDetail, useLogs } from "@/lib/api";
import type { ConversationLogSummary, LogFilterParams } from "@/lib/types";

function formatDate(value?: string | null): string {
  if (!value) {
    return "Sin fecha";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function LogsPage() {
  const [filters, setFilters] = useState<LogFilterParams>({
    limit: 50,
    offset: 0,
  });
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const logsQuery = useLogs(filters);
  const detailQuery = useLogDetail(selectedSessionId);

  const columns = useMemo<ColumnDef<ConversationLogSummary>[]>(
    () => [
      {
        accessorKey: "session_id",
        header: "Session ID",
        cell: ({ row }) => (
          <button
            type="button"
            className="font-mono text-sm font-bold text-primary underline-offset-4 hover:underline"
            onClick={() => setSelectedSessionId(row.original.session_id)}
          >
            {row.original.session_id}
          </button>
        ),
      },
      {
        accessorKey: "turn_count",
        header: "Turnos",
      },
      {
        accessorKey: "intent_types",
        header: "Intenciones",
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.intent_types.length ? (
              row.original.intent_types.map((intent) => (
                <span
                  key={intent}
                  className="rounded-full bg-secondary px-2 py-1 text-xs font-semibold text-secondary-foreground"
                >
                  {intent}
                </span>
              ))
            ) : (
              <span className="text-muted-foreground">Sin intención</span>
            )}
          </div>
        ),
      },
      {
        accessorKey: "escalated",
        header: "Escalado",
        cell: ({ row }) => (row.original.escalated ? "Sí" : "No"),
      },
      {
        accessorKey: "last_timestamp",
        header: "Última actividad",
        cell: ({ row }) => formatDate(row.original.last_timestamp),
      },
      {
        id: "actions",
        header: "Detalle",
        cell: ({ row }) => (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setSelectedSessionId(row.original.session_id)}
          >
            Ver transcript
          </Button>
        ),
      },
    ],
    [],
  );

  const logs = logsQuery.data?.items ?? [];
  const total = logsQuery.data?.total ?? 0;

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-3xl border bg-card shadow-sm">
        <div className="border-b bg-gradient-to-r from-primary/12 via-accent/10 to-transparent p-6">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
            Auditoría de conversaciones
          </p>
          <h1 className="mt-2 font-display text-3xl font-black">
            Logs de atención automatizada
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Filtra sesiones por intención, fecha, escalamiento o identificador para
            revisar decisiones del bot sin tocar la operación de chat.
          </p>
        </div>
      </section>

      <LogFilterBar
        filters={filters}
        onApply={setFilters}
        onClear={() => setFilters({ limit: 50, offset: 0 })}
      />

      {logsQuery.isLoading ? (
        <p className="rounded-2xl border bg-card p-5 text-sm text-muted-foreground">
          Cargando logs de conversación…
        </p>
      ) : logsQuery.error ? (
        <p className="rounded-2xl border border-destructive/30 bg-destructive/10 p-5 text-sm text-destructive">
          {logsQuery.error.message}
        </p>
      ) : (
        <section className="space-y-3">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>{total.toLocaleString("es-MX")} sesiones encontradas</span>
            <span>Mostrando {logs.length.toLocaleString("es-MX")}</span>
          </div>
          <DataTable
            columns={columns}
            data={logs}
            emptyMessage="No hay logs para los filtros aplicados."
          />
        </section>
      )}

      <LogDetailDrawer
        sessionId={selectedSessionId}
        isOpen={Boolean(selectedSessionId)}
        entries={detailQuery.data ?? []}
        isLoading={detailQuery.isLoading}
        error={detailQuery.error}
        onClose={() => setSelectedSessionId(null)}
      />
    </div>
  );
}
