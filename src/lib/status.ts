import type { Status } from '../api/types';

/** Indonesian labels and token-based classes for transaction status. */
export const STATUS_META: Record<Status, { label: string; text: string; pill: string; bar: string; row: string; hex: string }> = {
  approved: { label: 'Disetujui', text: 'text-approved', pill: 'bg-approved-bg text-approved', bar: 'bg-approved', row: '', hex: '#2FD3A0' },
  flagged: { label: 'Ditandai', text: 'text-flagged', pill: 'bg-flagged-bg text-flagged', bar: 'bg-flagged', row: '', hex: '#F5B14C' },
  blocked: { label: 'Diblokir', text: 'text-blocked', pill: 'bg-blocked-bg text-blocked', bar: 'bg-blocked', row: 'bg-[#160D16]', hex: '#F2546B' },
};

export function statusMeta(status: string) {
  return STATUS_META[status as Status] ?? {
    label: status, text: 'text-text-secondary', pill: 'bg-secondary text-text-secondary', bar: 'bg-muted-foreground', row: '', hex: '#93A3BC',
  };
}

/** Recharts colors (SVG attributes cannot read Tailwind classes). */
export const CHART = {
  grid: '#1C2740',
  axis: '#93A3BC',
  brand: '#139EF6',
  brandDeep: '#1F6FB2',
  link: '#7CC4FA',
  approved: '#2FD3A0',
  flagged: '#F5B14C',
  blocked: '#F2546B',
  tooltip: { backgroundColor: '#111A2E', border: '1px solid #23304A', borderRadius: 8, color: '#E6EDF7', fontSize: 12 },
  tooltipLabel: { color: '#B4C1D6' },
  tooltipItem: { color: '#E6EDF7' },
  cursor: { fill: 'rgba(124,196,250,0.08)' },
} as const;
