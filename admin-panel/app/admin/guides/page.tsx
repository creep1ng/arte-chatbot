"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useGuides } from "@/lib/api";
import type { GuideMeta } from "@/lib/types";

function normalizeIntent(value: string): string {
  return value.trim().replace(/\s+/g, "-").replace(/[^a-zA-Z0-9_-]/g, "");
}

export default function GuidesPage() {
  const router = useRouter();
  const [intent, setIntent] = useState("");
  const { data: guides = [], isLoading, isError, error } = useGuides();

  const columns = useMemo<ColumnDef<GuideMeta>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Guía",
        cell: ({ row }) => (
          <Link
            className="font-semibold text-primary underline-offset-4 hover:underline"
            href={`/admin/guides/${row.original.intent}`}
          >
            {row.original.title}
          </Link>
        ),
      },
      {
        accessorKey: "intent",
        header: "Intent",
      },
      {
        accessorKey: "updated_at",
        header: "Actualizada",
        cell: ({ row }) => row.original.updated_at ?? "—",
      },
    ],
    [],
  );

  function handleOpenIntent() {
    const normalized = normalizeIntent(intent);
    if (!normalized) {
      return;
    }
    router.push(`/admin/guides/${normalized}`);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          Guías
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          Guías markdown por intención
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Cada guía vive en S3 como <code>guides/&lt;intent&gt;.md</code>.
        </p>
      </section>

      <section className="space-y-4 rounded-[2rem] border bg-card/95 p-6 shadow-xl">
        <div className="flex flex-col gap-2 md:flex-row md:items-end">
          <div className="flex-1">
            <label className="text-sm font-semibold" htmlFor="new-guide-intent">
              Crear o abrir intent
            </label>
            <Input
              id="new-guide-intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder="cotizacion-paneles"
            />
          </div>
          <Button type="button" onClick={handleOpenIntent}>
            Abrir editor
          </Button>
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Cargando guías…</p>
        ) : isError ? (
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : "No se pudieron cargar las guías"}
          </p>
        ) : (
          <DataTable<GuideMeta>
            columns={columns}
            data={guides}
            emptyMessage="No hay guías markdown todavía."
          />
        )}
      </section>
    </div>
  );
}
