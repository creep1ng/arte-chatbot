"use client";

import { Upload } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePresignedUpload } from "@/lib/api";

interface UploadDialogProps {
  prefix: string;
}

export function UploadDialog({ prefix }: UploadDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [destination, setDestination] = useState(prefix);
  const uploadMutation = usePresignedUpload();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      toast.error("Selecciona un archivo antes de subir.");
      return;
    }

    const normalizedPrefix = destination.trim().replace(/^\/+/, "");
    const key = normalizedPrefix.endsWith(file.name)
      ? normalizedPrefix
      : `${normalizedPrefix.replace(/\/+$/, "")}/${file.name}`;

    try {
      const presigned = await uploadMutation.mutateAsync({
        key,
        content_type: file.type || "application/octet-stream",
      });
      const formData = new FormData();
      Object.entries(presigned.fields).forEach(([field, value]) => {
        formData.append(field, value);
      });
      formData.append("file", file);

      const response = await fetch(presigned.url, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(`S3 rechazó la subida (${response.status})`);
      }

      toast.success(`Archivo subido: ${presigned.key}`);
      setFile(null);
      setDestination(prefix);
      setIsOpen(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error inesperado";
      toast.error(message);
    }
  }

  if (!isOpen) {
    return (
      <Button type="button" onClick={() => setIsOpen(true)}>
        <Upload className="h-4 w-4" />
        Subir archivo
      </Button>
    );
  }

  return (
    <div className="rounded-2xl border bg-card p-5 shadow-xl">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div>
          <label className="text-sm font-semibold" htmlFor="upload-file">
            Archivo
          </label>
          <Input
            id="upload-file"
            type="file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </div>
        <div>
          <label className="text-sm font-semibold" htmlFor="upload-destination">
            Prefijo o key destino
          </label>
          <Input
            id="upload-destination"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            placeholder="raw/paneles/"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Si escribes solo un prefijo, se usará el nombre original del archivo.
          </p>
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? "Preparando…" : "Confirmar subida"}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setIsOpen(false)}>
            Cancelar
          </Button>
        </div>
      </form>
    </div>
  );
}
