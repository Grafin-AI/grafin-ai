import { MapPin, TrendingUp, TrendingDown } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { cn } from './ui/utils';
import { useProvinces } from '../api/queries';
import { formatInt } from '../lib/format';

const RISK: Record<string, { label: string; pill: string }> = {
  high: { label: 'Risiko tinggi', pill: 'bg-blocked-bg text-blocked' },
  medium: { label: 'Risiko sedang', pill: 'bg-flagged-bg text-flagged' },
  low: { label: 'Risiko rendah', pill: 'bg-approved-bg text-approved' },
};

export function GeographicMap() {
  const { data, isLoading, isError } = useProvinces();
  const provinces = data?.provinces ?? [];
  const max = Math.max(1, ...provinces.map((p) => p.fraud_count));

  return (
    <section aria-label="Sebaran wilayah" data-animate className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card px-[18px] py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
          <MapPin className="size-4 text-primary" aria-hidden /> Sebaran Wilayah
        </h2>
        <span className="text-xs text-muted-foreground">distribusi fraud per provinsi</span>
      </div>
      {isLoading ? (
        <div className="space-y-2.5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
      ) : isError ? (
        <p className="text-sm text-muted-foreground">Data provinsi gagal dimuat.</p>
      ) : provinces.length === 0 ? (
        <p className="text-sm text-muted-foreground">Belum ada data provinsi.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {provinces.map((p) => {
            const risk = RISK[p.risk_level] ?? { label: p.risk_level, pill: 'bg-secondary text-text-secondary' };
            const up = p.change_pct > 0;
            return (
              <li key={p.name} className="flex items-center gap-3 rounded-[10px] border border-border bg-card-2 px-3 py-2.5">
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm text-foreground">{p.name}</span>
                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', risk.pill)}>{risk.label}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface-inset" aria-hidden>
                    <div className="h-1.5 rounded-full bg-flagged" style={{ width: `${(p.fraud_count / max) * 100}%` }} />
                  </div>
                </div>
                <div className="text-right">
                  <div className="num text-sm text-foreground">{formatInt(p.fraud_count)}</div>
                  <div className="text-[11px] text-muted-foreground">insiden</div>
                </div>
                <div className={cn('num flex w-16 items-center justify-end gap-1 text-xs', up ? 'text-blocked' : 'text-approved')}>
                  {up ? <TrendingUp className="size-3" aria-hidden /> : <TrendingDown className="size-3" aria-hidden />}
                  <span className="sr-only">{up ? 'naik' : 'turun'}</span>
                  {Math.abs(p.change_pct).toLocaleString('id-ID', { maximumFractionDigits: 1 })}%
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
