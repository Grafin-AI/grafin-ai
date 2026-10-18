import { Skeleton } from './ui/skeleton';
import { useHeatmap } from '../api/queries';
import { formatInt } from '../lib/format';

// Backend rotates Postgres dow so index 0 is Monday.
const DAYS = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'];
const DAYS_LONG = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];

// Brand blue on the dark card; alpha floor keeps empty cells visible.
const cellColor = (intensity: number) => `rgba(19, 158, 246, ${0.08 + intensity * 0.82})`;
const hh = (h: number) => `${String(h).padStart(2, '0')}:00`;

export function TransactionHeatmap() {
  const { data, isLoading, isError } = useHeatmap();
  const cells = data?.cells ?? [];
  const all = cells.flat();
  const max = all.length ? Math.max(...all) : 0;
  const total = all.reduce((a, b) => a + b, 0);

  let peak = { day: 0, hour: 0, v: -1 };
  cells.forEach((row, d) => row.forEach((v, h) => { if (v > peak.v) peak = { day: d, hour: h, v }; }));

  return (
    <section aria-label="Heatmap aktivitas" data-animate className="flex min-w-0 flex-col gap-3.5 rounded-xl border border-border bg-card px-[18px] py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-foreground">Heatmap Aktivitas</h2>
          <span className="text-xs text-muted-foreground">jumlah transaksi per hari dan jam (UTC)</span>
        </div>
        {max > 0 && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground" aria-hidden>
            rendah
            <span className="h-2 w-20 rounded-full" style={{ background: `linear-gradient(90deg, ${cellColor(0)}, ${cellColor(1)})` }} />
            tinggi
          </div>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-[220px] w-full" />
      ) : isError ? (
        <div className="grid h-[220px] place-items-center"><p className="text-sm text-muted-foreground">Data heatmap gagal dimuat.</p></div>
      ) : cells.length === 0 ? (
        <div className="grid h-[220px] place-items-center"><p className="text-sm text-muted-foreground">Belum ada data heatmap.</p></div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <div className="grid min-w-[420px] gap-[3px] [grid-template-columns:32px_repeat(24,minmax(0,1fr))]" role="img"
              aria-label={`Heatmap transaksi; puncak ${DAYS_LONG[peak.day]} ${hh(peak.hour)} dengan ${formatInt(peak.v)} transaksi`}>
              <span />
              {Array.from({ length: 24 }, (_, h) => (
                <span key={h} className="num text-center text-[10px] text-muted-foreground">{h % 6 === 0 ? String(h).padStart(2, '0') : ''}</span>
              ))}
              {DAYS.map((day, d) => (
                <div key={day} className="contents">
                  <span className="self-center text-xs text-text-secondary">{day}</span>
                  {Array.from({ length: 24 }, (_, h) => {
                    const v = cells[d]?.[h] ?? 0;
                    return (
                      <span
                        key={h}
                        className="aspect-square rounded-[3px]"
                        style={{ backgroundColor: cellColor(max > 0 ? v / max : 0) }}
                        title={`${DAYS_LONG[d]} ${hh(h)}: ${formatInt(v)} transaksi`}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3">
            <div>
              <span className="text-xs text-muted-foreground">Jam tersibuk</span>
              <p className="num text-sm font-semibold text-foreground">{peak.v >= 0 ? `${DAYS_LONG[peak.day]} ${hh(peak.hour)} · ${formatInt(peak.v)}` : '—'}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Total transaksi</span>
              <p className="num text-sm font-semibold text-foreground">{formatInt(total)}</p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
