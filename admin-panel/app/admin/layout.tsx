"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import {
  BarChart3,
  BookOpen,
  Database,
  FileText,
  GitBranch,
  LogOut,
  Settings,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAdminAuth } from "@/providers/admin-auth-provider";

const navItems = [
  { href: "/admin/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/admin/config", label: "Config", icon: Settings },
  { href: "/admin/escalation", label: "Escalamiento", icon: GitBranch },
  { href: "/admin/catalog", label: "Catálogo", icon: Database },
  { href: "/admin/guides", label: "Guías", icon: BookOpen },
  { href: "/admin/logs", label: "Logs", icon: FileText },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isReady, logout } = useAdminAuth();
  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (isReady && !isAuthenticated && !isLoginPage) {
      router.replace("/admin/login");
    }
  }, [isAuthenticated, isLoginPage, isReady, router]);

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (!isReady || !isAuthenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center solar-grid">
        <p className="rounded-full border bg-card px-5 py-3 text-sm text-muted-foreground shadow-sm">
          Verificando credenciales administrativas…
        </p>
      </main>
    );
  }

  return (
    <div className="min-h-screen solar-grid">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r bg-card/90 p-5 shadow-xl backdrop-blur md:block">
        <div className="mb-10">
          <p className="text-xs font-bold uppercase tracking-[0.32em] text-accent">
            ARTE
          </p>
          <h1 className="font-display text-2xl font-black text-primary">
            Admin Solar
          </h1>
        </div>
        <nav className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow"
                    : "text-muted-foreground hover:bg-secondary hover:text-secondary-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="md:pl-64">
        <header className="sticky top-0 z-10 border-b bg-background/80 px-6 py-4 backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-muted-foreground">
                Operación B2B
              </p>
              <h2 className="font-display text-2xl font-bold text-foreground">
                Centro de control
              </h2>
            </div>
            <Button
              variant="secondary"
              onClick={() => {
                logout();
                router.replace("/admin/login");
              }}
            >
              <LogOut className="h-4 w-4" />
              Salir
            </Button>
          </div>
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
