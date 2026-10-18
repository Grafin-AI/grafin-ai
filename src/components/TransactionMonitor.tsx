import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Eye } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { cn } from './ui/utils';
import { TransactionDetailsModal } from './TransactionDetailsModal';
import { UserProfileDetailsModal } from './UserProfileDetailsModal';
import { useLiveTransactions } from '../api/useLiveTransactions';
import { formatTime } from '../lib/formatTime';
import { formatIDR, formatScore } from '../lib/format';
import { statusMeta } from '../lib/status';
import { animateRowIn } from '../lib/motion';
import type { LiveItem, Status } from '../api/types';

type Filter = 'all' | Extract<Status, 'flagged' | 'blocked'>;

const FILTERS: { key: Filter; label: string; tone: string }[] = [
  { key: 'all', label: 'Semua', tone: 'text-foreground' },
  { key: 'flagged', label: 'Ditandai', tone: 'text-flagged' },
  { key: 'blocked', label: 'Diblokir', tone: 'text-blocked' },
];

interface TransactionMonitorProps {
  /** Reports the dataset time of the newest event (for the header LIVE badge). */
  onLatestEventTime?: (iso: string | null) => void;
}

export function TransactionMonitor({ onLatestEventTime }: TransactionMonitorProps = {}) {
  const { items } = useLiveTransactions(100);
  const [filter, setFilter] = useState<Filter>('all');
  const [selectedTransactionId, setSelectedTransactionId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);

  const counts = useMemo(() => ({
    all: items.length,
    flagged: items.filter((i) => i.status === 'flagged').length,
    blocked: items.filter((i) => i.status === 'blocked').length,
  }), [items]);
  const rows = filter === 'all' ? items : items.filter((i) => i.status === filter);

  const latest = items[0]?.event_time ?? null;
  useEffect(() => { onLatestEventTime?.(latest); }, [latest, onLatestEventTime]);

  // Slide in rows that arrived after the first paint (not the initial window).
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const known = useRef<Set<number> | null>(null);
  useLayoutEffect(() => {
    if (!items.length) return;
    if (known.current == null) {
      known.current = new Set(items.map((i) => i.seq));
      return;
    }
    const fresh = items.filter((i) => !known.current!.has(i.seq)).slice(0, 12);
    fresh.forEach((i) => known.current!.add(i.seq));
    if (known.current.size > 500) known.current = new Set(items.map((i) => i.seq));
    fresh.forEach((i) => {
      const tr = bodyRef.current?.querySelector(`tr[data-seq="${i.seq}"]`);
      if (tr) animateRowIn(tr);
    });
  }, [items]);

  const handleViewTransaction = (transactionId: number) => {
    setSelectedTransactionId(transactionId);
    setIsModalOpen(true);
  };
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTransactionId(null);
  };
  const handleOpenUserProfile = (entityId: string) => {
    setSelectedEntityId(entityId);
    setIsProfileModalOpen(true);
  };
  const handleCloseProfileModal = () => {
    setIsProfileModalOpen(false);
    setSelectedEntityId(null);
  };

  return (
    <>
      <section aria-label="Transaksi live" data-animate className="min-w-0 overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-[18px] py-3">
          <div className="flex items-center gap-2.5">
            <h2 className="text-base font-semibold text-foreground">Transaksi Live</h2>
            <span className="num rounded-full bg-secondary px-2 py-0.5 text-xs text-text-secondary">{items.length} terbaru</span>
          </div>
          <div className="flex gap-1.5" role="group" aria-label="Filter status">
            {FILTERS.map((f) => {
              const active = filter === f.key;
              return (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    'inline-flex min-h-11 items-center gap-1.5 rounded-md border border-[#C9D3E1] px-3 text-[13px] transition-colors sm:min-h-9',
                    active ? 'bg-brand-soft text-foreground' : `bg-transparent hover:bg-accent ${f.tone}`,
                  )}
                >
                  {f.label}
                  <span className="num text-xs text-muted-foreground">{counts[f.key]}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="max-h-[520px] overflow-auto">
          <table className="w-full min-w-[860px] border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-muted-foreground">
                {['ID', 'Waktu (UTC)', 'Bank', 'Kanal', 'Nominal', 'Skor model', 'Tipologi', 'Status', ''].map((h, i) => (
                  <th
                    key={i}
                    scope="col"
                    className={cn(
                      'sticky top-0 z-10 bg-card px-2 py-2.5 font-medium',
                      i === 0 && 'pl-[18px]', i === 8 && 'pr-[18px]', h === 'Nominal' && 'text-right',
                    )}
                  >
                    {h || <span className="sr-only">Aksi</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody ref={bodyRef}>
              {items.length === 0 && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-t border-surface-inset">
                  {Array.from({ length: 9 }).map((__, j) => (
                    <td key={j} className={cn('px-2 py-3', j === 0 && 'pl-[18px]')}><Skeleton className="h-4 w-full max-w-24" /></td>
                  ))}
                </tr>
              ))}
              {items.length > 0 && rows.length === 0 && (
                <tr className="border-t border-surface-inset">
                  <td colSpan={9} className="px-[18px] py-8 text-center text-muted-foreground">
                    Tidak ada transaksi dengan status ini di jendela live.
                  </td>
                </tr>
              )}
              {rows.map((item: LiveItem) => {
                const s = statusMeta(item.status);
                return (
                  <tr key={item.seq} data-seq={item.seq} className={cn('border-t border-surface-inset transition-colors hover:bg-card-2', s.row)}>
                    <td className="num py-2 pl-[18px] pr-2 text-text-secondary">TXN-{item.transaction_id}</td>
                    <td className="num whitespace-nowrap px-2 py-2 text-muted-foreground">{formatTime(item.event_time)}</td>
                    <td className="px-2 py-2 text-foreground">{item.bank || '—'}</td>
                    <td className="px-2 py-2 text-text-secondary">{item.type || '—'}</td>
                    <td className="num whitespace-nowrap px-2 py-2 text-right text-foreground">{formatIDR(item.amount)}</td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-border" aria-hidden>
                          <div className={cn('h-1.5', s.bar)} style={{ width: `${Math.max(item.fraud_score * 100, 2)}%` }} />
                        </div>
                        <span className={cn('num', s.text)}>{formatScore(item.fraud_score)}</span>
                      </div>
                    </td>
                    <td className="max-w-[200px] truncate px-2 py-2 text-text-secondary" title={item.typology ?? undefined}>
                      {item.typology ?? <span className="text-text-faint">—</span>}
                    </td>
                    <td className="px-2 py-2">
                      <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', s.pill)}>{s.label}</span>
                    </td>
                    <td className="py-1 pl-2 pr-[18px]">
                      <button
                        type="button"
                        onClick={() => handleViewTransaction(item.transaction_id)}
                        aria-label={`Lihat detail TXN-${item.transaction_id}`}
                        className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2.5 text-xs text-link transition-colors hover:bg-accent hover:text-[#095A96]"
                      >
                        <Eye className="size-3.5" aria-hidden />
                        Detail
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <TransactionDetailsModal
        transactionId={selectedTransactionId}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onOpenUserProfile={handleOpenUserProfile}
      />

      <UserProfileDetailsModal
        entityId={selectedEntityId}
        isOpen={isProfileModalOpen}
        onClose={handleCloseProfileModal}
      />
    </>
  );
}
