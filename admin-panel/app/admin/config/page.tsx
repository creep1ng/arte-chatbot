"use client";

import { ConfigForm } from "@/components/config-form";
import { useConfig } from "@/lib/api";

export default function ConfigPage() {
  const { data: config, isError, isLoading, error } = useConfig();

  if (isLoading) {
    return (
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-sm text-muted-foreground">Cargando configuración…</p>
      </section>
    );
  }

  if (isError || !config) {
    const message = error instanceof Error ? error.message : "Error inesperado";
    return (
      <section className="rounded-[2rem] border border-destructive/30 bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-destructive">
          Error
        </p>
        <h1 className="mt-3 font-display text-3xl font-black text-primary">
          No se pudo cargar la configuración
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">{message}</p>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          Hot reload
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          Configuración
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Edita parámetros operativos del chatbot sin tocar secretos ni valores
          que requieren reinicio del contenedor.
        </p>
      </section>

      <ConfigForm config={config} />
    </div>
  );
}
