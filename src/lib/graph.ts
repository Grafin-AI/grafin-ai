// Pure data -> layout helpers for the transaction network graph.
// The d3-force simulation runs synchronously for a fixed number of ticks, so the
// layout is deterministic (d3-force v3 uses a seeded LCG) and test-friendly.
import {
  forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  type SimulationLinkDatum, type SimulationNodeDatum,
} from 'd3-force';
import type { NetworkEdge, NetworkNode, TransactionNetwork } from '../api/types';

export const EDGE_COLORS = {
  focal: '#F2546B',
  blocked: '#F2546B',
  flagged: '#F5B14C',
  normal: '#2B3B5C',
} as const;

export type EdgeKind = keyof typeof EDGE_COLORS;

export interface EdgeStyle {
  kind: EdgeKind;
  color: string;
  width: number;
}

export function edgeStyle(edge: Pick<NetworkEdge, 'focal' | 'status'>): EdgeStyle {
  if (edge.focal) return { kind: 'focal', color: EDGE_COLORS.focal, width: 4 };
  if (edge.status === 'blocked') return { kind: 'blocked', color: EDGE_COLORS.blocked, width: 2 };
  if (edge.status === 'flagged') return { kind: 'flagged', color: EDGE_COLORS.flagged, width: 2 };
  return { kind: 'normal', color: EDGE_COLORS.normal, width: 1.5 };
}

export interface NodeStyle {
  r: number;
  fill: string;
  stroke: string;
  strokeWidth: number;
  /** Short in-node label for the focal accounts. */
  badge: string | null;
}

export function nodeStyle(node: Pick<NetworkNode, 'role' | 'flagged_count'>): NodeStyle {
  if (node.role === 'sender') return { r: 18, fill: '#12305A', stroke: '#139EF6', strokeWidth: 2, badge: 'PGR' };
  if (node.role === 'receiver') return { r: 18, fill: '#12305A', stroke: '#139EF6', strokeWidth: 2, badge: 'PNR' };
  if (node.flagged_count > 0) return { r: 10, fill: '#172138', stroke: '#F5B14C', strokeWidth: 2, badge: null };
  return { r: 9, fill: '#172138', stroke: '#2B3B5C', strokeWidth: 2, badge: null };
}

export interface LayoutNode extends NetworkNode, NodeStyle {
  x: number;
  y: number;
}

export interface LayoutEdge extends NetworkEdge, EdgeStyle {
  /** SVG path from source rim to target rim (straight, or quadratic when parallel). */
  path: string;
}

export interface NetworkLayout {
  width: number;
  height: number;
  nodes: LayoutNode[];
  edges: LayoutEdge[];
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  r: number;
}

export interface LayoutOptions {
  width?: number;
  height?: number;
  ticks?: number;
}

const round = (v: number) => Math.round(v * 10) / 10;

export function layoutNetwork(net: TransactionNetwork, opts: LayoutOptions = {}): NetworkLayout {
  const width = opts.width ?? 480;
  const height = opts.height ?? 340;
  const ticks = opts.ticks ?? 300;

  const styled = net.nodes.map((n) => ({ ...n, ...nodeStyle(n) }));
  const ids = new Set(styled.map((n) => n.id));
  const edges = net.edges.filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target);

  if (styled.length === 0) return { width, height, nodes: [], edges: [] };

  // Pin the focal accounts so the transaction under review reads left -> right in the middle.
  const sim: SimNode[] = styled.map((n) => {
    const node: SimNode = { id: n.id, r: n.r };
    if (n.role === 'sender') { node.fx = width * 0.36; node.fy = height / 2; }
    if (n.role === 'receiver') { node.fx = width * 0.64; node.fy = height / 2; }
    return node;
  });
  const links: SimulationLinkDatum<SimNode>[] = edges.map((e) => ({ source: e.source, target: e.target }));

  const simulation = forceSimulation(sim)
    .force('link', forceLink<SimNode, SimulationLinkDatum<SimNode>>(links).id((d) => d.id).distance(70).strength(0.6))
    .force('charge', forceManyBody().strength(-180))
    .force('center', forceCenter(width / 2, height / 2))
    .force('x', forceX(width / 2).strength(0.04))
    .force('y', forceY(height / 2).strength(0.08))
    .force('collide', forceCollide<SimNode>().radius((d) => d.r + 6))
    .stop();
  simulation.tick(ticks);

  const pos = new Map<string, { x: number; y: number }>();
  sim.forEach((s) => {
    const r = s.r + 2;
    const x = Math.min(width - r, Math.max(r, s.fx ?? s.x ?? width / 2));
    const y = Math.min(height - r, Math.max(r, s.fy ?? s.y ?? height / 2));
    pos.set(s.id, { x: round(x), y: round(y) });
  });

  const nodes: LayoutNode[] = styled.map((n) => ({ ...n, ...pos.get(n.id)! }));
  const radius = new Map(nodes.map((n) => [n.id, n.r]));

  // Group parallel/reciprocal edges by unordered pair so they can fan out as curves.
  const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);
  const groups = new Map<string, NetworkEdge[]>();
  edges.forEach((e) => {
    const k = pairKey(e.source, e.target);
    groups.set(k, [...(groups.get(k) ?? []), e]);
  });

  const layoutEdges: LayoutEdge[] = edges.map((e) => {
    const s = pos.get(e.source)!;
    const t = pos.get(e.target)!;
    const group = groups.get(pairKey(e.source, e.target))!;
    const dx = t.x - s.x;
    const dy = t.y - s.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const sr = radius.get(e.source)!;
    const tr = radius.get(e.target)! + 4; // leave room for the arrowhead
    const x1 = s.x + ux * sr;
    const y1 = s.y + uy * sr;
    const x2 = t.x - ux * tr;
    const y2 = t.y - uy * tr;
    let path = `M${round(x1)} ${round(y1)} L${round(x2)} ${round(y2)}`;
    // One edge per pair stays straight (the focal one if present); the rest bend
    // away on alternating sides, measured against the pair's canonical direction.
    const straight = group.find((g) => g.focal) ?? group[0];
    if (e !== straight) {
      const rank = group.filter((g) => g !== straight).indexOf(e) + 1;
      const side = rank % 2 === 1 ? 1 : -1;
      const bend = 26 * Math.ceil(rank / 2) * side;
      const canon = e.source < e.target ? 1 : -1;
      const mx = (x1 + x2) / 2 - uy * canon * bend;
      const my = (y1 + y2) / 2 + ux * canon * bend;
      path = `M${round(x1)} ${round(y1)} Q${round(mx)} ${round(my)} ${round(x2)} ${round(y2)}`;
    }
    return { ...e, ...edgeStyle(e), path };
  });

  return { width, height, nodes, edges: layoutEdges };
}

export function summarizeNetwork(net: TransactionNetwork): string {
  const flagged = net.edges.filter((e) => e.status === 'flagged').length;
  const blocked = net.edges.filter((e) => e.status === 'blocked').length;
  return `Jaringan transaksi ${net.window_hours} jam: ${net.nodes.length} rekening, ${net.edges.length} transaksi, ${flagged} ditandai, ${blocked} diblokir.`;
}
