import { useRef, useState } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { AlertTriangle, Check, FileText, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import type { Status, TransactionExplanation } from '../api/types';
import { Skeleton } from './ui/skeleton';

gsap.registerPlugin(useGSAP);

export const REASON_CODE_LABELS: Record<string, string> = {
  'GA-FANIN': 'Pengumpulan dana (fan-in)',
  'GA-FANOUT': 'Penyebaran dana (fan-out / smurfing)',
  'GA-CYCLE': 'Siklus dana (round-tripping)',
  'GA-GATHER': 'Gather-scatter',
  'GA-VELOCITY': 'Kecepatan transaksi tidak wajar',
  'GA-AMOUNT': 'Nominal tidak biasa',
  'GA-NETWORK': 'Keterkaitan jaringan berisiko',
};

const ACTION: Record<Status, { label: string; cls: string }> = {
  blocked: { label: 'BLOKIR', cls: 'bg-blocked-bg text-blocked' },
  flagged: { label: 'TINJAU', cls: 'bg-flagged-bg text-flagged' },
  approved: { label: 'LOLOS', cls: 'bg-approved-bg text-approved' },
};

const CONFIDENCE_CLS: Record<string, string> = {
  Tinggi: 'bg-blocked-bg text-blocked',
  Sedang: 'bg-flagged-bg text-flagged',
  Rendah: 'bg-brand-soft text-link',
};

const SECTIONS: Array<[keyof TransactionExplanation, string]> = [
  ['pattern_matching', 'Pencocokan Pola'],
  ['behavior_analysis', 'Analisis Perilaku'],
  ['network_analysis', 'Analisis Jaringan'],
  ['recommendation', 'Rekomendasi'],
];

const formatSaved = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

export function explanationSummaryText(e: TransactionExplanation): string {
  return SECTIONS.map(([k, title]) => `${title}: ${String(e[k] ?? '')}`).join('\n\n');
}

const primaryBtn =
  'h-11 px-[18px] rounded-lg border-0 bg-[#0B6FB8] text-white text-sm font-semibold inline-flex items-center gap-2 hover:bg-[#095A96] disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0B6FB8] focus-visible:ring-offset-2 focus-visible:ring-offset-white';
const ghostBtn =
  'h-11 px-4 rounded-lg border border-[#C9D3E1] bg-transparent text-sm inline-flex items-center gap-2 hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0B6FB8]';

export interface InsightNarratorProps {
  /** undefined = loading/unknown, null = not generated yet. */
  explanation: TransactionExplanation | null | undefined;
  status: Status;
  isLoading?: boolean;
  /** GET failed for a reason other than "not generated". */
  loadError?: boolean;
  generating?: boolean;
  generateError?: string | null;
  onGenerate: () => void;
  draftPending?: boolean;
  onGenerateDraft?: () => void;
}

export function InsightNarrator({
  explanation, status, isLoading = false, loadError = false, generating = false,
  generateError = null, onGenerate, draftPending = false, onGenerateDraft,
}: InsightNarratorProps) {
  const scope = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);

  // Reveal the narrative sections once an explanation arrives (reduced-motion safe).
  useGSAP(() => {
    if (!explanation || typeof window.matchMedia !== 'function') return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.narr-reveal', { y: 8, opacity: 0, duration: 0.35, ease: 'power2.out', stagger: 0.06, clearProps: 'all' });
    });
    return () => mm.revert();
  }, { scope, dependencies: [explanation?.generated_at, explanation?.source] });

  const copySummary = async () => {
    if (!explanation) return;
    try {
      await navigator.clipboard.writeText(explanationSummaryText(explanation));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable: ignore */
    }
  };

  const persisted = !!explanation?.persisted;
  const action = ACTION[status] ?? ACTION.flagged;

  let caption: string | null = null;
  if (explanation) {
    caption = explanation.persisted
      ? `${explanation.model ?? 'LLM'} · tersimpan ${formatSaved(explanation.generated_at)}`
      : 'Aturan deterministik · tidak tersimpan';
  }

  return (
    <section
      ref={scope}
      aria-label="Insight Narrator"
      aria-busy={generating || isLoading}
      className="bg-card border border-border rounded-xl p-[18px] flex flex-col gap-3.5 min-w-0"
    >
      <div className="flex justify-between items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Sparkles className="w-[18px] h-[18px] text-[#139EF6]" aria-hidden="true" />
          <h3 className="m-0 text-base font-semibold">Insight Narrator</h3>
        </div>
        {caption && <span className="text-xs text-muted-foreground">{caption}</span>}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3" aria-label="Memuat penjelasan">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : generating ? (
        <div role="status" className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <Loader2 className="w-7 h-7 animate-spin text-[#139EF6]" aria-hidden="true" />
          <span className="text-sm font-medium">Menyusun penjelasan…</span>
          <span className="text-xs text-muted-foreground max-w-xs">
            Model AI sedang menganalisis pola, perilaku, dan jaringan transaksi. Biasanya 5–15 detik.
          </span>
        </div>
      ) : !explanation ? (
        <div className="rounded-xl border border-dashed border-[#C9D3E1] bg-card-2 p-4 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-sm">
              {loadError ? 'Penjelasan AI gagal dimuat.' : 'Penjelasan AI belum dibuat untuk transaksi ini.'}
            </span>
            <span className="text-xs text-muted-foreground">
              Penjelasan disusun oleh AI berdasarkan bukti model dan disimpan untuk audit.
            </span>
          </div>
          {generateError && <p role="alert" className="m-0 text-sm text-blocked">{generateError}</p>}
          <div>
            <button type="button" className={primaryBtn} onClick={onGenerate}>
              <Sparkles className="w-4 h-4" aria-hidden="true" />
              Buat Penjelasan AI
            </button>
          </div>
        </div>
      ) : (
        <>
          {!persisted && (
            <div role="status" className="narr-reveal flex items-center justify-between gap-3 flex-wrap rounded-lg bg-flagged-bg px-3 py-2">
              <span className="inline-flex items-center gap-2 text-xs font-semibold text-flagged">
                <AlertTriangle className="w-4 h-4" aria-hidden="true" />
                Mode cadangan (aturan)
                <span className="font-normal">— layanan AI tidak tersedia, penjelasan tidak disimpan.</span>
              </span>
              <button
                type="button"
                onClick={onGenerate}
                className="h-9 px-3 rounded-md border border-[#F5D9A8] text-flagged text-xs font-semibold inline-flex items-center gap-1.5 hover:bg-[#FCEBC8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B26A00]"
              >
                <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                Coba lagi
              </button>
            </div>
          )}
          {generateError && <p role="alert" className="m-0 text-sm text-blocked">{generateError}</p>}

          <div className="narr-reveal flex gap-2.5 flex-wrap">
            {explanation.reason_code && (
              <span
                className="num px-2.5 py-1 rounded-md bg-brand-soft text-link text-xs font-semibold"
                title={REASON_CODE_LABELS[explanation.reason_code] ?? explanation.reason_code}
              >
                {explanation.reason_code}
              </span>
            )}
            {explanation.confidence && (
              <span className={`px-2.5 py-1 rounded-md text-xs font-semibold ${CONFIDENCE_CLS[explanation.confidence] ?? CONFIDENCE_CLS.Rendah}`}>
                Keyakinan: {explanation.confidence}
              </span>
            )}
            <span className={`px-2.5 py-1 rounded-md text-xs font-semibold ${action.cls}`}>{action.label}</span>
          </div>

          {SECTIONS.map(([key, title]) => (
            <div key={key} className="narr-reveal flex flex-col gap-1">
              <h4 className="m-0 text-xs font-semibold text-link uppercase tracking-[0.6px]">{title}</h4>
              <p className="m-0 text-sm leading-[1.55] text-text-secondary">{String(explanation[key] ?? '')}</p>
            </div>
          ))}

          {explanation.risk_factors.length > 0 && (
            <div className="narr-reveal flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">Faktor risiko</span>
              <ul className="m-0 p-0 list-none flex flex-wrap gap-1.5">
                {explanation.risk_factors.map((f) => (
                  <li key={f.code} title={f.detail} className="px-2.5 py-1 rounded-full border border-[#C9D3E1] text-xs text-text-secondary">
                    {f.label}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {explanation.references?.length > 0 && (
            <div className="narr-reveal flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">Rujukan kebijakan</span>
              <ul className="m-0 p-0 list-none flex flex-wrap gap-1.5">
                {explanation.references.map((r) => (
                  <li key={r.id} title={r.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-card-2 border border-border-strong text-xs text-text-secondary">
                    <FileText className="w-3 h-3" aria-hidden="true" />
                    {r.title}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="narr-reveal flex gap-2.5 pt-1 flex-wrap">
            {onGenerateDraft && (
              <button
                type="button"
                className={primaryBtn}
                onClick={onGenerateDraft}
                disabled={!persisted || draftPending || !!explanation.str_draft}
                title={!persisted ? 'Tersedia setelah penjelasan AI tersimpan' : undefined}
              >
                {draftPending ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <FileText className="w-4 h-4" aria-hidden="true" />}
                {explanation.str_draft ? 'Draf LTKM tersedia' : draftPending ? 'Menyusun draf…' : 'Buat Draf LTKM'}
              </button>
            )}
            <button type="button" className={ghostBtn} onClick={copySummary}>
              {copied && <Check className="w-4 h-4 text-approved" aria-hidden="true" />}
              {copied ? 'Tersalin' : 'Salin ringkasan'}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

export default InsightNarrator;
