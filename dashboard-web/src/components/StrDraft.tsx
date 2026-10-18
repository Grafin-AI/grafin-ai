import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Check, Copy, FileText, Loader2, Printer } from 'lucide-react';
import type { StrDraft as StrDraftData, StrDraftParty } from '../api/types';

export const DEFAULT_DRAFT_NOTE = 'DRAF — perlu verifikasi analis sebelum dilaporkan ke PPATK';

/** "Nama (Bank · rekening)"; tolerates a plain string from older payloads. */
export function formatParty(p: StrDraftParty | string): string {
  if (typeof p === 'string') return p;
  const where = [p.bank, p.rekening].filter(Boolean).join(' · ');
  return p.nama ? `${p.nama} (${where})` : where;
}

/** Plain-text rendering of the draft for the clipboard. */
export function formatStrDraftText(d: StrDraftData): string {
  return [
    `${d.nomor_draf}`,
    d.catatan || DEFAULT_DRAFT_NOTE,
    '',
    `Pihak: Pengirim ${formatParty(d.pihak.pengirim)} → Penerima ${formatParty(d.pihak.penerima)}`,
    `Kronologi: ${d.kronologi}`,
    `Indikator:\n${d.indikator.map((i) => `- ${i}`).join('\n')}`,
    `Analisis: ${d.analisis}`,
    `Rekomendasi: ${d.rekomendasi}`,
  ].join('\n');
}

const PRINT_ATTR = 'data-str-print';

// Print only the draft section: hide everything else for the duration of the print job.
function printSection(el: HTMLElement) {
  el.setAttribute(PRINT_ATTR, '');
  const style = document.createElement('style');
  style.textContent = `@media print {
  body * { visibility: hidden !important; }
  [${PRINT_ATTR}], [${PRINT_ATTR}] * { visibility: visible !important; color: #000 !important; background: #fff !important; border-color: #999 !important; }
  [${PRINT_ATTR}] { position: fixed; inset: 0; padding: 24px; }
  [${PRINT_ATTR}] [data-no-print] { display: none !important; }
}`;
  document.head.appendChild(style);
  let done = false;
  const cleanup = () => {
    if (done) return;
    done = true;
    style.remove();
    el.removeAttribute(PRINT_ATTR);
    window.removeEventListener('afterprint', cleanup);
  };
  window.addEventListener('afterprint', cleanup);
  try {
    window.print();
  } finally {
    // print() blocks in most browsers; the timeout covers the ones where it does not.
    window.setTimeout(cleanup, 1000);
  }
}

interface StrDraftProps {
  draft: StrDraftData | null | undefined;
  /** Draft generation in flight (LLM, can take several seconds). */
  pending?: boolean;
  /** Error message to show (already human readable). */
  error?: string | null;
  /** Whether a persisted explanation exists (drafting is possible). */
  canGenerate?: boolean;
}

export function StrDraft({ draft, pending = false, error = null, canGenerate = false }: StrDraftProps) {
  const ref = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copy = async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(formatStrDraftText(draft));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const fields: Array<[string, ReactNode]> = draft
    ? [
        ['Pihak', `Pengirim ${formatParty(draft.pihak.pengirim)} → Penerima ${formatParty(draft.pihak.penerima)}`],
        ['Kronologi', draft.kronologi],
        ['Indikator', draft.indikator.length > 1 ? (
          <ul className="m-0 pl-4 list-disc space-y-0.5">{draft.indikator.map((i) => <li key={i}>{i}</li>)}</ul>
        ) : draft.indikator.join('; ')],
        ['Analisis', draft.analisis],
        ['Rekomendasi', draft.rekomendasi],
      ]
    : [];

  return (
    <section
      ref={ref}
      aria-label="Draf LTKM"
      className="bg-card border border-border rounded-xl p-4 flex flex-col gap-2.5 min-w-0"
    >
      <div className="flex justify-between items-center gap-2">
        <h3 className="m-0 text-base font-semibold flex items-center gap-2">
          <FileText className="w-4 h-4 text-[#139EF6]" aria-hidden="true" />
          Draf LTKM
        </h3>
        {draft && <span className="num text-xs text-muted-foreground">{draft.nomor_draf}</span>}
      </div>

      {draft ? (
        <>
          <div role="note" className="px-3 py-2 rounded-lg bg-flagged-bg text-flagged text-xs font-medium">
            {draft.catatan || DEFAULT_DRAFT_NOTE}
          </div>
          <dl className="m-0 flex flex-col gap-2">
            {fields.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[110px_1fr] gap-2.5 text-[13px] leading-normal">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="m-0 text-text-secondary">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="flex gap-2" data-no-print>
            <button
              type="button"
              onClick={copy}
              className="h-10 px-3.5 rounded-lg border border-[#C9D3E1] bg-transparent text-[13px] inline-flex items-center gap-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0B6FB8]"
            >
              {copied ? <Check className="w-4 h-4 text-approved" aria-hidden="true" /> : <Copy className="w-4 h-4" aria-hidden="true" />}
              {copied ? 'Tersalin' : 'Salin'}
            </button>
            <button
              type="button"
              onClick={() => ref.current && printSection(ref.current)}
              className="h-10 px-3.5 rounded-lg border border-[#C9D3E1] bg-transparent text-[13px] inline-flex items-center gap-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0B6FB8]"
            >
              <Printer className="w-4 h-4" aria-hidden="true" />
              Cetak
            </button>
          </div>
        </>
      ) : pending ? (
        <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground py-3">
          <Loader2 className="w-4 h-4 animate-spin text-[#139EF6]" aria-hidden="true" />
          Menyusun draf LTKM…
        </div>
      ) : (
        <p className="m-0 text-sm text-muted-foreground py-2">
          {canGenerate
            ? 'Draf LTKM belum dibuat. Gunakan tombol "Buat Draf LTKM" pada Insight Narrator.'
            : 'Draf LTKM tersedia setelah penjelasan AI tersimpan.'}
        </p>
      )}
      {error && !draft && (
        <p role="alert" className="m-0 text-sm text-blocked">{error}</p>
      )}
    </section>
  );
}

export default StrDraft;
