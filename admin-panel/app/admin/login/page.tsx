"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAdminAuth } from "@/providers/admin-auth-provider";

export default function AdminLoginPage() {
  const router = useRouter();
  const { isAuthenticated, isReady, setApiKey } = useAdminAuth();
  const [key, setKey] = useState("");

  useEffect(() => {
    if (isReady && isAuthenticated) {
      router.replace("/admin/dashboard");
    }
  }, [isAuthenticated, isReady, router]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!key.trim()) {
      return;
    }
    setApiKey(key);
    router.replace("/admin/dashboard");
  };

  return (
    <main className="grid min-h-screen place-items-center solar-grid px-6">
      <section className="w-full max-w-md overflow-hidden rounded-[2rem] border bg-card shadow-2xl">
        <div className="bg-primary p-8 text-primary-foreground">
          <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent shadow-lg">
            <ShieldCheck className="h-7 w-7" />
          </div>
          <p className="text-xs font-bold uppercase tracking-[0.34em] text-primary-foreground/70">
            Acceso interno
          </p>
          <h1 className="mt-2 font-display text-4xl font-black">
            Panel ARTE
          </h1>
          <p className="mt-3 text-sm leading-6 text-primary-foreground/80">
            Ingresa la API key administrativa para gestionar métricas,
            configuración y contenidos operativos.
          </p>
        </div>
        <form className="space-y-5 p-8" onSubmit={handleSubmit}>
          <label className="space-y-2 text-sm font-semibold" htmlFor="api-key">
            API key administrativa
            <Input
              id="api-key"
              name="api-key"
              type="password"
              autoComplete="off"
              placeholder="arte-admin-key"
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
          </label>
          <Button className="w-full" size="lg" type="submit">
            Guardar y entrar
          </Button>
        </form>
      </section>
    </main>
  );
}
