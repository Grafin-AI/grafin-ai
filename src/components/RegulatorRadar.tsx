import { useMemo } from 'react';
import { isAxiosError } from 'axios';
import { Radar, ShieldCheck } from 'lucide-react';
import { useInstitutions } from '../api/queries';
import type { InstitutionFlow, InstitutionStat } from '../api/types';
import { Skeleton } from './ui/skeleton';

export const FEDERATION_NOTE =
  'Simulasi federasi — prototipe memakai model terpusat; data dipartisi per institusi';

const MATRIX_SIZE = 8;

const fmtInt = (n: number) => n.toLocaleString('id-ID');
const fmtIDR = (n: number) =>
  new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n);
/** flagged_rate is expected as a fraction (0..1); tolerate a percentage too. */
const toFraction = (r: number) => (r > 1 ? r / 100 : r);
const fmtPct = (r: number) =>
  `${(toFraction(r) * 100).toLocaleString('id-ID', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

/** Heat colour for a matrix cell relative to the matrix maximum. */
export function heatColor(v: number, max: number): { bg: string; fg: string } {
  if (v <= 0 || max <= 0) return { bg: '#0A1020', fg: '#5B6B85' };
  const t = v / max;
  if (t < 0.1) return { bg: '#14213A', fg: '#D3DCEA' };
  if (t < 0.3) return { bg: '#1B3A63', fg: '#D3DCEA' };
  if (t < 0.6) return { bg: '#1F6FB2', fg: '#E6EDF7' };
  return { bg: '#139EF6', fg: '#04121F' };
}

export interface FlowMatrix {
  banks: string[];
  cells: number[][];
  amounts: number[][];
  max: number;
}

/** Build a from_bank x to_bank matrix over the given bank order. */
export function buildFlowMatrix(banks: string[], flows: InstitutionFlow[]): FlowMatrix {
  const index = new Map(banks.map((b, i) => [b, i]));
  const cells = banks.map(() => banks.map(() => 0));
  const amounts = banks.map(() => banks.map(() => 0));
  let max = 0;
  for (const f of flows) {
    const i = index.get(f.from_bank);
    const j = index.get(f.to_bank);
    if (i == null || j == null) continue;
    cells[i][j] += f.flagged_count;
    amounts[i][j] += f.amount;
    max = Math.max(max, cells[i][j]);
  }
  return { banks, cells, amounts, max };
}

function InstitutionCard({ inst, maxRate }: { inst: InstitutionStat; maxRate: number }) {
  const rate = toFraction(inst.flagged_rate);
  const width = maxRate > 0 ? Math.max(2, Math.round((rate / maxRate) * 100)) : 0;
  return (
    <li className="bg-card border border-border rounded-xl px-4 py-3.5 flex flex-col gap-2 list-none">
      <div className="flex justify-between items-center gap-2">
        <span className="text-sm font-semibold truncate">{inst.bank}</span>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-[#5BE3B5] shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-[#2FD3A0]" aria-hidden="true" />
          node aktif
        </span>
      </div>
      <span className="font-mono tabular-nums text-[22px] font-semibold" title="Jumlah transaksi">
        {fmtInt(inst.transactions)}
      </span>
      <div
        className="h-1.5 rounded-sm bg-[#1C2740] overflow-hidden"
        role="meter"
        aria-label={`Rasio ditandai ${inst.bank}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(rate * 1000) / 10}
      >
        <div className="h-1.5 bg-[#F5B14C]" style={{ width: `${width}%` }} />
      </div>
      <div className="font-mono tabular-nums flex justify-between text-xs text-[#93A3BC]">
        <span>ditandai {fmtPct(inst.flagged_rate)}</span>
        <span className="text-[#F2546B]">blokir {fmtInt(inst.blocked)}</span>
      </div>
    </li>
  );
}

function FlowMatrixTable({ matrix }: { matrix: FlowMatrix }) {
  const short = (b: string) => b.replace(/^Bank\s+/i, '');
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1 text-xs">
        <caption className="sr-only">Jumlah transaksi terflag dari bank (baris) ke bank (kolom)</caption>
        <thead>
          <tr>
            <th scope="col" className="text-[#93A3BC] font-medium text-left px-2 py-1">dari \ ke</th>
            {matrix.banks.map((b) => (
              <th key={b} scope="col" className="font-mono tabular-nums text-[#93A3BC] font-medium px-2 py-1" title={b}>
                {short(b)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.banks.map((from, i) => (
            <tr key={from}>
              <th scope="row" className="font-mono tabular-nums text-[#B4C1D6] font-medium text-left px-2 py-1 whitespace-nowrap" title={from}>
                {short(from)}
              </th>
              {matrix.cells[i].map((v, j) => {
                const c = heatColor(v, matrix.max);
                return (
                  <td
                    key={matrix.banks[j]}
                    className="font-mono tabular-nums w-14 h-9 text-center rounded-md"
                    style={{ background: c.bg, color: c.fg }}
                    title={`${from} → ${matrix.banks[j]}: ${fmtInt(v)} terflag · ${fmtIDR(matrix.amounts[i][j])}`}
                  >
                    {fmtInt(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PrivacyShield() {
  return (
    <section aria-label="Perisai privasi" className="bg-card border border-border rounded-xl px-[18px] py-4 flex flex-col gap-3 min-w-0">
      <h2 className="m-0 text-base font-semibold flex items-center gap-2">
        <ShieldCheck className="w-4 h-4 text-[#2FD3A0]" aria-hidden="true" />
        Perisai Privasi — yang dikirim tiap node
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-[#111A2E] border border-[#23304A] rounded-[10px] p-3 flex flex-col gap-1.5">
          <span className="text-xs text-[#F2546B] font-semibold">Tetap di institusi</span>
          <span className="text-[13px] text-[#D3DCEA]">Nama nasabah, NIK, nomor rekening, nominal mentah</span>
        </div>
        <div className="bg-[#111A2E] border border-[#23304A] rounded-[10px] p-3 flex flex-col gap-1.5">
          <span className="text-xs text-[#2FD3A0] font-semibold">Dikirim ke Hub</span>
          <span className="text-[13px] text-[#D3DCEA]">hash rekening asal/tujuan + vektor fitur</span>
        </div>
      </div>
      <pre
        aria-label="Contoh payload yang dikirim node"
        className="font-mono tabular-nums m-0 p-3 rounded-lg bg-[#0A1020] border border-[#1C2740] text-xs leading-relaxed text-[#B4C1D6] whitespace-pre-wrap"
      >{`{
  "src": "sha256:9f2c…41ab",
  "dst": "sha256:07de…c3f0",
  "vector128": [0.12, -0.84, 0.33, …],
  "ts": "2025-09-12T14:32:08Z"
}`}</pre>
      <p className="m-0 text-xs text-muted-foreground">
        Hub hanya menerima ringkasan yang tidak dapat dibalik ke identitas nasabah; skor dan peringatan dikembalikan ke node asal.
      </p>
    </section>
  );
}

export function RegulatorRadar() {
  const { data, isLoading, isError, error } = useInstitutions();

  const institutions = data?.institutions ?? [];
  const maxRate = useMemo(
    () => institutions.reduce((m, i) => Math.max(m, toFraction(i.flagged_rate)), 0),
    [institutions],
  );
  const matrix = useMemo(
    () => buildFlowMatrix(institutions.slice(0, MATRIX_SIZE).map((i) => i.bank), data?.flows ?? []),
    [institutions, data?.flows],
  );

  const notAvailable = isError && isAxiosError(error) && error.response?.status === 404;

  return (
    <div className="flex flex-col gap-[18px] p-6 min-w-0">
      <header className="flex flex-wrap justify-between items-center gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-2xl font-semibold flex items-center gap-2">
            <Radar className="w-6 h-6 text-[#139EF6]" aria-hidden="true" />
            Radar Regulator
          </h1>
          <span className="text-sm text-muted-foreground">
            Pandangan lintas institusi untuk BI / OJK — aliran dana mencurigakan antar bank
          </span>
        </div>
        <span role="note" className="px-3 py-2 rounded-lg bg-[#33250D] text-[#F7C878] text-[13px] max-w-[520px]">
          {FEDERATION_NOTE}
        </span>
      </header>

      {isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3" aria-label="Memuat data institusi">
          {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-[116px] rounded-xl" />)}
        </div>
      ) : isError && !notAvailable ? (
        <div role="alert" className="bg-card border border-border rounded-xl p-8 text-center text-sm text-[#F2546B]">
          Gagal memuat data institusi. Silakan coba lagi nanti.
        </div>
      ) : notAvailable || institutions.length === 0 ? (
        <div className="bg-card border border-dashed border-[#2B3B5C] rounded-xl p-10 text-center flex flex-col items-center gap-2">
          <Radar className="w-8 h-8 text-[#93A3BC]" aria-hidden="true" />
          <span className="text-sm font-medium">Data radar lintas institusi belum tersedia</span>
          <span className="text-xs text-muted-foreground max-w-md">
            Agregat per institusi akan muncul di sini setelah layanan analitik institusi aktif dan data transaksi dimuat.
          </span>
        </div>
      ) : (
        <>
          <section aria-label="Node institusi">
            <ul className="m-0 p-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
              {institutions.map((inst) => <InstitutionCard key={inst.bank} inst={inst} maxRate={maxRate} />)}
            </ul>
          </section>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,480px),1fr))] gap-4">
            <section aria-label="Matriks aliran" className="bg-card border border-border rounded-xl px-[18px] py-4 flex flex-col gap-3 min-w-0">
              <h2 className="m-0 text-base font-semibold">Aliran Terflag Antar Institusi</h2>
              {matrix.max === 0 ? (
                <p className="m-0 text-sm text-muted-foreground">Belum ada aliran terflag antar institusi.</p>
              ) : (
                <FlowMatrixTable matrix={matrix} />
              )}
              <span className="text-xs text-muted-foreground">
                Sel gelap = sedikit; sel terang = banyak transaksi terflag. Diagonal = di dalam satu institusi.
              </span>
            </section>
            <PrivacyShield />
          </div>
        </>
      )}

      {(notAvailable || (!isLoading && !isError && institutions.length === 0)) && <PrivacyShield />}
    </div>
  );
}

export default RegulatorRadar;
