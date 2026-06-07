"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { S3Tree } from "@/components/s3-tree";
import { UploadDialog } from "@/components/upload-dialog";
import { Button } from "@/components/ui/button";
import { useDeleteS3Objects, usePresignedDownload, useS3Tree } from "@/lib/api";

const PREFIXES = ["raw/", "guides/", "index/"];

export default function S3ExplorerPage() {
  const [prefix, setPrefix] = useState(PREFIXES[0]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const { data: nodes = [], isLoading, isError, error } = useS3Tree(prefix);
  const deleteMutation = useDeleteS3Objects();
  const presignedDownload = usePresignedDownload();

  async function openFile(key: string) {
    const response = await presignedDownload.mutateAsync({
      key,
      disposition: "inline",
    });
    window.open(response.url, "_blank", "noopener,noreferrer");
  }

  async function downloadFile(key: string) {
    const response = await presignedDownload.mutateAsync({
      key,
      disposition: "attachment",
    });
    const anchor = document.createElement("a");
    anchor.href = response.url;
    anchor.download = key.split("/").pop() ?? "ficha-tecnica.pdf";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  async function handleDelete() {
    if (selectedKeys.length === 0) {
      return;
    }
    const confirmed = window.confirm(
      `Eliminar ${selectedKeys.length} objeto(s) de S3? Esta acción no se puede deshacer.`,
    );
    if (!confirmed) {
      return;
    }
    await deleteMutation.mutateAsync({ keys: selectedKeys });
    setSelectedKeys([]);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          S3 Explorer
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          Archivos técnicos y guías
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Navega los prefijos operativos del bucket. Las subidas usan presigned
          POST para que el frontend no maneje credenciales AWS.
        </p>
      </section>

      <section className="space-y-4 rounded-[2rem] border bg-card/95 p-6 shadow-xl">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex gap-2">
            {PREFIXES.map((item) => (
              <Button
                key={item}
                type="button"
                variant={prefix === item ? "default" : "secondary"}
                onClick={() => {
                  setPrefix(item);
                  setSelectedKeys([]);
                }}
              >
                {item}
              </Button>
            ))}
          </div>
          <div className="flex flex-col gap-2 md:flex-row">
            <UploadDialog prefix={prefix} />
            <Button
              type="button"
              variant="secondary"
              disabled={selectedKeys.length === 0 || deleteMutation.isPending}
              onClick={handleDelete}
            >
              <Trash2 className="h-4 w-4" />
              Eliminar seleccionados ({selectedKeys.length})
            </Button>
          </div>
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Cargando árbol S3…</p>
        ) : isError ? (
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : "No se pudo cargar S3"}
          </p>
        ) : (
          <S3Tree
            nodes={nodes}
            selectedKeys={selectedKeys}
            onSelectedKeysChange={setSelectedKeys}
            onViewFile={prefix === "raw/" ? openFile : undefined}
            onDownloadFile={prefix === "raw/" ? downloadFile : undefined}
          />
        )}
      </section>
    </div>
  );
}
