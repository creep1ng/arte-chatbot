"use client";

import { useEffect, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { useCatalog, useUpdateCatalog } from "@/lib/api";
import { CatalogIndexSchema } from "@/lib/schemas";
import type { CatalogProduct } from "@/lib/types";

const EMPTY_PRODUCT: CatalogProduct = {
  nombre_comercial: "Nuevo producto",
  fabricante: "",
  categoria: "paneles",
  subcategoria: "",
  descripcion: "",
  ruta_s3: "raw/paneles/nuevo-producto.pdf",
  variantes: [],
  parametros_comunes: {},
};

function productToJson(product: CatalogProduct): string {
  return JSON.stringify(product, null, 2);
}

export default function CatalogPage() {
  const { data: catalog, isLoading, isError, error } = useCatalog();
  const updateCatalog = useUpdateCatalog();
  const [rows, setRows] = useState<CatalogProduct[]>([]);
  const [selectedRows, setSelectedRows] = useState<Record<number, boolean>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  useEffect(() => {
    if (catalog) {
      setRows(catalog.products);
      setDrafts(
        Object.fromEntries(catalog.products.map((product, index) => [index, productToJson(product)])),
      );
      setSelectedRows({});
    }
  }, [catalog]);

  const columns = useMemo<ColumnDef<CatalogProduct>[]>(
    () => [
      {
        id: "select",
        header: "",
        cell: ({ row }) => (
          <input
            aria-label={`Seleccionar ${row.original.nombre_comercial}`}
            checked={Boolean(selectedRows[row.index])}
            type="checkbox"
            onChange={() =>
              setSelectedRows((current) => ({
                ...current,
                [row.index]: !current[row.index],
              }))
            }
          />
        ),
      },
      {
        accessorKey: "nombre_comercial",
        header: "Producto",
      },
      {
        accessorKey: "fabricante",
        header: "Fabricante",
      },
      {
        accessorKey: "categoria",
        header: "Categoría",
      },
      {
        accessorKey: "ruta_s3",
        header: "Ruta S3",
      },
      {
        id: "json",
        header: "Edición JSON",
        cell: ({ row }) => (
          <textarea
            aria-label={`Editar ${row.original.nombre_comercial}`}
            className="min-h-40 w-full min-w-[340px] rounded-xl border bg-background p-3 font-mono text-xs"
            value={drafts[row.index] ?? productToJson(row.original)}
            onChange={(event) => {
              const value = event.target.value;
              setDrafts((current) => ({ ...current, [row.index]: value }));
              try {
                const parsed = JSON.parse(value) as CatalogProduct;
                setRows((current) =>
                  current.map((item, index) => (index === row.index ? parsed : item)),
                );
              } catch {
                // Keep the invalid draft visible; validation happens on save.
              }
            }}
          />
        ),
      },
    ],
    [drafts, selectedRows],
  );

  async function handleSave() {
    try {
      const parsedProducts = rows.map((row, index) => {
        const draft = drafts[index] ?? productToJson(row);
        return JSON.parse(draft) as CatalogProduct;
      });
      const parsed = CatalogIndexSchema.parse({ products: parsedProducts });
      await updateCatalog.mutateAsync(parsed);
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "JSON inválido";
      toast.error(message);
    }
  }

  function handleAddProduct() {
    setRows((current) => [...current, EMPTY_PRODUCT]);
    setDrafts((current) => ({
      ...current,
      [rows.length]: productToJson(EMPTY_PRODUCT),
    }));
  }

  function handleRemoveSelected() {
    const selectedIndexes = new Set(
      Object.entries(selectedRows)
        .filter(([, selected]) => selected)
        .map(([index]) => Number(index)),
    );
    const nextRows = rows.filter((_row, index) => !selectedIndexes.has(index));
    setRows(nextRows);
    setDrafts(Object.fromEntries(nextRows.map((product, index) => [index, productToJson(product)])));
    setSelectedRows({});
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Cargando catálogo…</p>;
  }

  if (isError || !catalog) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : "No se pudo cargar el catálogo"}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          Catálogo
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          Índice de productos
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Edita productos como JSON validado contra el schema frontend. Es menos
          vistoso que una grilla inline pura, pero más seguro para este MVP.
        </p>
      </section>

      <section className="space-y-4 rounded-[2rem] border bg-card/95 p-6 shadow-xl">
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={handleAddProduct}>
            Añadir producto
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={!Object.values(selectedRows).some(Boolean)}
            onClick={handleRemoveSelected}
          >
            Quitar seleccionados
          </Button>
          <Button
            type="button"
            disabled={updateCatalog.isPending}
            onClick={handleSave}
          >
            {updateCatalog.isPending ? "Guardando…" : "Guardar catálogo"}
          </Button>
        </div>

        <DataTable<CatalogProduct>
          columns={columns}
          data={rows}
          emptyMessage="El catálogo no contiene productos."
        />
      </section>
    </div>
  );
}
