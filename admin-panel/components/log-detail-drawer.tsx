"use client";

import {
  Bot,
  Clock3,
  FileText,
  Gauge,
  Hash,
  MessageSquare,
  User,
  X,
  type LucideIcon,
} from "lucide-react";

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

interface MetricCardProps {
  label: string;
  value: string;
  icon: LucideIcon;
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

function formatSessionId(sessionId: string | null): string {
  if (!sessionId) {
    return "Sesión sin seleccionar";
  }

  if (sessionId.length <= 22) {
    return sessionId;
  }

  return `${sessionId.slice(0, 12)}…${sessionId.slice(-8)}`;
}

function MetricCard({ label, value, icon: Icon }: MetricCardProps) {
  return (
    <div className="group rounded-2xl border border-foreground/10 bg-background/70 p-3 shadow-[0_10px_30px_rgba(22,45,39,0.06)] transition duration-200 hover:-translate-y-0.5 hover:border-accent/40">
      <dt className="flex items-center gap-2 text-[0.65rem] font-black uppercase tracking-[0.18em] text-muted-foreground">
        <Icon className="h-3.5 w-3.5 text-accent transition group-hover:rotate-6" />
        {label}
      </dt>
      <dd className="mt-1 font-display text-lg font-black tabular-nums text-foreground">
        {value}
      </dd>
    </div>
  );
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
    <div className="fixed inset-0 z-40 bg-foreground/30 backdrop-blur-md">
      <aside className="ml-auto flex h-full w-full max-w-5xl flex-col overflow-hidden border-l border-primary/20 bg-background shadow-[0_0_80px_rgba(8,48,42,0.32)]">
        <header className="relative overflow-hidden border-b border-primary/20 bg-card px-6 py-5">
          <div className="pointer-events-none absolute inset-0 opacity-80 [background-image:radial-gradient(circle_at_12%_20%,rgba(241,121,35,0.18),transparent_22rem),linear-gradient(120deg,rgba(16,83,73,0.08)_0,transparent_38%)]" />
          <div className="flex items-start justify-between gap-4">
            <div className="relative">
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-accent">
                Transcript cronológico
              </p>
              <h2 className="mt-1 font-display text-3xl font-black leading-tight md:text-4xl">
                {formatSessionId(sessionId)}
              </h2>
              {sessionId ? (
                <p className="mt-2 max-w-2xl break-all rounded-full border border-primary/10 bg-background/55 px-3 py-1 font-mono text-xs text-muted-foreground">
                  {sessionId}
                </p>
              ) : null}
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              className="relative"
            >
              <X className="h-4 w-4" />
              Cerrar
            </Button>
          </div>
        </header>

        <div className="solar-grid flex-1 overflow-y-auto p-4 md:p-6">
          {isLoading ? (
            <p className="rounded-3xl border bg-card p-6 text-sm text-muted-foreground shadow-sm">
              Cargando transcript…
            </p>
          ) : error ? (
            <p className="rounded-3xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive shadow-sm">
              {error.message}
            </p>
          ) : entries.length === 0 ? (
            <p className="rounded-3xl border bg-card p-6 text-sm text-muted-foreground shadow-sm">
              Esta sesión no tiene turnos registrados.
            </p>
          ) : (
            <ol className="relative space-y-7 before:absolute before:bottom-10 before:left-6 before:top-10 before:w-px before:bg-gradient-to-b before:from-accent before:via-primary/30 before:to-transparent md:before:left-8">
              {entries.map((entry) => (
                <li
                  key={`${entry.session_id}-${entry.turn_number}`}
                  className="relative grid gap-4 pl-14 md:grid-cols-[9rem_minmax(0,1fr)] md:gap-6 md:pl-0"
                >
                  <div className="absolute left-0 top-1 z-10 flex h-12 w-12 items-center justify-center rounded-2xl border border-primary/15 bg-primary font-display text-xl font-black text-primary-foreground shadow-[0_14px_32px_rgba(16,83,73,0.28)] md:static md:h-16 md:w-16 md:justify-self-center md:text-2xl">
                    {entry.turn_number}
                  </div>

                  <article className="overflow-hidden rounded-[2rem] border border-primary/15 bg-card/95 shadow-[0_22px_60px_rgba(22,45,39,0.10)] backdrop-blur">
                    <div className="flex flex-wrap items-center gap-2 border-b border-primary/10 bg-background/60 px-5 py-3 text-xs text-muted-foreground">
                      <span className="rounded-full bg-primary px-3 py-1 font-black uppercase tracking-[0.14em] text-primary-foreground">
                        Turno {entry.turn_number}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Clock3 className="h-3.5 w-3.5 text-accent" />
                        {formatTimestamp(entry.timestamp)}
                      </span>
                      <span className="rounded-full border border-primary/10 bg-background px-3 py-1 font-medium">
                        Intent: {entry.intent_type || "sin clasificar"}
                      </span>
                      <span
                        className={`rounded-full px-3 py-1 font-black ${
                          entry.escalate
                            ? "bg-destructive/15 text-destructive"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        {entry.escalate ? "Escalado" : "Automático"}
                      </span>
                    </div>

                    <div className="space-y-4 p-5">
                      <section className="flex gap-3 md:max-w-[76%]">
                        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                          <User className="h-4 w-4" />
                        </div>
                        <div className="rounded-[1.4rem] rounded-tl-sm bg-muted/70 px-5 py-4 shadow-inner">
                          <p className="mb-2 text-[0.68rem] font-black uppercase tracking-[0.2em] text-muted-foreground">
                            Usuario
                          </p>
                          <p className="whitespace-pre-wrap text-sm leading-7">
                            {entry.user_message}
                          </p>
                        </div>
                      </section>

                      <section className="ml-auto flex gap-3 md:max-w-[82%]">
                        <div className="order-2 mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground shadow-[0_10px_26px_rgba(241,121,35,0.25)]">
                          <Bot className="h-4 w-4" />
                        </div>
                        <div className="rounded-[1.4rem] rounded-tr-sm border border-accent/15 bg-gradient-to-br from-accent/14 to-secondary/55 px-5 py-4">
                          <p className="mb-2 text-[0.68rem] font-black uppercase tracking-[0.2em] text-accent">
                            Bot
                          </p>
                          <p className="whitespace-pre-wrap text-sm leading-7">
                            {entry.bot_response}
                          </p>
                        </div>
                      </section>
                    </div>

                    <dl className="grid gap-3 border-t border-primary/10 bg-background/45 p-5 sm:grid-cols-2 lg:grid-cols-4">
                      <MetricCard
                        label="Entrada"
                        value={entry.input_tokens.toLocaleString("es-MX")}
                        icon={MessageSquare}
                      />
                      <MetricCard
                        label="Salida"
                        value={entry.output_tokens.toLocaleString("es-MX")}
                        icon={Bot}
                      />
                      <MetricCard
                        label="Total"
                        value={entry.total_tokens.toLocaleString("es-MX")}
                        icon={Hash}
                      />
                      <MetricCard
                        label="Latencia"
                        value={`${Math.round(entry.response_time_ms)} ms`}
                        icon={Gauge}
                      />
                    </dl>

                    {entry.source_documents.length > 0 ? (
                      <div className="border-t border-primary/10 px-5 py-4">
                        <p className="mb-2 flex items-center gap-2 text-[0.68rem] font-black uppercase tracking-[0.18em] text-muted-foreground">
                          <FileText className="h-3.5 w-3.5 text-accent" />
                          Documentos fuente
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {entry.source_documents.map((document) => (
                            <span
                              key={document}
                              className="rounded-full border border-primary/10 bg-background px-3 py-1 font-mono text-xs text-muted-foreground"
                            >
                              {document}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </article>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  );
}
