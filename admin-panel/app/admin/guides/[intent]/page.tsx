"use client";

import { Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MarkdownEditor } from "@/components/markdown-editor";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Button } from "@/components/ui/button";
import { useDeleteGuide, useGuide, useUpdateGuide } from "@/lib/api";

export default function GuideEditorPage() {
  const params = useParams<{ intent: string }>();
  const router = useRouter();
  const intent = decodeURIComponent(params.intent);
  const { data: guide, isLoading, isError, error } = useGuide(intent);
  const updateGuide = useUpdateGuide();
  const deleteGuide = useDeleteGuide();
  const [content, setContent] = useState("");

  useEffect(() => {
    if (guide) {
      setContent(guide.content);
    } else if (isError) {
      setContent(`# ${intent}\n\n`);
    }
  }, [guide, intent, isError]);

  async function handleSave() {
    await updateGuide.mutateAsync({ intent, content });
  }

  async function handleDelete() {
    const confirmed = window.confirm(`Eliminar la guía ${intent}?`);
    if (!confirmed) {
      return;
    }
    await deleteGuide.mutateAsync(intent);
    router.push("/admin/guides");
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
          Editor de guía
        </p>
        <h1 className="mt-3 font-display text-4xl font-black text-primary">
          {intent}
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Escribe markdown a la izquierda y valida el preview seguro a la derecha.
        </p>
      </section>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando guía…</p>
      ) : null}

      {isError ? (
        <div className="rounded-2xl border border-accent/30 bg-accent/10 p-4 text-sm text-muted-foreground">
          {error instanceof Error ? error.message : "Guía no encontrada"}. Puedes
          crearla guardando contenido nuevo para este intent.
        </div>
      ) : null}

      <section className="space-y-4 rounded-[2rem] border bg-card/95 p-6 shadow-xl">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            disabled={updateGuide.isPending || !content.trim()}
            onClick={handleSave}
          >
            {updateGuide.isPending ? "Guardando…" : "Guardar guía"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={deleteGuide.isPending}
            onClick={handleDelete}
          >
            <Trash2 className="h-4 w-4" />
            Eliminar guía
          </Button>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <MarkdownEditor value={content} onChange={setContent} />
          <div className="space-y-2">
            <p className="text-sm font-semibold">Preview</p>
            <MarkdownPreview content={content} />
          </div>
        </div>
      </section>
    </div>
  );
}
