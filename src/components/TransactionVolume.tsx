import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Skeleton } from './ui/skeleton';
import { useVolume } from '../api/queries';
import { formatInt } from '../lib/format';
import { CHART } from '../lib/status';

type PeriodType = '24h' | 'weekly' | 'monthly' | 'yearly';

const PERIODS: Record<PeriodType, { label: string; title: string }> = {
  '24h': { label: '24 jam', title: 'Volume per Jam' },
  weekly: { label: 'Mingguan', title: 'Volume per Hari' },
  monthly: { label: 'Bulanan', title: 'Volume per Hari' },
  yearly: { label: 'Tahunan', title: 'Volume per Bulan' },
};

/** Bucket ISO timestamps are UTC (dataset time); label them without shifting zones. */
function bucketLabel(iso: string, period: PeriodType): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const opts: Intl.DateTimeFormatOptions =
    period === '24h' ? { hour: '2-digit', minute: '2-digit', hour12: false }
      : period === 'yearly' ? { month: 'short', year: 'numeric' }
        : { day: '2-digit', month: 'short' };
  return d.toLocaleString('id-ID', { timeZone: 'UTC', ...opts });
}

export function TransactionVolume() {
  const [period, setPeriod] = useState<PeriodType>('24h');
  const { data, isLoading, isError } = useVolume(period);

  // flagged in the volume series counts flagged + blocked (backend: status in (flagged, blocked)).
  const rows = data?.series.map((pt) => ({
    label: bucketLabel(pt.bucket, period),
    safe: Math.max(0, pt.count - pt.flagged),
    risky: pt.flagged,
  })) ?? [];

  return (
    <section aria-label="Volume transaksi" data-animate className="flex min-w-0 flex-col gap-3.5 rounded-xl border border-border bg-card px-[18px] py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col">
          <h2 className="text-base font-semibold text-foreground">{PERIODS[period].title}</h2>
          <span className="text-xs text-muted-foreground">disetujui · berisiko (ditandai + diblokir)</span>
        </div>
        <Select value={period} onValueChange={(v: PeriodType) => setPeriod(v)}>
          <SelectTrigger className="h-11 w-32 text-xs sm:h-9" aria-label="Periode volume">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(PERIODS) as PeriodType[]).map((p) => (
              <SelectItem key={p} value={p} className="text-xs">{PERIODS[p].label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <Skeleton className="h-[240px] w-full" />
      ) : isError ? (
        <div className="grid h-[240px] place-items-center"><p className="text-sm text-muted-foreground">Data volume gagal dimuat.</p></div>
      ) : rows.length === 0 ? (
        <div className="grid h-[240px] place-items-center"><p className="text-sm text-muted-foreground">Belum ada data untuk periode ini.</p></div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="18%">
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: CHART.axis }} stroke={CHART.grid} tickLine={false} minTickGap={12} />
            <YAxis tick={{ fontSize: 11, fill: CHART.axis }} stroke={CHART.grid} tickLine={false} tickFormatter={(v) => formatInt(v)} width={56} />
            <Tooltip
              contentStyle={CHART.tooltip} labelStyle={CHART.tooltipLabel} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
              formatter={(v, name) => [formatInt(Number(v)), name === 'safe' ? 'Disetujui' : 'Berisiko']}
            />
            <Legend
              iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: CHART.axis }}
              formatter={(v) => (v === 'safe' ? 'Disetujui' : 'Berisiko')}
            />
            <Bar dataKey="safe" stackId="v" fill={CHART.brandSoft} />
            <Bar dataKey="risky" stackId="v" fill={CHART.flagged} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}
