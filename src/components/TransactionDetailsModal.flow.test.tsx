import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { TransactionDetail, TransactionExplanation } from '../api/types';
import { TransactionDetailsModal } from './TransactionDetailsModal';

const txn: TransactionDetail = {
  id: 7, bank: 'BRI', amount: 1_000_000, currency: 'IDR', type: 'BI-FAST', fraud_score: 0.91,
  typology: 'Fan-In', status: 'blocked', event_time: '2025-09-03T14:22:00Z',
  from_bank: '002', from_bank_name: null, from_account: '0021****', from_entity_id: null, from_entity_name: null,
  to_bank: '008', to_bank_name: null, to_account: '0081****', to_entity_id: null, to_entity_name: null,
};

const expl: TransactionExplanation = {
  transaction_id: 7, source: 'llm', model: 'gemini-2.5-flash',
  pattern_matching: 'Pola A.', behavior_analysis: 'Perilaku B.', network_analysis: 'Jaringan C.',
  recommendation: 'Rekomendasi D.', risk_factors: [], evidence: {}, generated_at: '2025-09-03T14:30:00Z',
  reason_code: 'GA-FANIN', confidence: 'Tinggi', references: [], persisted: true, str_draft: null,
};

const notGenerated = () => new AxiosError('nf', '404', undefined, undefined, {
  status: 404, statusText: '', data: { detail: 'explanation_not_generated' }, headers: {},
  config: { headers: new AxiosHeaders() },
});

afterEach(() => vi.restoreAllMocks());

describe('TransactionDetailsModal generate flow', () => {
  it('not generated -> click -> generated -> LTKM draft', async () => {
    vi.spyOn(api, 'get').mockImplementation(async (url: string) => {
      if (url === '/transactions/7') return { data: txn };
      if (url === '/transactions/7/explanation') throw notGenerated();
      if (url === '/transactions/7/network') return { data: { transaction_id: 7, window_hours: 24, nodes: [], edges: [], truncated: false } };
      throw new Error(`unexpected ${url}`);
    });
    const post = vi.spyOn(api, 'post').mockImplementation(async (url: string) => {
      if (url === '/transactions/7/explanation') return { data: expl };
      if (url === '/transactions/7/str-draft') {
        return { data: {
          nomor_draf: 'LTKM-DRAFT-7', pihak: { pengirim: { nama: 'A', rekening: '0001', bank: 'Bank 1' }, penerima: { nama: null, rekening: '0002', bank: 'Bank 2' } }, kronologi: 'K.',
          indikator: ['Fan-in'], analisis: 'An.', rekomendasi: 'Rek.', catatan: 'DRAF — perlu verifikasi analis sebelum dilaporkan ke PPATK',
        } };
      }
      throw new Error(`unexpected ${url}`);
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <TransactionDetailsModal transactionId={7} isOpen onClose={() => {}} />
      </QueryClientProvider>,
    );

    const generateBtn = await screen.findByRole('button', { name: /Buat Penjelasan AI/ });
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(generateBtn);
    expect(await screen.findByText('Pola A.')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/transactions/7/explanation');

    fireEvent.click(screen.getByRole('button', { name: /Buat Draf LTKM/ }));
    const panel = screen.getByRole('region', { name: 'Draf LTKM' });
    await waitFor(() => expect(within(panel).getByText('LTKM-DRAFT-7')).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith('/transactions/7/str-draft');
  });
});
