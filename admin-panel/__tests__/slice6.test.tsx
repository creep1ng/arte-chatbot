import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LogsPage from "@/app/admin/logs/page";
import { LogDetailDrawer } from "@/components/log-detail-drawer";
import { STORAGE_KEY } from "@/providers/admin-auth-provider";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const logsResponse = {
  items: [
    {
      session_id: "session-123",
      turn_count: 2,
      last_timestamp: "2026-05-01T10:00:00Z",
      intent_types: ["cotizacion"],
      escalated: true,
    },
  ],
  total: 1,
};

const detailResponse = [
  {
    session_id: "session-123",
    turn_number: 1,
    timestamp: "2026-05-01T10:00:00Z",
    user_message: "Necesito cotizar paneles",
    bot_response: "Te ayudo con la cotización.",
    intent_type: "cotizacion",
    escalate: true,
    source_documents: [],
    input_tokens: 100,
    output_tokens: 50,
    total_tokens: 150,
    response_time_ms: 1200,
    model: "gpt-4.1-mini",
    git_commit_hash: "abc123",
    user_profile: null,
  },
];

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe("Slice 6 logs frontend", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    vi.restoreAllMocks();
  });

  it("renders logs, applies filters, and opens transcript drawer", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/admin/logs/session-123")) {
          return jsonResponse(detailResponse);
        }
        return jsonResponse(logsResponse);
      },
    );

    renderWithQuery(<LogsPage />);

    expect(await screen.findByText("session-123")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Filtrar por intención/i), "cotizacion");
    await userEvent.click(screen.getByRole("button", { name: /aplicar filtros/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("intent_type=cotizacion"),
        expect.any(Object),
      );
    });

    await userEvent.click(screen.getByRole("button", { name: /ver transcript/i }));

    expect(await screen.findByText("Necesito cotizar paneles")).toBeInTheDocument();
    expect(screen.getByText("Te ayudo con la cotización.")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
  });

  it("shows an empty drawer state when a selected session has no entries", () => {
    render(
      <LogDetailDrawer
        sessionId="empty-session"
        isOpen
        entries={[]}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/no tiene turnos registrados/i)).toBeInTheDocument();
  });
});
