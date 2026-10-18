/** Indonesian (id-ID) number formatting shared by the dashboard surfaces. */

const int = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 0 });
const idr = new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat('id-ID', { notation: 'compact', maximumFractionDigits: 1 });

/** 864812 -> "864.812" */
export const formatInt = (n: number) => int.format(Math.round(n));

/** 0.0205 -> "2,05%" */
export const formatPct = (ratio: number, digits = 2) =>
  `${(ratio * 100).toLocaleString('id-ID', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;

/** 241339749 -> "Rp 241.339.749" (non-breaking space normalised) */
export const formatIDR = (n: number) => idr.format(n).replace(/ /g, ' ');

/** 1.2e12 -> "Rp 1,2 T", 3.4e9 -> "Rp 3,4 M", 5e6 -> "Rp 5 jt" */
export const formatIDRCompact = (n: number) => `Rp ${compact.format(n).replace(/ /g, ' ')}`;

/** 0.98 -> "0,98" */
export const formatScore = (s: number, digits = 2) =>
  s.toLocaleString('id-ID', { minimumFractionDigits: digits, maximumFractionDigits: digits });
