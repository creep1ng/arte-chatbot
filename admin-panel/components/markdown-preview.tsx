"use client";

import { useMemo } from "react";

interface MarkdownPreviewProps {
  content: string;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderInline(value: string): string {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(content: string): string {
  const lines = content.split("\n");
  const html: string[] = [];
  let listOpen = false;

  for (const line of lines) {
    if (line.startsWith("- ")) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${renderInline(line.slice(2))}</li>`);
      continue;
    }

    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }

    if (line.startsWith("### ")) {
      html.push(`<h3>${renderInline(line.slice(4))}</h3>`);
    } else if (line.startsWith("## ")) {
      html.push(`<h2>${renderInline(line.slice(3))}</h2>`);
    } else if (line.startsWith("# ")) {
      html.push(`<h1>${renderInline(line.slice(2))}</h1>`);
    } else if (line.trim()) {
      html.push(`<p>${renderInline(line)}</p>`);
    }
  }

  if (listOpen) {
    html.push("</ul>");
  }

  return html.join("\n");
}

export function MarkdownPreview({ content }: MarkdownPreviewProps) {
  const html = useMemo(() => renderMarkdown(content), [content]);

  return (
    <article
      className="prose prose-sm max-w-none rounded-2xl border bg-card p-4 text-foreground shadow-sm [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_h1]:text-2xl [&_h1]:font-black [&_h2]:text-xl [&_h2]:font-bold [&_h3]:text-lg [&_h3]:font-bold [&_li]:ml-5 [&_li]:list-disc [&_p]:my-2"
      data-testid="markdown-preview"
      dangerouslySetInnerHTML={{ __html: html || "<p>Sin contenido.</p>" }}
    />
  );
}
