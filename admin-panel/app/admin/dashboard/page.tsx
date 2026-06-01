export default function DashboardPage() {
  return (
    <section className="rounded-[2rem] border bg-card/95 p-8 shadow-xl">
      <p className="text-xs font-bold uppercase tracking-[0.3em] text-accent">
        Slice 3 Bootstrap
      </p>
      <h1 className="mt-3 font-display text-4xl font-black text-primary">
        Dashboard administrativo
      </h1>
      <p className="mt-4 max-w-2xl text-muted-foreground">
        La estructura base está lista. Slice 4 conectará esta pantalla con
        TanStack Query, Recharts y las métricas reales de
        /admin/dashboard/metrics.
      </p>
    </section>
  );
}
