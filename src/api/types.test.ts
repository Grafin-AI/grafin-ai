import { describe, expect, it } from 'vitest';
import type { LiveItem, MetricsOverview, TokenResponse } from './types';

describe('api types', () => {
  it('compile-time shapes are usable at runtime', () => {
    const tok: TokenResponse = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' };
    const m: MetricsOverview = {
      total_transactions: 1, flagged: 0, blocked: 0, total_amount: 0, fraud_rate: 0,
    };
    const li: LiveItem = {
      seq: 1, transaction_id: 1, bank: 'BRI', type: 'BI-FAST', amount: 1, fraud_score: 0.1,
      typology: null, status: 'approved', surfaced_at: '2025-09-01T00:00:00Z',
      event_time: '2025-09-01T00:00:00Z',
    };
    expect(tok.token_type).toBe('bearer');
    expect(m.total_transactions).toBe(1);
    expect(li.status).toBe('approved');
  });
});

import type { InstitutionsResponse, StrDraft, TransactionExplanation, TransactionNetwork } from './types';

describe('demo-final api types', () => {
  it('explanation carries reason code, confidence, references and draft', () => {
    const draft: StrDraft = {
      nomor_draf: 'LTKM-DRAFT-1', pihak: { pengirim: 'A', penerima: 'B' }, kronologi: 'k',
      indikator: ['i'], analisis: 'a', rekomendasi: 'r', catatan: 'DRAF',
    };
    const e: TransactionExplanation = {
      transaction_id: 1, source: 'llm', model: 'm', pattern_matching: '', behavior_analysis: '',
      network_analysis: '', recommendation: '', risk_factors: [], evidence: {},
      generated_at: '2025-09-01T00:00:00Z', reason_code: 'GA-FANIN', confidence: 'Tinggi',
      references: [{ id: 'uu-8-2010', title: 'UU 8/2010' }], persisted: true, str_draft: draft,
    };
    const n: TransactionNetwork = {
      transaction_id: 1, window_hours: 24, truncated: false,
      nodes: [{ id: 'a', label: 'a', bank: 'b', role: 'sender', flagged_count: 0 }],
      edges: [],
    };
    const i: InstitutionsResponse = { institutions: [], flows: [] };
    expect(e.str_draft?.nomor_draf).toBe('LTKM-DRAFT-1');
    expect(n.nodes[0].role).toBe('sender');
    expect(i.flows).toEqual([]);
  });
});
