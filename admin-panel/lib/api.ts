import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { STORAGE_KEY } from "@/providers/admin-auth-provider";
import type {
  CurrentSettingsSnapshot,
  DashboardMetrics,
  MutableSettings,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface FastApiValidationError {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

export class AdminApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.details = details;
  }
}

function getAdminKey(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(STORAGE_KEY) ?? "";
}

function handleAuthFailure(status: number) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(STORAGE_KEY);

  if (status === 401) {
    window.location.assign("/admin/login");
    return;
  }

  toast.error("Acceso denegado. Verifica tu API key.");
  window.setTimeout(() => window.location.assign("/admin/login"), 3000);
}

async function parseErrorResponse(response: Response): Promise<AdminApiError> {
  const text = await response.text();
  let details: unknown = text;
  let message = text || `HTTP ${response.status}`;

  try {
    details = JSON.parse(text);
    if (
      details &&
      typeof details === "object" &&
      "detail" in details &&
      typeof details.detail === "string"
    ) {
      message = details.detail;
    }
  } catch {
    // Keep raw text when the backend returns plain text.
  }

  if (response.status === 401) {
    message = "Sesión administrativa expirada. Vuelve a iniciar sesión.";
  }

  if (response.status === 403) {
    message = "Acceso denegado. Verifica tu API key.";
  }

  return new AdminApiError(response.status, message, details);
}

async function adminFetch<TResponse>(
  path: string,
  init: RequestInit = {},
): Promise<TResponse> {
  const headers = new Headers(init.headers);
  headers.set("X-Admin-API-Key", getAdminKey());

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const error = await parseErrorResponse(response);
    if (response.status === 401 || response.status === 403) {
      handleAuthFailure(response.status);
    }
    throw error;
  }

  return response.json() as Promise<TResponse>;
}

export function extractFastApiFieldErrors(
  error: unknown,
): FastApiValidationError[] {
  if (!(error instanceof AdminApiError) || error.status !== 422) {
    return [];
  }

  if (
    error.details &&
    typeof error.details === "object" &&
    "detail" in error.details &&
    Array.isArray(error.details.detail)
  ) {
    return error.details.detail.filter(
      (entry): entry is FastApiValidationError =>
        entry &&
        typeof entry === "object" &&
        Array.isArray(entry.loc) &&
        typeof entry.msg === "string",
    );
  }

  return [];
}

export function useDashboardMetrics() {
  return useQuery({
    queryKey: ["admin", "dashboard", "metrics"],
    queryFn: () => adminFetch<DashboardMetrics>("/admin/dashboard/metrics"),
    staleTime: 30_000,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["admin", "config"],
    queryFn: () => adminFetch<CurrentSettingsSnapshot>("/admin/config"),
    staleTime: 60_000,
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: MutableSettings) =>
      adminFetch<CurrentSettingsSnapshot>("/admin/config", {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "config"] });
      toast.success("Configuración guardada");
    },
    onError: (error) => {
      if (error instanceof AdminApiError && error.status === 422) {
        toast.error("Revisa los campos marcados antes de guardar.");
        return;
      }

      const message = error instanceof Error ? error.message : "Error inesperado";
      toast.error(message);
    },
  });
}
