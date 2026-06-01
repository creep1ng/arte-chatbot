import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CatalogPage from "@/app/admin/catalog/page";
import GuideEditorPage from "@/app/admin/guides/[intent]/page";
import { S3Tree } from "@/components/s3-tree";
import { STORAGE_KEY } from "@/providers/admin-auth-provider";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ intent: "cotizacion-paneles" }),
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  usePathname: () => "/admin/guides/cotizacion-paneles",
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const catalogResponse = {
  products: [
    {
      nombre_comercial: "Panel Solar 550W",
      fabricante: "Arte Energy",
      categoria: "paneles",
      subcategoria: "monocristalino",
      descripcion: "Panel de alta eficiencia",
      ruta_s3: "raw/paneles/panel-550w.pdf",
      variantes: [],
      parametros_comunes: { potencia_w: 550 },
    },
  ],
};

const guideResponse = {
  intent: "cotizacion-paneles",
  content: "# Cotización\n\n- Validar consumo",
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

describe("Slice 5 admin frontend pages", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(STORAGE_KEY, "admin-key");
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it("expands S3 folders and selects files", async () => {
    const selectedKeys: string[] = [];
    const handleSelectedKeysChange = vi.fn((keys: string[]) => {
      selectedKeys.splice(0, selectedKeys.length, ...keys);
    });

    render(
      <S3Tree
        nodes={[
          {
            name: "raw",
            key: "raw/",
            type: "folder",
            children: [
              {
                name: "paneles",
                key: "raw/paneles/",
                type: "folder",
                children: [
                  {
                    name: "panel-550w.pdf",
                    key: "raw/paneles/panel-550w.pdf",
                    type: "file",
                    size: 2048,
                    last_modified: "2026-05-01T10:00:00Z",
                  },
                ],
              },
            ],
          },
        ]}
        selectedKeys={selectedKeys}
        onSelectedKeysChange={handleSelectedKeysChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /expandir paneles/i }));
    const checkbox = screen.getByLabelText(/seleccionar panel-550w.pdf/i);
    fireEvent.click(checkbox);

    expect(screen.getByText("panel-550w.pdf")).toBeInTheDocument();
    expect(handleSelectedKeysChange).toHaveBeenCalledWith([
      "raw/paneles/panel-550w.pdf",
    ]);
  });

  it("exposes view and download actions for S3 files", async () => {
    const handleViewFile = vi.fn();
    const handleDownloadFile = vi.fn();

    render(
      <S3Tree
        nodes={[
          {
            name: "raw",
            key: "raw/",
            type: "folder",
            children: [
              {
                name: "paneles",
                key: "raw/paneles/",
                type: "folder",
                children: [
                  {
                    name: "panel-550w.pdf",
                    key: "raw/paneles/panel-550w.pdf",
                    type: "file",
                    size: 2048,
                  },
                ],
              },
            ],
          },
        ]}
        selectedKeys={[]}
        onSelectedKeysChange={vi.fn()}
        onViewFile={handleViewFile}
        onDownloadFile={handleDownloadFile}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /expandir paneles/i }));
    await userEvent.click(screen.getByRole("button", { name: /ver panel-550w.pdf/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /descargar panel-550w.pdf/i }),
    );

    expect(handleViewFile).toHaveBeenCalledWith("raw/paneles/panel-550w.pdf");
    expect(handleDownloadFile).toHaveBeenCalledWith("raw/paneles/panel-550w.pdf");
  });

  it("loads catalog products and renders the table", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(catalogResponse));

    renderWithQuery(<CatalogPage />);

    expect(await screen.findByText("Panel Solar 550W")).toBeInTheDocument();
    expect(screen.getByText("Arte Energy")).toBeInTheDocument();
    expect(screen.getByText("raw/paneles/panel-550w.pdf")).toBeInTheDocument();
  });

  it("opens catalog technical sheets through a presigned URL", async () => {
    const openMock = vi.spyOn(window, "open").mockImplementation(() => null);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST") {
          return jsonResponse({
            url: "https://bucket.s3.amazonaws.com/raw/paneles/panel-550w.pdf?sig=1",
            key: "raw/paneles/panel-550w.pdf",
            expires_in: 300,
          });
        }
        return jsonResponse(catalogResponse);
      },
    );

    renderWithQuery(<CatalogPage />);

    await userEvent.click(await screen.findByRole("button", { name: /ver ficha/i }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(postCall).toBeTruthy();
      expect(JSON.parse(postCall?.[1]?.body as string)).toEqual({
        key: "raw/paneles/panel-550w.pdf",
        disposition: "inline",
      });
      expect(openMock).toHaveBeenCalledWith(
        "https://bucket.s3.amazonaws.com/raw/paneles/panel-550w.pdf?sig=1",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });

  it("downloads catalog technical sheets through a presigned URL", async () => {
    const anchorClickMock = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST") {
          return jsonResponse({
            url: "https://bucket.s3.amazonaws.com/raw/paneles/panel-550w.pdf?sig=1",
            key: "raw/paneles/panel-550w.pdf",
            expires_in: 300,
          });
        }
        return jsonResponse(catalogResponse);
      },
    );

    renderWithQuery(<CatalogPage />);

    await userEvent.click(await screen.findByRole("button", { name: /descargar/i }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(postCall).toBeTruthy();
      expect(JSON.parse(postCall?.[1]?.body as string)).toEqual({
        key: "raw/paneles/panel-550w.pdf",
        disposition: "attachment",
      });
      expect(anchorClickMock).toHaveBeenCalled();
    });
  });

  it("renders guide editor preview and saves markdown", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return jsonResponse({ intent: "cotizacion-paneles", content: "# Actualizada" });
        }
        return jsonResponse(guideResponse);
      },
    );

    renderWithQuery(<GuideEditorPage />);

    const editor = await screen.findByLabelText(/editor markdown/i);
    await waitFor(() => {
      expect(screen.getByTestId("markdown-preview")).toHaveTextContent("Cotización");
    });

    await userEvent.clear(editor);
    await userEvent.type(editor, "# Actualizada");
    await userEvent.click(screen.getByRole("button", { name: /guardar guía/i }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
      expect(putCall).toBeTruthy();
      expect(JSON.parse(putCall?.[1]?.body as string)).toMatchObject({
        intent: "cotizacion-paneles",
        content: "# Actualizada",
      });
    });
  });
});
