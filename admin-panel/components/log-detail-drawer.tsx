"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ConversationLogEntry } from "@/lib/types";

interface LogDetailDrawerProps {
  sessionId: string | null;
  entries: ConversationLogEntry[];
  isOpen: boolean;
  isLoading?: boolean;
  error?: Error | null;
  onClose: () => void;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function LogDetailDrawer({
  sessionId,
  entries,
  isOpen,
  isLoading = false,
  error = null,
  onClose,
}: LogDetailDrawerProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 bg-foreground/20 backdrop-blur-sm">
      <aside className="ml-auto flex h-full w-full max-w-3xl flex-col border-l bg-background shadow-2xl">
        <header className="border-b bg-card px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
                Transcript cronológico
              </p>
              <h2 className="mt-1 font-display text-2xl font-black">
                {sessionId ?? "Sesión sin seleccionar"}
              </h2>
            </div>
            <Button type="button" variant="secondary" onClick={onClose}>
              <X className="h-4 w-4" />
              Cerrar
            </Button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <p className="rounded-2xl border bg-card p-5 text-sm text-muted-foreground">
              Cargando transcript…
            </p>
          ) : error ? (
            <p className="rounded-2xl border border-destructive/30 bg-destructive/10 p-5 text-sm text-destructive">
              {error.message}
            </p>
          ) : entries.length === 0 ? (
            <p className="rounded-2xl border bg-card p-5 text-sm text-muted-foreground">
              Esta sesión no tiene turnos registrados.
            </p>
          ) : (
            <ol className="space-y-5">
              {entries.map((entry) => (
                <li
                  key={`${entry.session_id}-${entry.turn_number}`}
                  className="rounded-3xl border bg-card p-5 shadow-sm"
                >
                  <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded-full bg-primary px-3 py-1 font-bold text-primary-foreground">
                      Turno {entry.turn_number}
                    </span>
                    <span>{formatTimestamp(entry.timestamp)}</span>
                    <span>Intent: {entry.intent_type || "sin clasificar"}</span>
                    <span
                      className={`rounded-full px-3 py-1 font-bold ${
                        entry.escalate
                          ? "bg-destructive/15 text-destructive"
                          : "bg-secondary text-secondary-foreground"
                      }`}
                    >
                      {entry.escalate ? "Escalado" : "Automático"}
                    </span>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="rounded-2xl bg-muted/60 p-4">
                      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                        Usuario
                      </p>
                      <p className="whitespace-pre-wrap text-sm leading-6">
                        {entry.user_message}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-accent/10 p-4">
                      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-accent">
                        Bot
                      </p>
                      <p className="whitespace-pre-wrap text-sm leading-6">
                        {entry.bot_response}
                      </p>
                    </div>
                  </div>

                  <dl className="mt-4 grid gap-3 text-xs text-muted-foreground sm:grid-cols-4">
                    <div>
                      <dt className="font-bold text-foreground">Tokens entrada</dt>
                      <dd>{entry.input_tokens.toLocaleString("es-MX")}</dd>
                    </div>
                    <div>
                      <dt className="font-bold text-foreground">Tokens salida</dt>
                      <dd>{entry.output_tokens.toLocaleString("es-MX")}</dd>
                    </div>
                    <div>
                      <dt className="font-bold text-foreground">Total</dt>
                      <dd>{entry.total_tokens.toLocaleString("es-MX")}</dd>
                    </div>
                    <div>
                      <dt className="font-bold text-foreground">Latencia</dt>
                      <dd>{Math.round(entry.response_time_ms)} ms</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  );
}
