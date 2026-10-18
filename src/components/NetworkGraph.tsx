import { useMemo, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { Share2 } from 'lucide-react';
import { useTransactionNetwork } from '../api/queries';
import type { TransactionNetwork } from '../api/types';
import { EDGE_COLORS, layoutNetwork, summarizeNetwork, type EdgeKind } from '../lib/graph';
import { Skeleton } from './ui/skeleton';

gsap.registerPlugin(useGSAP);

const VIEW_W = 480;
const VIEW_H = 340;

const formatIDR = (amount: number, currency = 'IDR') =>
  new Intl.NumberFormat('id-ID', {
    style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(amount);

const STATUS_LABEL: Record<string, string> = {
  approved: 'disetujui', flagged: 'ditandai', blocked: 'diblokir',
};

const MARKERS: EdgeKind[] = ['focal', 'blocked', 'flagged', 'normal'];

export function NetworkGraphView({ network, animate = true }: { network: TransactionNetwork; animate?: boolean }) {
  const scope = useRef<SVGSVGElement>(null);
  const layout = useMemo(() => layoutNetwork(network, { width: VIEW_W, height: VIEW_H }), [network]);
  const labelById = useMemo(() => new Map(network.nodes.map((n) => [n.id, n])), [network]);
  const summary = summarizeNetwork(network);

  // Build-in: edges draw, then nodes pop. Skipped under reduced motion (and in jsdom).
  useGSAP(() => {
    if (!animate || typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const tl = gsap.timeline();
      tl.fromTo('.ng-edge', { strokeDasharray: 1, strokeDashoffset: 1 },
        { strokeDashoffset: 0, duration: 0.6, ease: 'power2.out', stagger: 0.01, clearProps: 'strokeDasharray,strokeDashoffset' });
      tl.from('.ng-node', { scale: 0, opacity: 0, transformOrigin: '50% 50%', duration: 0.35, ease: 'back.out(2)', stagger: 0.015 }, '-=0.3');
    });
    return () => mm.revert();
  }, { scope, dependencies: [layout, animate] });

  if (layout.nodes.length === 0) {
    return <p className="text-sm text-muted-foreground py-6 text-center">Tidak ada rekening terkait dalam {network.window_hours} jam terakhir.</p>;
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="relative rounded-[10px] bg-[#0A1020] overflow-hidden">
        <svg
          ref={scope}
          role="img"
          aria-label={summary}
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="xMidYMid meet"
          className="block w-full h-auto"
        >
          <title>{summary}</title>
          <defs>
            {MARKERS.map((kind) => (
              <marker
                key={kind}
                id={`ng-arrow-${network.transaction_id}-${kind}`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                markerUnits="userSpaceOnUse"
                orient="auto-start-reverse"
              >
                <path d="M0 0 L10 5 L0 10 z" fill={EDGE_COLORS[kind]} />
              </marker>
            ))}
          </defs>
          <g fill="none">
            {/* focal edge drawn last so it sits on top */}
            {[...layout.edges].sort((a, b) => Number(a.focal) - Number(b.focal)).map((e) => {
              const src = labelById.get(e.source);
              const dst = labelById.get(e.target);
              return (
                <path
                  key={e.id}
                  className="ng-edge"
                  data-kind={e.kind}
                  d={e.path}
                  pathLength={1}
                  stroke={e.color}
                  strokeWidth={e.width}
                  strokeLinecap="round"
                  markerEnd={`url(#ng-arrow-${network.transaction_id}-${e.kind})`}
                >
                  <title>
                    {`${src?.label ?? e.source} → ${dst?.label ?? e.target} · ${formatIDR(e.amount, e.currency || 'IDR')} · ${STATUS_LABEL[e.status] ?? e.status}${e.focal ? ' · transaksi ini' : ''}`}
                  </title>
                </path>
              );
            })}
          </g>
          <g>
            {layout.nodes.map((n) => (
              <g key={n.id} className="ng-node" transform={`translate(${n.x} ${n.y})`}>
                <title>{`${n.label} · ${n.bank}${n.flagged_count > 0 ? ` · ${n.flagged_count} transaksi ditandai` : ''}`}</title>
                <circle r={n.r} fill={n.fill} stroke={n.stroke} strokeWidth={n.strokeWidth} />
                {n.badge && (
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={10}
                    fontWeight={600}
                    fill="#E6EDF7"
                    style={{ pointerEvents: 'none' }}
                  >
                    {n.badge}
                  </text>
                )}
              </g>
            ))}
          </g>
        </svg>
        <span className="absolute left-3 bottom-2 text-[11px] text-[#93A3BC] pointer-events-none">
          PGR = pengirim · PNR = penerima · arahkan kursor untuk detail
        </span>
      </div>
      <div className="flex flex-wrap gap-3.5 text-xs text-[#B4C1D6]" aria-label="Legenda grafik">
        <span className="inline-flex items-center gap-1.5"><span className="w-[18px] h-1 bg-[#F2546B]" />transaksi ini / diblokir</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-[18px] h-[3px] bg-[#F5B14C]" />ditandai</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-[18px] h-[2px] bg-[#2B3B5C]" />normal</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-3 h-3 rounded-full border-2 border-[#139EF6] bg-[#12305A]" />pihak transaksi</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-3 h-3 rounded-full border-2 border-[#F5B14C] bg-[#172138]" />rekening terflag</span>
      </div>
      {network.truncated && (
        <p className="text-xs text-[#F7C878]">
          Grafik dipangkas ke {network.nodes.length} rekening dan {network.edges.length} transaksi paling relevan.
        </p>
      )}
    </div>
  );
}

/** "Analisis Jaringan" panel: fetches the 2-hop / 24 h network around a transaction. */
export function NetworkGraph({ transactionId, enabled = true }: { transactionId: number | null; enabled?: boolean }) {
  const { data, isLoading, isError } = useTransactionNetwork(transactionId, enabled);
  return (
    <section aria-label="Analisis Jaringan" className="bg-card border border-border rounded-xl p-4 flex flex-col gap-2.5 min-w-0">
      <div className="flex justify-between items-center gap-2">
        <h3 className="m-0 text-base font-semibold flex items-center gap-2">
          <Share2 className="w-4 h-4 text-[#139EF6]" aria-hidden="true" />
          Analisis Jaringan
        </h3>
        <span className="text-xs text-muted-foreground">{data?.window_hours ?? 24} jam · 2 lompatan</span>
      </div>
      {isLoading ? (
        <Skeleton className="h-[260px] w-full rounded-[10px]" />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Grafik jaringan belum tersedia untuk transaksi ini.</p>
      ) : (
        <NetworkGraphView network={data} />
      )}
    </section>
  );
}

export default NetworkGraph;
