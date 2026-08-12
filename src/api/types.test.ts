import { describe, expect, it } from 'vitest';
import type { LiveItem, MetricsOverview, TokenResponse } from './types';

describe('api types', () => {
  it('compile-time shapes are usable at runtime', () => {
    const tok: TokenResponse = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' };
    const m: MetricsOverview = {
      total_transactions: 1, flagged: 0, blocked: 0, total_amount: 0, fraud_rate: 0,
    };
    const li: LiveItem = {
      seq: 1, transaction_id: 1, bank: 'BRI', type: 'ACH', amount: 1, fraud_score: 0.1,
      typology: null, status: 'approved', surfaced_at: '2025-09-01T00:00:00Z',
      event_time: '2025-09-01T00:00:00Z',
    };
    expect(tok.token_type).toBe('bearer');
    expect(m.total_transactions).toBe(1);
    expect(li.status).toBe('approved');
  });
});
