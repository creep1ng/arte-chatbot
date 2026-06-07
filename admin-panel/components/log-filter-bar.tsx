"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { LogFilterParams } from "@/lib/types";

type EscalatedOption = "" | "true" | "false";

interface LogFilterBarProps {
  filters: LogFilterParams;
  onApply: (filters: LogFilterParams) => void;
  onClear: () => void;
}

export function LogFilterBar({ filters, onApply, onClear }: LogFilterBarProps) {
  const [sessionId, setSessionId] = useState(filters.session_id ?? "");
  const [intentType, setIntentType] = useState(filters.intent_type ?? "");
  const [dateFrom, setDateFrom] = useState(filters.date_from ?? "");
  const [dateTo, setDateTo] = useState(filters.date_to ?? "");
  const [escalated, setEscalated] = useState<EscalatedOption>(
    filters.escalated === undefined ? "" : String(filters.escalated) as EscalatedOption,
  );

  useEffect(() => {
    setSessionId(filters.session_id ?? "");
    setIntentType(filters.intent_type ?? "");
    setDateFrom(filters.date_from ?? "");
    setDateTo(filters.date_to ?? "");
    setEscalated(
      filters.escalated === undefined ? "" : String(filters.escalated) as EscalatedOption,
    );
  }, [filters]);

  function handleApply() {
    onApply({
      session_id: sessionId.trim() || undefined,
      intent_type: intentType.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      escalated: escalated === "" ? undefined : escalated === "true",
      limit: filters.limit ?? 50,
      offset: 0,
    });
  }

  return (
    <section className="rounded-3xl border bg-card/90 p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
            Búsqueda operativa
          </p>
          <h2 className="font-display text-xl font-bold">Filtros de logs</h2>
        </div>
        <Button type="button" variant="secondary" onClick={onClear}>
          Limpiar filtros
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <label className="space-y-2 text-sm font-semibold">
          Session ID
          <Input
            aria-label="Filtrar por session id"
            value={sessionId}
            placeholder="wa-52d..."
            onChange={(event) => setSessionId(event.target.value)}
          />
        </label>

        <label className="space-y-2 text-sm font-semibold">
          Intención
          <Input
            aria-label="Filtrar por intención"
            list="log-intents"
            value={intentType}
            placeholder="cotizacion"
            onChange={(event) => setIntentType(event.target.value)}
          />
          <datalist id="log-intents">
            <option value="cotizacion" />
            <option value="soporte" />
            <option value="producto" />
            <option value="escalamiento" />
          </datalist>
        </label>

        <label className="space-y-2 text-sm font-semibold">
          Desde
          <Input
            aria-label="Filtrar fecha desde"
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </label>

        <label className="space-y-2 text-sm font-semibold">
          Hasta
          <Input
            aria-label="Filtrar fecha hasta"
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </label>

        <label className="space-y-2 text-sm font-semibold">
          Escalado
          <select
            aria-label="Filtrar por escalamiento"
            className="flex h-11 w-full rounded-md border border-input bg-card px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={escalated}
            onChange={(event) => setEscalated(event.target.value as EscalatedOption)}
          >
            <option value="">Todos</option>
            <option value="true">Solo escalados</option>
            <option value="false">Sin escalar</option>
          </select>
        </label>
      </div>

      <div className="mt-4 flex justify-end">
        <Button type="button" onClick={handleApply}>
          Aplicar filtros
        </Button>
      </div>
    </section>
  );
}
