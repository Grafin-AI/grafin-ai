import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TransactionNetwork } from '../api/types';
import { NetworkGraphView } from './NetworkGraph';

const net: TransactionNetwork = {
  transaction_id: 7,
  window_hours: 24,
  truncated: true,
  nodes: [
    { id: 'S', label: '8005DF****', bank: 'Bank 1420', role: 'sender', flagged_count: 0 },
    { id: 'R', label: '8000F4****', bank: 'Bank 3209', role: 'receiver', flagged_count: 0 },
    { id: 'A', label: '1111AA****', bank: 'Bank 0070', role: 'other', flagged_count: 3 },
  ],
  edges: [
    { id: 1, source: 'S', target: 'R', amount: 241339749, currency: 'IDR', event_time: '2025-09-12T14:32:08Z', status: 'blocked', fraud_score: 0.98, focal: true },
    { id: 2, source: 'A', target: 'R', amount: 5000000, currency: 'IDR', event_time: '2025-09-12T10:00:00Z', status: 'flagged', fraud_score: 0.7, focal: false },
  ],
};

describe('NetworkGraphView', () => {
  it('renders an accessible SVG with one path per edge and one group per node', () => {
    const { container } = render(<NetworkGraphView network={net} animate={false} />);
    const img = screen.getByRole('img', { name: /3 rekening, 2 transaksi, 1 ditandai, 1 diblokir/ });
    expect(img.tagName.toLowerCase()).toBe('svg');
    expect(container.querySelectorAll('path.ng-edge')).toHaveLength(2);
    expect(container.querySelectorAll('g.ng-node')).toHaveLength(3);
    expect(container.querySelector('path[data-kind="focal"]')).toHaveAttribute('stroke', '#D12C47');
    expect(container.querySelector('path[data-kind="flagged"]')).toHaveAttribute('stroke', '#B26A00');
    expect(screen.getByText('PGR')).toBeInTheDocument();
    expect(screen.getByText('PNR')).toBeInTheDocument();
  });

  it('exposes masked account, bank and amount tooltips and the truncated note', () => {
    render(<NetworkGraphView network={net} animate={false} />);
    expect(screen.getByText('1111AA**** · Bank 0070 · 3 transaksi ditandai')).toBeInTheDocument();
    expect(screen.getByText(/8005DF\*\*\*\* → 8000F4\*\*\*\* · Rp\s?241\.339\.749 · diblokir · transaksi ini/)).toBeInTheDocument();
    expect(screen.getByText(/Grafik dipangkas/)).toBeInTheDocument();
  });

  it('shows an empty message when there are no nodes', () => {
    render(<NetworkGraphView network={{ ...net, nodes: [], edges: [], truncated: false }} animate={false} />);
    expect(screen.getByText(/Tidak ada rekening terkait/)).toBeInTheDocument();
  });
});
