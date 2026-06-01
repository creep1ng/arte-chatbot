import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminLayout from "@/app/admin/layout";
import AdminLoginPage from "@/app/admin/login/page";
import { AdminAuthProvider, STORAGE_KEY } from "@/providers/admin-auth-provider";

const replaceMock = vi.fn();
let pathname = "/admin/login";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => pathname,
}));

function renderWithAuth(ui: ReactNode) {
  return render(<AdminAuthProvider>{ui}</AdminAuthProvider>);
}

describe("Slice 3 admin auth bootstrap", () => {
  beforeEach(() => {
    window.localStorage.clear();
    replaceMock.mockClear();
    pathname = "/admin/login";
  });

  it("stores the admin key and redirects on login submit", async () => {
    const user = userEvent.setup();
    renderWithAuth(<AdminLoginPage />);

    await user.type(screen.getByLabelText(/API key administrativa/i), "admin-123");
    await user.click(screen.getByRole("button", { name: /guardar y entrar/i }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("admin-123");
    expect(replaceMock).toHaveBeenCalledWith("/admin/dashboard");
  });

  it("redirects unauthenticated users away from protected admin routes", async () => {
    pathname = "/admin/dashboard";

    renderWithAuth(
      <AdminLayout>
        <div>Secret dashboard</div>
      </AdminLayout>,
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/admin/login");
    });
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });
});
