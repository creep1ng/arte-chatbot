import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminChatPage from "@/app/admin/chat/page";
import AdminLayout from "@/app/admin/layout";
import { ADMIN_CHAT_HISTORY_KEY } from "@/components/chat/chat-history";
import { STORAGE_KEY, AdminAuthProvider } from "@/providers/admin-auth-provider";

const replaceMock = vi.fn();
let pathname = "/admin/chat";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithProviders(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AdminAuthProvider>{ui}</AdminAuthProvider>
    </QueryClientProvider>,
  );
}

describe("Admin chat workbench", () => {
  beforeEach(() => {
    pathname = "/admin/chat";
    replaceMock.mockClear();
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("blocks unauthenticated access through the admin layout", async () => {
    renderWithProviders(
      <AdminLayout>
        <AdminChatPage />
      </AdminLayout>,
    );

    expect(await screen.findByText(/verificando credenciales/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/admin/login");
    });
  });

  it("renders the chat route inside the existing admin navigation", async () => {
    window.localStorage.setItem(STORAGE_KEY, "admin-key");

    renderWithProviders(
      <AdminLayout>
        <AdminChatPage />
      </AdminLayout>,
    );

    expect(await screen.findByRole("heading", { name: /chat ui de pruebas/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /chat/i })).toHaveAttribute(
      "href",
      "/admin/chat",
    );
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute(
      "href",
      "/admin/dashboard",
    );
    expect(screen.getByRole("link", { name: /config/i })).toHaveAttribute(
      "href",
      "/admin/config",
    );
    expect(screen.getByRole("link", { name: /logs/i })).toHaveAttribute(
      "href",
      "/admin/logs",
    );
  });

  it("restores saved recent conversation history when selected", async () => {
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    window.localStorage.setItem(
      ADMIN_CHAT_HISTORY_KEY,
      JSON.stringify([
        {
          id: "conversation-a",
          sessionId: "session-a",
          title: "Consulta panel Tiger",
          createdAt: "2026-06-01T12:00:00.000Z",
          updatedAt: "2026-06-01T12:01:00.000Z",
          messages: [
            { id: "u1", role: "user", content: "Necesito ficha Tiger" },
            { id: "a1", role: "assistant", content: "La ficha Tiger está disponible." },
          ],
        },
      ]),
    );

    renderWithProviders(<AdminChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: /consulta panel tiger/i }));

    expect(screen.getByText("Necesito ficha Tiger")).toBeInTheDocument();
    expect(screen.getByText("La ficha Tiger está disponible.")).toBeInTheDocument();
  });

  it("sends chat through admin auth, renders split bubbles, and never stores CHAT_API_KEY", async () => {
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        response: "fallback ignored",
        session_id: "session-split",
        source_documents: [],
        messages: ["Primera parte técnica", "Segunda parte técnica"],
        delays_ms: [100, 200],
        escalate: false,
        input_tokens: 10,
        output_tokens: 20,
        total_tokens: 30,
      }),
    );

    renderWithProviders(<AdminChatPage />);

    await userEvent.type(
      screen.getByLabelText(/mensaje para probar el chatbot/i),
      "Compará paneles de 550W",
    );
    await userEvent.click(screen.getByRole("button", { name: /enviar mensaje/i }));

    expect(await screen.findByText("Primera parte técnica")).toBeInTheDocument();
    expect(screen.getByText("Segunda parte técnica")).toBeInTheDocument();
    expect(screen.getAllByText("Entrada: 10")).toHaveLength(2);
    expect(screen.getAllByText("Salida: 20")).toHaveLength(2);
    expect(screen.queryByText("fallback ignored")).not.toBeInTheDocument();
    expect(screen.getAllByText("Compará paneles de 550W").length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/admin/chat"),
        expect.objectContaining({
          method: "POST",
          headers: expect.any(Headers),
        }),
      );
    });
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Headers).get("X-Admin-API-Key")).toBe("admin-key");
    expect(window.localStorage.getItem("CHAT_API_KEY")).toBeNull();
  });

  it("shows deduplicated datasheet sources in a modal with admin download flow", async () => {
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    const openMock = vi.spyOn(window, "open").mockImplementation(() => null);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST" && String(init.body).includes("presigned")) {
          return jsonResponse({
            url: "https://signed.example/raw/paneles/tiger.pdf",
            key: "raw/paneles/tiger.pdf",
            expires_in: 300,
          });
        }

        if (String(_input).includes("/admin/s3/presigned-download")) {
          return jsonResponse({
            url: "https://signed.example/raw/paneles/tiger.pdf",
            key: "raw/paneles/tiger.pdf",
            expires_in: 300,
          });
        }

        return jsonResponse({
          response: "Usé una ficha técnica.",
          session_id: "session-source",
          source_documents: [
            { ruta: "raw/paneles/tiger.pdf", contenido_relevante: "Potencia 550W" },
            { ruta: "raw/paneles/tiger.pdf", contenido_relevante: "Potencia 550W" },
          ],
          messages: [],
          delays_ms: [],
          escalate: false,
        });
      },
    );

    renderWithProviders(<AdminChatPage />);

    await userEvent.type(screen.getByLabelText(/mensaje para probar el chatbot/i), "Ficha Tiger");
    await userEvent.click(screen.getByRole("button", { name: /enviar mensaje/i }));
    await userEvent.click(await screen.findByRole("button", { name: /ver fichas técnicas/i }));

    expect(screen.getByRole("dialog", { name: /fichas técnicas usadas/i })).toBeInTheDocument();
    expect(screen.getAllByText("tiger.pdf")).toHaveLength(1);
    expect(screen.getByText("raw/paneles/tiger.pdf")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /abrir tiger.pdf/i }));

    await waitFor(() => {
      const presignedCall = fetchMock.mock.calls.find(([input]) =>
        String(input).includes("/admin/s3/presigned-download"),
      );
      expect(presignedCall).toBeTruthy();
      expect(JSON.parse(presignedCall?.[1]?.body as string)).toEqual({
        key: "raw/paneles/tiger.pdf",
        disposition: "inline",
      });
      expect(openMock).toHaveBeenCalledWith(
        "https://signed.example/raw/paneles/tiger.pdf",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });
});
