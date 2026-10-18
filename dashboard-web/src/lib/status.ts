import type { Status } from '../api/types';

/** Indonesian labels and token-based classes for transaction status. */
export const STATUS_META: Record<Status, { label: string; text: string; pill: string; bar: string; row: string; hex: string }> = {
  approved: { label: 'Disetujui', text: 'text-approved', pill: 'bg-approved-bg text-approved', bar: 'bg-approved', row: '', hex: '#0E8A5F' },
  flagged: { label: 'Ditandai', text: 'text-flagged', pill: 'bg-flagged-bg text-flagged', bar: 'bg-flagged', row: '', hex: '#B26A00' },
  blocked: { label: 'Diblokir', text: 'text-blocked', pill: 'bg-blocked-bg text-blocked', bar: 'bg-blocked', row: 'bg-[#FFF7F8]', hex: '#D12C47' },
};

export function statusMeta(status: string) {
  return STATUS_META[status as Status] ?? {
    label: status, text: 'text-text-secondary', pill: 'bg-secondary text-text-secondary', bar: 'bg-muted-foreground', row: '', hex: '#5B6B82',
  };
}

/** Recharts colors (SVG attributes cannot read Tailwind classes). */
export const CHART = {
  grid: '#E3E8F0',
  axis: '#5B6B82',
  brand: '#139EF6',
  brandSoft: '#9CCFF7',
  link: '#0B6FB8',
  approved: '#0E8A5F',
  flagged: '#B26A00',
  blocked: '#D12C47',
  tooltip: { backgroundColor: '#FFFFFF', border: '1px solid #E3E8F0', borderRadius: 8, color: '#0F172A', fontSize: 12, boxShadow: '0 4px 12px rgba(15,23,42,0.08)' },
  tooltipLabel: { color: '#334155' },
  tooltipItem: { color: '#0F172A' },
  cursor: { fill: 'rgba(19,158,246,0.06)' },
} as const;

/** Entity risk levels as stored by the API (High/Medium/Low). */
export const RISK_META: Record<string, { label: string; pill: string; text: string; bar: string; hex: string }> = {
  High: { label: 'Tinggi', pill: 'bg-blocked-bg text-blocked', text: 'text-blocked', bar: 'bg-blocked', hex: '#D12C47' },
  Medium: { label: 'Sedang', pill: 'bg-flagged-bg text-flagged', text: 'text-flagged', bar: 'bg-flagged', hex: '#B26A00' },
  Low: { label: 'Rendah', pill: 'bg-approved-bg text-approved', text: 'text-approved', bar: 'bg-approved', hex: '#0E8A5F' },
};
const UNKNOWN = { label: 'Tidak diketahui', pill: 'bg-secondary text-text-secondary', text: 'text-text-secondary', bar: 'bg-muted-foreground', hex: '#5B6B82' };
export const riskMeta = (level: string | null | undefined) => (level && RISK_META[level]) || UNKNOWN;

