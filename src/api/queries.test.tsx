import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { api } from './client';
import {
  apiErrorMessage, useAlerts, useGenerateExplanation, useGenerateStrDraft, useInstitutions,
  useMetricsOverview, useTransactionExplanation, useTransactionNetwork,
} from './queries';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function makeWrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function httpError(status: number, detail: string): AxiosError {
  return new AxiosError('fail', String(status), undefined, undefined, {
    status, statusText: '', data: { detail }, headers: {}, config: { headers: new AxiosHeaders() },
  });
}

describe('view query hooks', () => {
  it('useMetricsOverview fetches /metrics/overview', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { total_transactions: 4, flagged: 1, blocked: 1, total_amount: 100, fraud_rate: 0.5 },
    } as any);
    const { result } = renderHook(() => useMetricsOverview(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_transactions).toBe(4);
  });

  it('useAlerts fetches /alerts with status param', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { alerts: [] } } as any);
    const { result } = renderHook(() => useAlerts('active'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/alerts', { params: { status: 'active' } });
  });

  it('useTransactionExplanation fetches /transactions/:id/explanation', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { transaction_id: 7, source: 'rules' } } as any);
    const { result } = renderHook(() => useTransactionExplanation(7), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/transactions/7/explanation', undefined);
  });

  it('useTransactionExplanation stays idle without an id or when disabled', () => {
    const spy = vi.spyOn(api, 'get').mockClear();
    renderHook(() => useTransactionExplanation(null), { wrapper });
    renderHook(() => useTransactionExplanation(7, false), { wrapper });
    expect(spy).not.toHaveBeenCalled();
  });

  it('useTransactionExplanation maps 404 explanation_not_generated to null without retrying', async () => {
    const spy = vi.spyOn(api, 'get').mockRejectedValue(httpError(404, 'explanation_not_generated'));
    spy.mockClear();
    // retry enabled at the client level: the hook must still not retry this 404
    const qc = new QueryClient({ defaultOptions: { queries: { retry: 3, retryDelay: 1 } } });
    const { result } = renderHook(() => useTransactionExplanation(9), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('useTransactionExplanation surfaces other 404s as errors without retrying', async () => {
    const spy = vi.spyOn(api, 'get').mockRejectedValue(httpError(404, 'transaction not found'));
    spy.mockClear();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: 3, retryDelay: 1 } } });
    const { result } = renderHook(() => useTransactionExplanation(9), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('useGenerateExplanation POSTs and stores the result in the explanation cache', async () => {
    const body = { transaction_id: 5, source: 'llm', persisted: true, str_draft: null };
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: body } as any);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useGenerateExplanation(5), { wrapper: makeWrapper(qc) });
    await act(async () => { await result.current.mutateAsync(); });
    expect(spy).toHaveBeenCalledWith('/transactions/5/explanation');
    expect(qc.getQueryData(['transaction', 5, 'explanation'])).toEqual(body);
  });

  it('useGenerateStrDraft POSTs and merges the draft into the cached explanation', async () => {
    const draft = { nomor_draf: 'LTKM-DRAFT-5' };
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: draft } as any);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(['transaction', 5, 'explanation'], { transaction_id: 5, persisted: true, str_draft: null });
    const { result } = renderHook(() => useGenerateStrDraft(5), { wrapper: makeWrapper(qc) });
    await act(async () => { await result.current.mutateAsync(); });
    expect(spy).toHaveBeenCalledWith('/transactions/5/str-draft');
    expect(qc.getQueryData<any>(['transaction', 5, 'explanation']).str_draft).toEqual(draft);
  });

  it('apiErrorMessage maps backend detail codes to Indonesian messages', () => {
    expect(apiErrorMessage(httpError(409, 'explanation_required'))).toMatch(/penjelasan AI tersimpan/i);
    expect(apiErrorMessage(httpError(502, 'str_generation_failed'))).toMatch(/gagal menyusun draf/i);
    expect(apiErrorMessage(new Error('x'))).toMatch(/terjadi kesalahan/i);
  });

  it('useTransactionNetwork fetches only when enabled', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { nodes: [], edges: [] } } as any);
    spy.mockClear();
    renderHook(() => useTransactionNetwork(3, false), { wrapper });
    expect(spy).not.toHaveBeenCalled();
    const { result } = renderHook(() => useTransactionNetwork(3, true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/transactions/3/network', undefined);
  });

  it('useInstitutions fetches /analytics/institutions', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { institutions: [], flows: [] } } as any);
    const { result } = renderHook(() => useInstitutions(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/analytics/institutions', undefined);
  });
});
