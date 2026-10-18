import { Skeleton } from './ui/skeleton';
import { useMetricsOverview } from '../api/queries';
import { formatIDRCompact, formatInt, formatPct } from '../lib/format';
import { useRef } from 'react';
import { useCountUp, useStaggerIn } from '../lib/motion';

interface KpiProps {
  label: string;
  value: number;
  format: (n: number) => string;
  sub: string;
  valueClass: string;
  dotClass: string;
}

function Kpi({ label, value, format, sub, valueClass, dotClass }: KpiProps) {
  const ref = useCountUp<HTMLSpanElement>(value, format);
  return (
    <div data-kpi className="flex flex-col gap-2.5 rounded-xl border border-border bg-card px-[18px] py-4">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-muted-foreground">{label}</span>
        <span aria-hidden className={`size-2 rounded-full ${dotClass}`} />
      </div>
      <span ref={ref} className={`num text-[28px] font-semibold leading-none ${valueClass}`}>{format(value)}</span>
      <span className="text-xs text-muted-foreground">{sub}</span>
    </div>
  );
}

function KpiSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-[18px] py-4">
      <Skeleton className="h-3.5 w-28" />
      <Skeleton className="h-7 w-24" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

const GRID = 'grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(190px,1fr))]';

export function MetricsOverview() {
  const { data, isLoading, isError } = useMetricsOverview();
  const ref = useRef<HTMLElement>(null);
  useStaggerIn(ref, [!!data], '[data-kpi]');

  if (isLoading) {
    return (
      <section aria-label="Ringkasan" className={GRID}>
        {[0, 1, 2, 3, 4].map((i) => <KpiSkeleton key={i} />)}
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section aria-label="Ringkasan" className="rounded-xl border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Ringkasan metrik gagal dimuat. Mencoba lagi otomatis…</p>
      </section>
    );
  }

  const total = data.total_transactions;
  const approved = Math.max(0, total - data.flagged - data.blocked);
  const ratio = (n: number) => (total ? n / total : 0);

  const kpis: KpiProps[] = [
    {
      label: 'Transaksi diperiksa', value: total, format: formatInt,
      sub: 'kumulatif periode simulasi', valueClass: 'text-foreground', dotClass: 'bg-primary',
    },
    {
      label: 'Disetujui', value: ratio(approved), format: (n) => formatPct(n, 1),
      sub: `${formatInt(approved)} transaksi`, valueClass: 'text-approved', dotClass: 'bg-approved',
    },
    {
      label: 'Ditandai', value: ratio(data.flagged), format: (n) => formatPct(n, 2),
      sub: `${formatInt(data.flagged)} untuk ditinjau`, valueClass: 'text-flagged', dotClass: 'bg-flagged',
    },
    {
      label: 'Diblokir', value: data.blocked, format: formatInt,
      sub: `${formatPct(ratio(data.blocked), 2)} dari total`, valueClass: 'text-blocked', dotClass: 'bg-blocked',
    },
    {
      label: 'Nominal diproses', value: data.total_amount, format: formatIDRCompact,
      sub: `tingkat risiko ${formatPct(data.fraud_rate, 2)}`, valueClass: 'text-foreground', dotClass: 'bg-link',
    },
  ];

  return (
    <section ref={ref} aria-label="Ringkasan" className={GRID}>
      {kpis.map((k) => <Kpi key={k.label} {...k} />)}
    </section>
  );
}
