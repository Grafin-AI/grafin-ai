import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Skeleton } from './ui/skeleton';
import { useFraudAnalytics } from '../api/queries';
import { formatIDRCompact, formatInt, formatPct } from '../lib/format';
import { CHART } from '../lib/status';

const CARD = 'flex flex-col gap-3.5 rounded-xl border border-border bg-card px-[18px] py-4';

/**
 * "Pola Jaringan Terdeteksi": flagged + blocked transactions per typology as
 * horizontal bars. Log scale, because the model-only bucket dwarfs the rest.
 */
export function TypologyBars() {
  const { data, isLoading, isError } = useFraudAnalytics();
  const rows = [...(data?.distribution ?? [])].sort((a, b) => b.count - a.count);
  const maxLog = Math.log10(Math.max(10, ...rows.map((r) => r.count)));

  return (
    <section aria-label="Tipologi" data-animate className={CARD}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">Pola Jaringan Terdeteksi</h2>
        <span className="text-xs text-muted-foreground">transaksi ditandai + diblokir · skala log</span>
      </div>
      {isLoading ? (
        <div className="space-y-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4 w-full" />)}</div>
      ) : isError ? (
        <p className="text-sm text-muted-foreground">Data tipologi gagal dimuat.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Belum ada pola terdeteksi.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((r) => {
            const w = r.count > 0 ? Math.max(2, Math.round((Math.log10(r.count + 1) / maxLog) * 100)) : 0;
            return (
              <li key={r.typology} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_64px] items-center gap-3 text-[13px] sm:grid-cols-[210px_1fr_64px]">
                <span className="truncate text-text-secondary" title={r.typology}>{r.typology}</span>
                <div className="h-2.5 overflow-hidden rounded-full bg-surface-inset" aria-hidden>
                  <div className="h-2.5 rounded-full bg-primary" style={{ width: `${w}%` }} />
                </div>
                <span className="num text-right text-foreground">{formatInt(r.count)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-text-secondary">{label}</span>
        <span className="num font-semibold text-foreground">{formatPct(value, 1)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-inset" aria-hidden>
        <div className="h-2 rounded-full" style={{ width: `${Math.min(100, value * 100)}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

const axisTick = { fontSize: 11, fill: CHART.axis };

/** Analytics page: detection metrics + typology counts and amounts. */
export function FraudAnalytics() {
  const { data, isLoading, isError } = useFraudAnalytics();

  const rows = data?.distribution.map((item) => ({
    fraudType: item.typology,
    totalAmount: item.total_amount,
    count: item.count,
  })) ?? [];
  const detection = data?.detection;

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className={CARD}><Skeleton className="h-[280px] w-full" /></div>)}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={CARD}>
        <p className="text-sm text-muted-foreground">Analitik fraud gagal dimuat.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section data-animate aria-label="Metrik deteksi" className={CARD}>
        <h2 className="text-base font-semibold text-foreground">Metrik Deteksi</h2>
        {detection ? (
          <div className="space-y-4">
            <MetricBar label="Presisi" value={detection.precision} color={CHART.brand} />
            <MetricBar label="Recall" value={detection.recall} color={CHART.approved} />
            <MetricBar label="F1" value={detection.f1} color={CHART.link} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Metrik deteksi belum tersedia.</p>
        )}
      </section>

      <section data-animate aria-label="Jumlah per tipologi" className={CARD}>
        <h2 className="text-base font-semibold text-foreground">Jumlah per Tipologi</h2>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Belum ada data.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="fraudType" tick={{ ...axisTick, fontSize: 10 }} angle={-30} textAnchor="end" interval={0} height={56} stroke={CHART.grid} />
              <YAxis tick={axisTick} tickFormatter={(v) => formatInt(v)} stroke={CHART.grid} width={56} />
              <Tooltip
                contentStyle={CHART.tooltip} labelStyle={CHART.tooltipLabel} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
                formatter={(v) => [formatInt(Number(v)), 'Transaksi']}
              />
              <Bar dataKey="count" fill={CHART.brand} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section data-animate aria-label="Nominal per tipologi" className={CARD}>
        <h2 className="text-base font-semibold text-foreground">Nominal per Tipologi</h2>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Belum ada data.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="fraudType" tick={{ ...axisTick, fontSize: 10 }} angle={-30} textAnchor="end" interval={0} height={56} stroke={CHART.grid} />
              <YAxis tick={axisTick} tickFormatter={(v) => formatIDRCompact(Number(v)).replace('Rp ', '')} stroke={CHART.grid} width={56} />
              <Tooltip
                contentStyle={CHART.tooltip} labelStyle={CHART.tooltipLabel} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
                formatter={(v) => [formatIDRCompact(Number(v)), 'Total nominal']}
              />
              <Bar dataKey="totalAmount" fill={CHART.link} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>
    </div>
  );
}
