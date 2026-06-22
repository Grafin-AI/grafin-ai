import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { api } from './client';
import { useMetricsOverview, useAlerts } from './queries';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
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
});
