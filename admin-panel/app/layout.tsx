import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Toaster } from "sonner";

import "./globals.css";

import { AdminAuthProvider } from "@/providers/admin-auth-provider";
import { AdminQueryClientProvider } from "@/providers/query-client";
import { ThemeProvider } from "@/providers/theme-provider";

export const metadata: Metadata = {
  title: "ARTE Admin Panel",
  description: "Panel operativo para Arte Soluciones Energéticas",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <AdminQueryClientProvider>
            <AdminAuthProvider>{children}</AdminAuthProvider>
            <Toaster richColors position="top-right" />
          </AdminQueryClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
