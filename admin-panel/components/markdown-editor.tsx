"use client";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
}

export function MarkdownEditor({ value, onChange }: MarkdownEditorProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-semibold" htmlFor="guide-content">
        Editor markdown
      </label>
      <textarea
        id="guide-content"
        aria-label="Editor markdown"
        className="min-h-[420px] w-full rounded-2xl border bg-card p-4 font-mono text-sm shadow-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="# Título de la guía\n\nDescribe aquí el flujo operativo..."
      />
    </div>
  );
}
