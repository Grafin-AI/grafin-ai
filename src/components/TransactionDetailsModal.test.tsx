import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StrDraft, TransactionDetail, TransactionExplanation } from '../api/types';

const state = vi.hoisted(() => ({
  detail: null as unknown,
  explanation: { data: undefined, isLoading: false, isError: false } as Record<string, unknown>,
  explanationArgs: [] as unknown[][],
  generate: { isPending: false, isError: false, error: null } as Record<string, unknown>,
  draft: { isPending: false, isError: false, error: null } as Record<string, unknown>,
  generateMutate: (() => {}) as () => void,
  draftMutate: (() => {}) as () => void,
}));

vi.mock('../api/queries', () => ({
  apiErrorMessage: () => 'Gagal menyusun draf LTKM. Layanan AI sedang tidak tersedia, coba lagi.',
  useTransactionDetail: () => ({ data: state.detail, isLoading: false, isError: false }),
  useTransactionExplanation: (...args: unknown[]) => {
    state.explanationArgs.push(args);
    return state.explanation;
  },
  useGenerateExplanation: () => ({ ...state.generate, mutate: state.generateMutate, reset: noop }),
  useGenerateStrDraft: () => ({ ...state.draft, mutate: state.draftMutate, reset: noop }),
  useTransactionNetwork: () => ({ data: undefined, isLoading: false, isError: true }),
}));

function noop() {}

import { TransactionDetailsModal } from './TransactionDetailsModal';

const txn: TransactionDetail = {
  id: 42, bank: 'BRI', amount: 15_000_000, currency: 'IDR', type: 'BI-FAST',
  fraud_score: 0.82, typology: 'Fan-In', status: 'blocked', event_time: '2025-09-03T14:22:00Z',
  from_bank: '002', from_bank_name: 'Bank Rakyat Indonesia', from_account: '0021****881',
  from_entity_id: 'ENT-100', from_entity_name: 'B*** S******',
  to_bank: '008', to_bank_name: null, to_account: '0081****112',
  to_entity_id: null, to_entity_name: null,
};

const draftDoc: StrDraft = {
  nomor_draf: 'LTKM-DRAFT-42',
  pihak: { pengirim: { nama: 'A**** S****', rekening: '0021****881', bank: 'Bank Rakyat Indonesia' }, penerima: { nama: null, rekening: '0081****112', bank: '008' } },
  kronologi: 'Transfer BI-FAST Rp 15.000.000.',
  indikator: ['Fan-in tinggi', 'Nominal tidak biasa'],
  analisis: 'Pola rekening penampung.',
  rekomendasi: 'Tahan transaksi dan lakukan EDD.',
  catatan: 'DRAF — perlu verifikasi analis sebelum dilaporkan ke PPATK',
};

const llm: TransactionExplanation = {
  transaction_id: 42, source: 'llm', model: 'gemini-2.5-flash',
  pattern_matching: 'Pola fan-in terdeteksi.',
  behavior_analysis: 'Frekuensi meningkat tajam.',
  network_analysis: 'Terhubung ke klaster berisiko.',
  recommendation: 'BLOKIR dan laporkan ke PPATK.',
  risk_factors: [{ code: 'high_fan_in', label: 'Fan-in Tinggi', detail: '9 pengirim berbeda dalam 24 jam' }],
  evidence: { fan_in_24h: 9 },
  generated_at: '2025-09-03T14:30:00Z',
  reason_code: 'GA-FANIN',
  confidence: 'Tinggi',
  references: [{ id: 'uu-8-2010', title: 'UU 8/2010 — Kewajiban pelaporan' }],
  persisted: true,
  str_draft: null,
};

const rules: TransactionExplanation = { ...llm, source: 'rules', model: null, persisted: false, references: [] };

function renderModal(onOpenUserProfile = vi.fn()) {
  render(<TransactionDetailsModal transactionId={42} isOpen onClose={() => {}} onOpenUserProfile={onOpenUserProfile} />);
  return onOpenUserProfile;
}

const narrator = () => screen.getByRole('region', { name: 'Insight Narrator' });
const draftPanel = () => screen.getByRole('region', { name: 'Draf LTKM' });

describe('TransactionDetailsModal', () => {
  beforeEach(() => {
    state.detail = txn;
    state.explanation = { data: llm, isLoading: false, isError: false };
    state.explanationArgs = [];
    state.generate = { isPending: false, isError: false, error: null };
    state.draft = { isPending: false, isError: false, error: null };
    state.generateMutate = vi.fn();
    state.draftMutate = vi.fn();
  });

  it('renders header: id, status pill, typology chip and score', () => {
    renderModal();
    expect(screen.getByRole('heading', { name: /Transaksi #42/ })).toBeInTheDocument();
    expect(screen.getByText('DIBLOKIR')).toBeInTheDocument();
    expect(screen.getByText('Fan-In')).toBeInTheDocument();
    expect(screen.getByText('0,82')).toBeInTheDocument();
    expect(state.explanationArgs[0]).toEqual([42, true]);
  });

  it('shows "Buat Penjelasan AI" when not generated and does not call the LLM on open', () => {
    state.explanation = { data: null, isLoading: false, isError: false };
    renderModal();
    expect(screen.getByText(/belum dibuat untuk transaksi ini/)).toBeInTheDocument();
    expect(state.generateMutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Buat Penjelasan AI/ }));
    expect(state.generateMutate).toHaveBeenCalledTimes(1);
  });

  it('shows a spinner while generating', () => {
    state.explanation = { data: null, isLoading: false, isError: false };
    state.generate = { isPending: true, isError: false, error: null };
    renderModal();
    expect(within(narrator()).getByText('Menyusun penjelasan…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Buat Penjelasan AI/ })).not.toBeInTheDocument();
  });

  it('shows a loading skeleton while the stored explanation is fetched', () => {
    state.explanation = { data: undefined, isLoading: true, isError: false };
    renderModal();
    expect(within(narrator()).getByLabelText('Memuat penjelasan')).toBeInTheDocument();
  });

  it('renders the generated explanation: chips, four sections, factors, references, footer', () => {
    renderModal();
    const n = within(narrator());
    expect(n.getByText('GA-FANIN')).toBeInTheDocument();
    expect(n.getByText('Keyakinan: Tinggi')).toBeInTheDocument();
    expect(n.getByText('BLOKIR')).toBeInTheDocument();
    for (const h of ['Pencocokan Pola', 'Analisis Perilaku', 'Analisis Jaringan', 'Rekomendasi']) {
      expect(n.getByRole('heading', { name: h })).toBeInTheDocument();
    }
    expect(n.getByText('Pola fan-in terdeteksi.')).toBeInTheDocument();
    expect(n.getByText('BLOKIR dan laporkan ke PPATK.')).toBeInTheDocument();
    expect(n.getByText('Fan-in Tinggi')).toHaveAttribute('title', '9 pengirim berbeda dalam 24 jam');
    expect(n.getByText('Rujukan kebijakan')).toBeInTheDocument();
    expect(n.getByText('UU 8/2010 — Kewajiban pelaporan')).toBeInTheDocument();
    expect(n.getByText(/gemini-2\.5-flash · tersimpan/)).toBeInTheDocument();
    expect(n.queryByText(/Mode cadangan/)).not.toBeInTheDocument();
  });

  it('shows the fallback badge with retry when the explanation is not persisted', () => {
    state.explanation = { data: rules, isLoading: false, isError: false };
    renderModal();
    expect(within(narrator()).getByText(/Mode cadangan \(aturan\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Coba lagi/ }));
    expect(state.generateMutate).toHaveBeenCalledTimes(1);
  });

  it('keeps "Buat Draf LTKM" disabled until the explanation is persisted', () => {
    state.explanation = { data: rules, isLoading: false, isError: false };
    renderModal();
    expect(screen.getByRole('button', { name: /Buat Draf LTKM/ })).toBeDisabled();
    expect(within(draftPanel()).getByText(/tersedia setelah penjelasan AI tersimpan/)).toBeInTheDocument();
  });

  it('generates the LTKM draft when persisted', () => {
    renderModal();
    const btn = screen.getByRole('button', { name: /Buat Draf LTKM/ });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(state.draftMutate).toHaveBeenCalledTimes(1);
  });

  it('renders the stored draft with DRAF warning, fields, copy and print', async () => {
    state.explanation = { data: { ...llm, str_draft: draftDoc }, isLoading: false, isError: false };
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderModal();
    const d = within(draftPanel());
    expect(d.getByText('LTKM-DRAFT-42')).toBeInTheDocument();
    expect(d.getByRole('note')).toHaveTextContent('DRAF — perlu verifikasi analis');
    expect(d.getByText('Tahan transaksi dan lakukan EDD.')).toBeInTheDocument();
    expect(d.getByText('Nominal tidak biasa')).toBeInTheDocument();
    fireEvent.click(d.getByRole('button', { name: 'Salin' }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('LTKM-DRAFT-42'));
    expect(await d.findByText('Tersalin')).toBeInTheDocument();
    fireEvent.click(d.getByRole('button', { name: /Cetak/ }));
    expect(print).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Draf LTKM tersedia/ })).toBeDisabled();
  });

  it('surfaces draft generation errors', () => {
    state.draft = { isPending: false, isError: true, error: new Error('502') };
    renderModal();
    expect(within(draftPanel()).getByRole('alert')).toHaveTextContent(/Gagal menyusun draf LTKM/);
  });

  it('never renders ground-truth laundering labels', () => {
    renderModal();
    expect(screen.queryByText(/is_laundering/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Indikasi Pencucian/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ya \(Terdeteksi\)/)).not.toBeInTheDocument();
  });

  it('shows sender and receiver cards and opens the sender entity profile', () => {
    const onOpen = renderModal();
    expect(screen.getByText('Bank Rakyat Indonesia')).toBeInTheDocument();
    expect(screen.getByText('008')).toBeInTheDocument(); // receiver bank code fallback
    expect(screen.getByText('B*** S******')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /profil pengirim/i }));
    expect(onOpen).toHaveBeenCalledWith('ENT-100');
    expect(screen.getByRole('button', { name: /profil penerima/i })).toBeDisabled();
  });

  it('renders the network panel', () => {
    renderModal();
    expect(screen.getByRole('region', { name: 'Analisis Jaringan' })).toBeInTheDocument();
  });
});
