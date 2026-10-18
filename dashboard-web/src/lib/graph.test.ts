import { describe, expect, it } from 'vitest';
import type { TransactionNetwork } from '../api/types';
import { EDGE_COLORS, edgeStyle, layoutNetwork, nodeStyle, summarizeNetwork } from './graph';

const net: TransactionNetwork = {
  transaction_id: 1,
  window_hours: 24,
  truncated: false,
  nodes: [
    { id: 'S', label: '8005DF****', bank: 'Bank 1420', role: 'sender', flagged_count: 0 },
    { id: 'R', label: '8000F4****', bank: 'Bank 3209', role: 'receiver', flagged_count: 2 },
    { id: 'A', label: '1111AA****', bank: 'Bank 0070', role: 'other', flagged_count: 1 },
    { id: 'B', label: '2222BB****', bank: 'Bank 0070', role: 'other', flagged_count: 0 },
  ],
  edges: [
    { id: 1, source: 'S', target: 'R', amount: 1e6, currency: 'IDR', event_time: '2025-09-12T14:32:08Z', status: 'blocked', fraud_score: 0.98, focal: true },
    { id: 2, source: 'A', target: 'R', amount: 2e5, currency: 'IDR', event_time: '2025-09-12T10:00:00Z', status: 'flagged', fraud_score: 0.7, focal: false },
    { id: 3, source: 'B', target: 'R', amount: 1e5, currency: 'IDR', event_time: '2025-09-12T09:00:00Z', status: 'approved', fraud_score: 0.1, focal: false },
    { id: 4, source: 'R', target: 'S', amount: 9e5, currency: 'IDR', event_time: '2025-09-12T13:00:00Z', status: 'blocked', fraud_score: 0.9, focal: false },
    { id: 5, source: 'R', target: 'GHOST', amount: 1, currency: 'IDR', event_time: '2025-09-12T13:00:00Z', status: 'approved', fraud_score: 0, focal: false },
  ],
};

describe('graph helpers', () => {
  it('styles edges: focal thick red, blocked red, flagged amber, others neutral', () => {
    expect(edgeStyle(net.edges[0])).toMatchObject({ color: EDGE_COLORS.focal, kind: 'focal' });
    expect(edgeStyle(net.edges[0]).width).toBeGreaterThan(edgeStyle(net.edges[3]).width);
    expect(edgeStyle(net.edges[3])).toMatchObject({ color: EDGE_COLORS.blocked, kind: 'blocked' });
    expect(edgeStyle(net.edges[1])).toMatchObject({ color: EDGE_COLORS.flagged, kind: 'flagged' });
    expect(edgeStyle(net.edges[2])).toMatchObject({ color: EDGE_COLORS.normal, kind: 'normal' });
  });

  it('styles nodes by role and flagged count', () => {
    expect(nodeStyle(net.nodes[0]).stroke).toBe('#139EF6');
    expect(nodeStyle(net.nodes[1]).stroke).toBe('#139EF6'); // focal role wins over flagged
    expect(nodeStyle(net.nodes[2]).stroke).toBe('#B26A00');
    expect(nodeStyle(net.nodes[3]).stroke).toBe('#94A3B8');
    expect(nodeStyle(net.nodes[0]).r).toBeGreaterThan(nodeStyle(net.nodes[3]).r);
  });

  it('lays out every node inside the viewBox, drops dangling edges, and is deterministic', () => {
    const a = layoutNetwork(net, { width: 480, height: 340 });
    const b = layoutNetwork(net, { width: 480, height: 340 });
    expect(a.nodes).toHaveLength(4);
    expect(a.edges.map((e) => e.id)).toEqual([1, 2, 3, 4]);
    for (const n of a.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(n.r);
      expect(n.x).toBeLessThanOrEqual(480 - n.r);
      expect(n.y).toBeGreaterThanOrEqual(n.r);
      expect(n.y).toBeLessThanOrEqual(340 - n.r);
      expect(Number.isFinite(n.x) && Number.isFinite(n.y)).toBe(true);
    }
    expect(a.nodes.map((n) => [n.x, n.y])).toEqual(b.nodes.map((n) => [n.x, n.y]));
    // sender sits left of receiver so the focal edge reads left-to-right
    const s = a.nodes.find((n) => n.id === 'S')!;
    const r = a.nodes.find((n) => n.id === 'R')!;
    expect(s.x).toBeLessThan(r.x);
    // reciprocal edges are curved so they do not overlap
    expect(a.edges.find((e) => e.id === 4)!.path).toContain('Q');
    expect(a.edges.find((e) => e.id === 2)!.path).not.toContain('Q');
  });

  it('handles an empty network', () => {
    const l = layoutNetwork({ ...net, nodes: [], edges: [] });
    expect(l.nodes).toEqual([]);
    expect(l.edges).toEqual([]);
  });

  it('summarizes the network for screen readers', () => {
    expect(summarizeNetwork(net)).toBe(
      'Jaringan transaksi 24 jam: 4 rekening, 5 transaksi, 1 ditandai, 2 diblokir.',
    );
  });
});
