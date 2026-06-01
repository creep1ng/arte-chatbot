"use client";

import { ChevronDown, ChevronRight, Download, Eye, File, Folder } from "lucide-react";
import { useState } from "react";

import type { S3TreeNode } from "@/lib/types";

interface S3TreeProps {
  nodes: S3TreeNode[];
  selectedKeys: string[];
  onSelectedKeysChange: (keys: string[]) => void;
  onViewFile?: (key: string) => void;
  onDownloadFile?: (key: string) => void;
}

interface S3TreeNodeRowProps extends S3TreeProps {
  node: S3TreeNode;
  depth: number;
}

function formatBytes(size?: number | null): string {
  if (size === undefined || size === null) {
    return "";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function toggleKey(keys: string[], key: string): string[] {
  return keys.includes(key) ? keys.filter((item) => item !== key) : [...keys, key];
}

function S3TreeNodeRow({
  node,
  depth,
  selectedKeys,
  onSelectedKeysChange,
  onViewFile,
  onDownloadFile,
}: S3TreeNodeRowProps) {
  const [isOpen, setIsOpen] = useState(depth === 0);
  const children = node.children ?? [];
  const isFolder = node.type === "folder";
  const isSelected = selectedKeys.includes(node.key);

  return (
    <li>
      <div
        className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 rounded-xl px-3 py-2 text-sm hover:bg-muted/60"
        style={{ paddingLeft: `${depth * 1.25 + 0.75}rem` }}
      >
        <div className="flex min-w-0 items-center gap-2">
          {isFolder ? (
            <button
              type="button"
              aria-label={isOpen ? `Contraer ${node.name}` : `Expandir ${node.name}`}
              className="rounded p-1 hover:bg-background"
              onClick={() => setIsOpen((value) => !value)}
            >
              {isOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          ) : (
            <input
              aria-label={`Seleccionar ${node.name}`}
              checked={isSelected}
              className="h-4 w-4 rounded border-input"
              type="checkbox"
              onChange={() => onSelectedKeysChange(toggleKey(selectedKeys, node.key))}
            />
          )}
          {isFolder ? (
            <Folder className="h-4 w-4 shrink-0 text-accent" />
          ) : (
            <File className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate font-medium">{node.name}</span>
        </div>
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatBytes(node.size)}
        </span>
        <span className="hidden text-xs text-muted-foreground md:inline">
          {formatDate(node.last_modified)}
        </span>
        {!isFolder && (onViewFile || onDownloadFile) ? (
          <div className="flex items-center gap-1">
            {onViewFile ? (
              <button
                type="button"
                aria-label={`Ver ${node.name}`}
                className="rounded-lg border px-2 py-1 text-xs font-semibold text-primary hover:bg-muted"
                onClick={() => onViewFile(node.key)}
              >
                <Eye className="h-3.5 w-3.5" />
                <span className="sr-only">Ver</span>
              </button>
            ) : null}
            {onDownloadFile ? (
              <button
                type="button"
                aria-label={`Descargar ${node.name}`}
                className="rounded-lg border px-2 py-1 text-xs font-semibold text-primary hover:bg-muted"
                onClick={() => onDownloadFile(node.key)}
              >
                <Download className="h-3.5 w-3.5" />
                <span className="sr-only">Descargar</span>
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      {isFolder && isOpen && children.length > 0 ? (
        <ul className="space-y-1">
          {children.map((child) => (
            <S3TreeNodeRow
              key={child.key}
              depth={depth + 1}
              node={child}
              selectedKeys={selectedKeys}
              onSelectedKeysChange={onSelectedKeysChange}
              onViewFile={onViewFile}
              onDownloadFile={onDownloadFile}
              nodes={children}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function S3Tree({
  nodes,
  selectedKeys,
  onSelectedKeysChange,
  onViewFile,
  onDownloadFile,
}: S3TreeProps) {
  if (nodes.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
        No hay objetos bajo este prefijo.
      </div>
    );
  }

  return (
    <ul className="space-y-1 rounded-2xl border bg-card p-3 shadow-sm">
      {nodes.map((node) => (
        <S3TreeNodeRow
          key={node.key}
          depth={0}
          node={node}
          nodes={nodes}
          selectedKeys={selectedKeys}
          onSelectedKeysChange={onSelectedKeysChange}
          onViewFile={onViewFile}
          onDownloadFile={onDownloadFile}
        />
      ))}
    </ul>
  );
}
