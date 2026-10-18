import { useLayoutEffect, useRef } from 'react';
import { Check } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { cn } from './ui/utils';
import { useAlerts, useAckAlert } from '../api/queries';
import { formatTime } from '../lib/formatTime';
import { formatInt } from '../lib/format';
import { pulseOnce } from '../lib/motion';
import type { AlertItem } from '../api/types';

// Alerts are raised by the ingest pipeline for blocked transactions.
function levelMeta(severity: string) {
  switch (severity) {
    case 'critical':
    case 'high':
      return { label: 'BLOKIR', text: 'text-blocked', bar: 'bg-blocked', border: 'border-[#F6C7D0]', blocked: true };
    case 'medium':
    case 'warning':
      return { label: 'TINJAU', text: 'text-flagged', bar: 'bg-flagged', border: 'border-[#F5D9A8]', blocked: false };
    default:
      return { label: severity.toUpperCase() || 'INFO', text: 'text-link', bar: 'bg-link', border: 'border-border', blocked: false };
  }
}

function AlertRow({ alert, onAck }: { alert: AlertItem; onAck: (id: number) => void }) {
  const m = levelMeta(alert.severity);
  return (
    <li
      data-alert-id={alert.id}
      data-blocked={m.blocked || undefined}
      className={cn('relative flex gap-3 rounded-[10px] border bg-card-2 p-3', m.border, alert.acknowledged && 'opacity-70')}
    >
      <span data-pulse-ring aria-hidden className="pointer-events-none absolute -inset-px rounded-[10px] opacity-0 ring-2 ring-blocked" />
      <span aria-hidden className={cn('w-1 flex-none rounded-sm', m.bar)} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className={cn('text-[13px] font-semibold', m.text)}>{m.label}</span>
          <span className="num text-xs text-muted-foreground">#{alert.id} · seq {alert.event_seq}</span>
        </div>
        <span className="text-[13px] text-foreground">{alert.typology ?? 'Transaksi diblokir model'}</span>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="num text-xs text-muted-foreground">{formatTime(alert.event_time)}</span>
          {alert.acknowledged ? (
            <span className="inline-flex items-center gap-1 text-xs text-approved">
              <Check className="size-3" aria-hidden /> Sudah ditinjau
            </span>
          ) : (
            <button
              type="button"
              onClick={() => onAck(alert.id)}
              className="-my-2 inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-link transition-colors hover:bg-accent hover:text-[#095A96]"
            >
              <Check className="size-3" aria-hidden />
              Tandai ditinjau
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export function AlertsPanel() {
  const { data, isLoading, isError } = useAlerts('all');
  const ackMutation = useAckAlert();

  const alerts = data?.alerts ?? [];
  const unread = alerts.filter((a) => !a.acknowledged).length;

  // Pulse alerts that arrive after the first load, once.
  const listRef = useRef<HTMLUListElement>(null);
  const seen = useRef<Set<number> | null>(null);
  useLayoutEffect(() => {
    if (!alerts.length) return;
    if (seen.current == null) {
      seen.current = new Set(alerts.map((a) => a.id));
      return;
    }
    const fresh = alerts.filter((a) => !seen.current!.has(a.id));
    fresh.forEach((a) => {
      seen.current!.add(a.id);
      const el = listRef.current?.querySelector(`[data-alert-id="${a.id}"][data-blocked]`);
      if (el) pulseOnce(el);
    });
  }, [alerts]);

  return (
    <section aria-label="Peringatan" data-animate className="flex min-w-0 flex-col gap-2.5 rounded-xl border border-border bg-card px-4 py-3.5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Peringatan</h2>
        {unread > 0 && (
          <span className="num rounded-full bg-blocked-bg px-2 py-0.5 text-xs text-blocked">{formatInt(unread)} baru</span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2.5">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[88px] w-full rounded-[10px]" />)}
        </div>
      ) : isError ? (
        <p className="text-sm text-muted-foreground">Peringatan gagal dimuat.</p>
      ) : alerts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Belum ada peringatan.</p>
      ) : (
        <ul ref={listRef} className="-mr-2 flex max-h-[520px] flex-col gap-2.5 overflow-y-auto pr-2">
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onAck={(id) => ackMutation.mutate(id)} />
          ))}
        </ul>
      )}
    </section>
  );
}
