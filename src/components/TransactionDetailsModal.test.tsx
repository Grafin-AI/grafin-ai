import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TransactionDetail, TransactionExplanation } from '../api/types';

const state = vi.hoisted(() => ({
  detail: null as unknown,
  explanation: { data: undefined, isLoading: false, isError: false } as Record<string, unknown>,
  explanationArgs: [] as unknown[][],
}));

vi.mock('../api/queries', () => ({
  useTransactionDetail: () => ({ data: state.detail, isLoading: false, isError: false }),
  useTransactionExplanation: (...args: unknown[]) => {
    state.explanationArgs.push(args);
    return state.explanation;
  },
}));

import { TransactionDetailsModal } from './TransactionDetailsModal';

const txn: TransactionDetail = {
  id: 42, bank: 'BRI', amount: 15_000_000, currency: 'IDR', type: 'BI-FAST',
  fraud_score: 0.82, typology: 'Fan-In', status: 'blocked', event_time: '2025-09-03T14:22:00Z',
  from_bank: '002', from_bank_name: 'Bank Rakyat Indonesia', from_account: '0021****881',
  from_entity_id: 'ENT-100', from_entity_name: 'B*** S******',
  to_bank: '008', to_bank_name: null, to_account: '0081****112',
  to_entity_id: null, to_entity_name: null,
};

const llm: TransactionExplanation = {
  transaction_id: 42, source: 'llm', model: 'claude-sonnet-5-5',
  pattern_matching: 'Pola fan-in terdeteksi.',
  behavior_analysis: 'Frekuensi meningkat tajam.',
  network_analysis: 'Terhubung ke klaster berisiko.',
  recommendation: 'BLOKIR dan laporkan ke PPATK.',
  risk_factors: [{ code: 'high_fan_in', label: 'Fan-in Tinggi', detail: '9 pengirim berbeda dalam 24 jam' }],
  evidence: { fan_in_24h: 9 },
  generated_at: '2025-09-03T14:30:00Z',
};

function renderModal(onOpenUserProfile = vi.fn()) {
  render(<TransactionDetailsModal transactionId={42} isOpen onClose={() => {}} onOpenUserProfile={onOpenUserProfile} />);
  return onOpenUserProfile;
}

describe('TransactionDetailsModal', () => {
  beforeEach(() => {
    state.detail = txn;
    state.explanation = { data: llm, isLoading: false, isError: false };
    state.explanationArgs = [];
  });

  it('renders the four analysis cards and LLM caption from the explanation API', () => {
    renderModal();
    expect(screen.getByText('Pola fan-in terdeteksi.')).toBeInTheDocument();
    expect(screen.getByText('Frekuensi meningkat tajam.')).toBeInTheDocument();
    expect(screen.getByText('Terhubung ke klaster berisiko.')).toBeInTheDocument();
    expect(screen.getByText('BLOKIR dan laporkan ke PPATK.')).toBeInTheDocument();
    expect(screen.getByText(/Dihasilkan oleh claude-sonnet-5-5/)).toBeInTheDocument();
    expect(state.explanationArgs[0]).toEqual([42, true]);
  });

  it('shows the rules caption when the explanation comes from rules', () => {
    state.explanation = { data: { ...llm, source: 'rules', model: null }, isLoading: false, isError: false };
    renderModal();
    expect(screen.getByText(/Ringkasan berbasis aturan/)).toBeInTheDocument();
    expect(screen.queryByText(/Dihasilkan oleh/)).not.toBeInTheDocument();
  });

  it('renders risk-factor chips from the API with detail as tooltip', () => {
    renderModal();
    const chip = screen.getByText('Fan-in Tinggi');
    expect(chip).toHaveAttribute('title', '9 pengirim berbeda dalam 24 jam');
    expect(screen.queryByText('Laundering Indicator')).not.toBeInTheDocument();
    expect(screen.queryByText('High Fraud Score')).not.toBeInTheDocument();
  });

  it('never renders ground-truth laundering labels', () => {
    renderModal();
    expect(screen.queryByText(/Indikasi Pencucian/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ya \(Terdeteksi\)/)).not.toBeInTheDocument();
  });

  it('shows a loading state while the explanation is generated', () => {
    state.explanation = { data: undefined, isLoading: true, isError: false };
    renderModal();
    expect(screen.getByText('Menganalisis transaksi…')).toBeInTheDocument();
    expect(screen.getByText('TXN-42', { selector: 'p' })).toBeInTheDocument();
  });

  it('stays usable when the explanation fails', () => {
    state.explanation = { data: undefined, isLoading: false, isError: true };
    renderModal();
    expect(screen.getByText(/Analisis belum tersedia/)).toBeInTheDocument();
    expect(screen.getByText('Bank Rakyat Indonesia')).toBeInTheDocument();
  });

  it('shows sender and receiver blocks and opens the sender entity profile', () => {
    const onOpen = renderModal();
    expect(screen.getByText('Bank Rakyat Indonesia')).toBeInTheDocument();
    expect(screen.getByText('008')).toBeInTheDocument(); // receiver bank code fallback
    expect(screen.getByText('B*** S******')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /profil pengirim/i }));
    expect(onOpen).toHaveBeenCalledWith('ENT-100');
    expect(screen.getByRole('button', { name: /profil penerima/i })).toBeDisabled();
  });
});
