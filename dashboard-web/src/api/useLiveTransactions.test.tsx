import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from './client';
import { tokenStore } from './tokenStore';
import { useLiveTransactions } from './useLiveTransactions';

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { FakeWS.instances.push(this); }
  emit(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

beforeEach(() => {
  FakeWS.instances = [];
  (globalThis as any).WebSocket = FakeWS as any;
  tokenStore.set({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' });
});
afterEach(() => vi.restoreAllMocks());

describe('useLiveTransactions', () => {
  it('seeds from REST then prepends newer WS events', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { items: [{ seq: 5, transaction_id: 5, bank: 'BRI', type: 'BI-FAST', amount: 1, fraud_score: 0.1, typology: null, status: 'approved', surfaced_at: 't', event_time: 't' }] },
    } as any);

    const { result } = renderHook(() => useLiveTransactions(10));
    await waitFor(() => expect(result.current.items.length).toBe(1));

    act(() => { FakeWS.instances[0].onopen?.(); });
    act(() => {
      FakeWS.instances[0].emit({ seq: 6, transaction_id: 6, bank: 'Mandiri', type: 'BI-FAST', amount: 2, fraud_score: 0.9, typology: 'Fan-Out', status: 'blocked', surfaced_at: 't', event_time: 't' });
    });
    await waitFor(() => expect(result.current.items[0].seq).toBe(6));
    // a stale seq (<= cursor) is ignored
    act(() => { FakeWS.instances[0].emit({ seq: 5, transaction_id: 5, bank: 'X', type: 'BI-FAST', amount: 1, fraud_score: 0, typology: null, status: 'approved', surfaced_at: 't', event_time: 't' }); });
    expect(result.current.items.filter((i) => i.seq === 5).length).toBe(1);
  });
});
