import { render, screen, within } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ q: {} as Record<string, unknown> }));
vi.mock('../api/queries', () => ({ useInstitutions: () => state.q }));

import RegulatorRadarDefault, { FEDERATION_NOTE, RegulatorRadar, buildFlowMatrix, heatColor } from './RegulatorRadar';

const notFound = new AxiosError('nf', '404', undefined, undefined, {
  status: 404, statusText: '', data: { detail: 'Not Found' }, headers: {}, config: { headers: new AxiosHeaders() },
});

describe('RegulatorRadar', () => {
  beforeEach(() => {
    state.q = { data: undefined, isLoading: false, isError: false, error: null };
  });

  it('exports the page as default and named', () => {
    expect(RegulatorRadarDefault).toBe(RegulatorRadar);
  });

  it('shows a friendly empty state when the endpoint 404s', () => {
    state.q = { data: undefined, isLoading: false, isError: true, error: notFound };
    render(<RegulatorRadar />);
    expect(screen.getByText(/belum tersedia/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText(FEDERATION_NOTE)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Perisai privasi' })).toBeInTheDocument();
  });

  it('shows an error for other failures', () => {
    state.q = { data: undefined, isLoading: false, isError: true, error: new Error('boom') };
    render(<RegulatorRadar />);
    expect(screen.getByRole('alert')).toHaveTextContent(/Gagal memuat/);
  });

  it('renders institution cards and the flagged-flow matrix', () => {
    state.q = {
      isLoading: false, isError: false, error: null,
      data: {
        institutions: [
          { bank: 'Bank 0070', transactions: 182340, flagged: 2900, blocked: 212, flagged_rate: 0.016 },
          { bank: 'Bank 1420', transactions: 96512, flagged: 3300, blocked: 188, flagged_rate: 0.034 },
        ],
        flows: [
          { from_bank: 'Bank 0070', to_bank: 'Bank 1420', flagged_count: 12, amount: 5e8 },
          { from_bank: 'Bank 1420', to_bank: 'Bank 1420', flagged_count: 55, amount: 9e8 },
          { from_bank: 'Lainnya', to_bank: 'Bank 1420', flagged_count: 3, amount: 1 },
        ],
      },
    };
    render(<RegulatorRadar />);
    const nodes = within(screen.getByRole('region', { name: 'Node institusi' }));
    expect(nodes.getAllByRole('listitem')).toHaveLength(2);
    expect(nodes.getByText('182.340')).toBeInTheDocument();
    expect(nodes.getByText('ditandai 3,4%')).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByText('55')).toHaveAttribute('title', expect.stringContaining('Bank 1420 → Bank 1420: 55 terflag'));
    expect(table.getAllByRole('row')).toHaveLength(3);
  });
});

describe('radar helpers', () => {
  it('builds a from x to matrix ignoring unknown banks', () => {
    const m = buildFlowMatrix(['A', 'B'], [
      { from_bank: 'A', to_bank: 'B', flagged_count: 4, amount: 10 },
      { from_bank: 'A', to_bank: 'B', flagged_count: 1, amount: 5 },
      { from_bank: 'X', to_bank: 'B', flagged_count: 9, amount: 1 },
    ]);
    expect(m.cells).toEqual([[0, 5], [0, 0]]);
    expect(m.amounts[0][1]).toBe(15);
    expect(m.max).toBe(5);
  });

  it('shades cells relative to the maximum', () => {
    expect(heatColor(0, 10).bg).toBe('#0A1020');
    expect(heatColor(10, 10).bg).toBe('#139EF6');
    expect(heatColor(1, 100).bg).toBe('#14213A');
  });
});
