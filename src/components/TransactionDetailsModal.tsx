import { useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from './ui/dialog';
import { Skeleton } from './ui/skeleton';
import {
  apiErrorMessage, useGenerateExplanation, useGenerateStrDraft, useTransactionDetail,
  useTransactionExplanation,
} from '../api/queries';
import type { Status, TransactionDetail } from '../api/types';
import { InsightNarrator } from './InsightNarrator';
import { NetworkGraph } from './NetworkGraph';
import { StrDraft } from './StrDraft';

interface TransactionDetailsModalProps {
  transactionId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenUserProfile?: (entityId: string) => void;
}

const STATUS_PILL: Record<Status, { label: string; cls: string }> = {
  blocked: { label: 'DIBLOKIR', cls: 'bg-[#3A1420] text-[#F2546B]' },
  flagged: { label: 'DITANDAI', cls: 'bg-[#33250D] text-[#F5B14C]' },
  approved: { label: 'DISETUJUI', cls: 'bg-[#0F2E25] text-[#2FD3A0]' },
};

const scoreColor = (s: number) => (s >= 0.85 ? 'text-[#F2546B]' : s >= 0.6 ? 'text-[#F5B14C]' : 'text-[#2FD3A0]');

const formatAmount = (amount: number, currency = 'IDR') =>
  new Intl.NumberFormat('id-ID', {
    style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(amount);

const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString('id-ID', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

type Side = 'from' | 'to';

function PartyCard({ txn, side, onOpenUserProfile }: {
  txn: TransactionDetail;
  side: Side;
  onOpenUserProfile?: (entityId: string) => void;
}) {
  const isFrom = side === 'from';
  const bank = (isFrom ? txn.from_bank_name || txn.from_bank : txn.to_bank_name || txn.to_bank) || '—';
  const account = (isFrom ? txn.from_account : txn.to_account) || '—';
  const entityId = isFrom ? txn.from_entity_id : txn.to_entity_id;
  const entityName = isFrom ? txn.from_entity_name : txn.to_entity_name;
  const label = isFrom ? 'Pengirim' : 'Penerima';

  return (
    <div className="bg-card border border-border rounded-xl px-4 py-3.5 flex flex-col gap-1.5 min-w-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-[15px] font-semibold truncate">{entityName || '—'}</span>
      <span className="font-mono tabular-nums text-[13px] text-[#B4C1D6] truncate">
        <span>{bank}</span> · <span>{account}</span>
      </span>
      {onOpenUserProfile && (
        <button
          type="button"
          aria-label={`Buka profil ${label.toLowerCase()}`}
          disabled={!entityId}
          onClick={() => entityId && onOpenUserProfile(entityId)}
          className="self-start font-mono text-xs text-[#7CC4FA] hover:text-[#B5DDFC] disabled:text-[#93A3BC] disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#139EF6] rounded"
        >
          {entityId ? `Profil ${entityId}` : 'Profil tidak tersedia'}
        </button>
      )}
    </div>
  );
}

export function TransactionDetailsModal({ transactionId, isOpen, onClose, onOpenUserProfile }: TransactionDetailsModalProps) {
  const { data: txn, isLoading, isError } = useTransactionDetail(transactionId);
  // GET only reads the stored explanation (null = not generated). No LLM call until the user asks.
  const explanationQuery = useTransactionExplanation(transactionId, isOpen);
  const generate = useGenerateExplanation(transactionId);
  const draft = useGenerateStrDraft(transactionId);
  const { reset: resetGenerate } = generate;
  const { reset: resetDraft } = draft;

  // Mutation state belongs to one transaction: clear it when another one is opened.
  useEffect(() => {
    resetGenerate();
    resetDraft();
  }, [transactionId, resetGenerate, resetDraft]);

  const explanation = explanationQuery.data;
  const pill = txn ? STATUS_PILL[txn.status] ?? STATUS_PILL.flagged : null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent
        aria-describedby={undefined}
        className="max-w-[1200px] sm:max-w-[1200px] w-[calc(100%-2rem)] max-h-[92vh] p-0 gap-0 flex flex-col overflow-hidden rounded-2xl border-[#23304A] bg-[#0B1120] text-[#E6EDF7]"
      >
        {/* Header */}
        <div className="flex justify-between items-start gap-4 px-[26px] py-[22px] pr-14 border-b border-[#1C2740]">
          <div className="flex flex-col gap-2 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <DialogTitle className="m-0 text-xl font-semibold">
                {isLoading ? <Skeleton className="h-6 w-48" /> : isError ? 'Gagal memuat transaksi' : (
                  <>Transaksi <span className="font-mono tabular-nums">#{txn?.id ?? transactionId}</span></>
                )}
              </DialogTitle>
              {pill && <span className={`px-2.5 py-[3px] rounded-full text-xs font-semibold ${pill.cls}`}>{pill.label}</span>}
              {txn?.typology && (
                <span className="px-2.5 py-[3px] rounded-full text-xs bg-[#142238] text-[#7CC4FA]">{txn.typology}</span>
              )}
            </div>
            {txn && (
              <span className="font-mono tabular-nums text-[13px] text-[#93A3BC]">
                {formatDateTime(txn.event_time)} · {txn.type} · {formatAmount(txn.amount, txn.currency || 'IDR')}
              </span>
            )}
          </div>
          {txn && (
            <div className="flex flex-col items-end shrink-0">
              <span className="text-xs text-[#93A3BC]">Skor risiko</span>
              <span className={`font-mono tabular-nums text-[30px] leading-tight font-semibold ${scoreColor(txn.fraud_score)}`}>
                {txn.fraud_score.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          )}
        </div>

        <div className="overflow-y-auto min-h-0">
          {isLoading && (
            <div className="p-[26px] grid gap-4" aria-label="Memuat transaksi">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_1fr] gap-4">
                <Skeleton className="h-96 w-full" />
                <Skeleton className="h-96 w-full" />
              </div>
            </div>
          )}

          {isError && (
            <div className="p-8 text-center text-[#F2546B]" role="alert">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2" aria-hidden="true" />
              <p>Gagal memuat data transaksi. Silakan coba lagi.</p>
            </div>
          )}

          {txn && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 px-[26px] py-[18px]">
                <PartyCard txn={txn} side="from" onOpenUserProfile={onOpenUserProfile} />
                <PartyCard txn={txn} side="to" onOpenUserProfile={onOpenUserProfile} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-4 px-[26px] pb-6">
                <InsightNarrator
                  explanation={explanation}
                  status={txn.status}
                  isLoading={explanationQuery.isLoading}
                  loadError={explanationQuery.isError}
                  generating={generate.isPending}
                  generateError={generate.isError ? apiErrorMessage(generate.error) : null}
                  onGenerate={() => generate.mutate()}
                  draftPending={draft.isPending}
                  onGenerateDraft={() => draft.mutate()}
                />
                <div className="flex flex-col gap-4 min-w-0">
                  <NetworkGraph transactionId={transactionId} enabled={isOpen} />
                  <StrDraft
                    draft={explanation?.str_draft}
                    pending={draft.isPending}
                    error={draft.isError ? apiErrorMessage(draft.error) : null}
                    canGenerate={!!explanation?.persisted}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
