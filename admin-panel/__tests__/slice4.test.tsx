import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConfigPage from "@/app/admin/config/page";
import DashboardPage from "@/app/admin/dashboard/page";
import EscalationPage from "@/app/admin/escalation/page";
import { STORAGE_KEY } from "@/providers/admin-auth-provider";

vi.mock("recharts", () => ({
  Bar: () => <div data-testid="bar" />,
  BarChart: ({ children }: { children?: ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Cell: () => <div data-testid="cell" />,
  Pie: ({ children }: { children?: ReactNode }) => (
    <div data-testid="pie">{children}</div>
  ),
  PieChart: ({ children }: { children?: ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  ResponsiveContainer: ({ children }: { children?: ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Tooltip: () => <div data-testid="tooltip" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
}));

const dashboardMetrics = {
  active_sessions: 3,
  total_input_tokens: 1200,
  total_output_tokens: 800,
  total_tokens: 2000,
  escalation_rate: 0.25,
  intent_distribution: {
    cotizacion: 4,
    soporte: 2,
  },
};

const configSnapshot = {
  mutable: {
    llm_model: "gpt-4.1-mini",
    log_level: "INFO",
    escalation_confidence_threshold: 0.7,
    false_positive_limit: 0.12,
    false_negative_limit: 0.18,
    whatsapp_formatter_enabled: true,
    split_messages_enabled: false,
    msg_delay_min_ms: 1000,
    msg_delay_max_ms: 3000,
    greeting_enabled: true,
    greeting_timezone: "America/Mexico_City",
    multi_message_buffer_enabled: true,
    buffer_window_seconds: 8,
    conversation_logging_enabled: true,
    conversation_log_prefix: "conversations/",
    admin_api_key: "***REDACTED***",
  },
  immutable: {
    openai_api_key: "***REDACTED***",
    aws_access_key_id: "***REDACTED***",
    aws_secret_access_key: "***REDACTED***",
    aws_bucket_name: "arte-chatbot-data",
    aws_region: "us-east-1",
    chat_api_key: "***REDACTED***",
    git_commit_hash: "abc123",
  },
};

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

describe("Slice 4 admin frontend pages", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    vi.restoreAllMocks();
  });

  it("renders dashboard stats cards from the metrics API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(dashboardMetrics),
    );

    renderWithQuery(<DashboardPage />);

    expect(await screen.findByText("Sesiones activas")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Total tokens")).toBeInTheDocument();
    expect(screen.getByText("2,000")).toBeInTheDocument();
    expect(screen.getAllByText("25%").length).toBeGreaterThan(0);
    expect(screen.getByTestId("intent-pie-chart")).toBeInTheDocument();
  });

  it("disables immutable config fields and submits mutable settings", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return jsonResponse(configSnapshot);
        }
        return jsonResponse(configSnapshot);
      },
    );
    const user = userEvent.setup();

    renderWithQuery(<ConfigPage />);

    const bucketInput = await screen.findByDisplayValue("arte-chatbot-data");
    expect(bucketInput).toBeDisabled();

    const thresholdInput = screen.getByLabelText(
      /Umbral de confianza para escalamiento/i,
    );
    await user.clear(thresholdInput);
    await user.type(thresholdInput, "0.55");
    await user.click(
      screen.getByRole("button", { name: /guardar configuración/i }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/admin/config"),
        expect.objectContaining({ method: "PUT" }),
      );
    });

    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const payload = JSON.parse(putCall?.[1]?.body as string);
    expect(payload).toMatchObject({
      escalation_confidence_threshold: 0.55,
      llm_model: "gpt-4.1-mini",
    });
    expect(payload).not.toHaveProperty("admin_api_key");
  });

  it("updates escalation threshold and submits it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return jsonResponse(configSnapshot);
        }
        return jsonResponse(configSnapshot);
      },
    );
    const user = userEvent.setup();

    renderWithQuery(<EscalationPage />);

    const thresholdSlider = await screen.findByLabelText(/Umbral de confianza/i);
    fireEvent.change(thresholdSlider, { target: { value: "0.42" } });
    await user.click(
      screen.getByRole("button", { name: /guardar escalamiento/i }),
    );

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([, init]) => init?.method === "PUT",
      );
      expect(JSON.parse(putCall?.[1]?.body as string)).toMatchObject({
        escalation_confidence_threshold: 0.42,
      });
    });
  });
});
