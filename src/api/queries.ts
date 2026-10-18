import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { api } from './client';
import type {
  AlertsResponse, FraudAnalytics, GeoResponse, HeatmapResponse, InstitutionsResponse, LiveResponse,
  MetricsOverview, RiskProfile, StrDraft, SystemHealth, TransactionDetail, TransactionExplanation,
  TransactionNetwork, UserRiskResponse, VolumeResponse,
} from './types';

const get = async <T,>(url: string, params?: Record<string, unknown>): Promise<T> =>
  (await api.get<T>(url, params ? { params } : undefined)).data;

// The simulation clock advances continuously, so the dashboard aggregates must
// poll to stay live (the backend caches them ~5s, so this is cheap).
const LIVE = { refetchInterval: 4000 } as const;

export const useMetricsOverview = () =>
  useQuery({ queryKey: ['metrics', 'overview'], queryFn: () => get<MetricsOverview>('/metrics/overview'), ...LIVE });

export const useVolume = (range: string) =>
  useQuery({ queryKey: ['metrics', 'volume', range], queryFn: () => get<VolumeResponse>('/metrics/volume', { range }), ...LIVE });

export const useHeatmap = () =>
  useQuery({ queryKey: ['metrics', 'heatmap'], queryFn: () => get<HeatmapResponse>('/metrics/heatmap'), ...LIVE });

export const useFraudAnalytics = () =>
  useQuery({ queryKey: ['analytics', 'fraud'], queryFn: () => get<FraudAnalytics>('/analytics/fraud'), ...LIVE });

export const useProvinces = () =>
  useQuery({ queryKey: ['geo', 'provinces'], queryFn: () => get<GeoResponse>('/geo/provinces'), ...LIVE });

export const useUserRisk = (risk?: string) =>
  useQuery({ queryKey: ['users', 'risk', risk ?? 'all'], queryFn: () => get<UserRiskResponse>('/users/risk', risk ? { risk } : undefined), ...LIVE });

export const useUserProfile = (entityId: string | null) =>
  useQuery({
    queryKey: ['users', 'profile', entityId],
    queryFn: () => get<RiskProfile>(`/users/${entityId}/profile`),
    enabled: !!entityId,
  });

export const useAlerts = (status: string = 'all') =>
  useQuery({ queryKey: ['alerts', status], queryFn: () => get<AlertsResponse>('/alerts', { status }), ...LIVE });

export const useAckAlert = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post(`/alerts/${id}/ack`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
};

export const useTransactionDetail = (id: number | null) =>
  useQuery({
    queryKey: ['transaction', id],
    queryFn: () => get<TransactionDetail>(`/transactions/${id}`),
    enabled: id != null,
  });

const httpStatus = (err: unknown): number | undefined =>
  isAxiosError(err) ? err.response?.status : undefined;

const httpDetail = (err: unknown): string | undefined => {
  if (!isAxiosError(err)) return undefined;
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : undefined;
};

/** Retry transient failures once, never 4xx (404/409 are answers, not glitches). */
const retryTransient = (failureCount: number, err: unknown) => {
  const status = httpStatus(err);
  if (status != null && status >= 400 && status < 500) return false;
  return failureCount < 1;
};

const ERROR_MESSAGES: Record<string, string> = {
  explanation_required: 'Buat penjelasan AI tersimpan terlebih dahulu sebelum menyusun draf LTKM.',
  str_generation_failed: 'Gagal menyusun draf LTKM. Layanan AI sedang tidak tersedia, coba lagi.',
  explanation_not_generated: 'Penjelasan AI belum dibuat untuk transaksi ini.',
  'transaction not found': 'Transaksi tidak ditemukan.',
};

/** Human-readable (Indonesian) message for an API error. */
export function apiErrorMessage(err: unknown): string {
  const detail = httpDetail(err);
  if (detail && ERROR_MESSAGES[detail]) return ERROR_MESSAGES[detail];
  const status = httpStatus(err);
  if (status === 409) return ERROR_MESSAGES.explanation_required;
  if (status === 502) return ERROR_MESSAGES.str_generation_failed;
  return 'Terjadi kesalahan. Silakan coba lagi.';
}

const explanationKey = (id: number | null) => ['transaction', id, 'explanation'] as const;

// Explanations are generated on demand (POST) and persisted by the backend, so
// GET either returns the stored one or 404 `explanation_not_generated`, which
// we map to `null` ("not generated yet") rather than an error.
export const useTransactionExplanation = (id: number | null, enabled = true) =>
  useQuery<TransactionExplanation | null>({
    queryKey: explanationKey(id),
    queryFn: async () => {
      try {
        return await get<TransactionExplanation>(`/transactions/${id}/explanation`);
      } catch (err) {
        if (httpStatus(err) === 404 && httpDetail(err) === 'explanation_not_generated') return null;
        throw err;
      }
    },
    enabled: enabled && id != null,
    staleTime: 30 * 60 * 1000,
    retry: retryTransient,
  });

/** Generate (or fetch the already-stored) AI explanation. LLM may take 5-15 s. */
export const useGenerateExplanation = (id: number | null) => {
  const qc = useQueryClient();
  return useMutation<TransactionExplanation, unknown, void>({
    mutationFn: () => api.post<TransactionExplanation>(`/transactions/${id}/explanation`).then((r) => r.data),
    onSuccess: (data) => qc.setQueryData(explanationKey(id), data),
  });
};

/** Generate (or fetch the stored) LTKM draft. 409 = no persisted explanation, 502 = LLM failure. */
export const useGenerateStrDraft = (id: number | null) => {
  const qc = useQueryClient();
  return useMutation<StrDraft, unknown, void>({
    mutationFn: async () => {
      const data = (await api.post<StrDraft | { str_draft: StrDraft }>(`/transactions/${id}/str-draft`)).data;
      // Tolerate the backend returning either the bare draft or the explanation that wraps it.
      return data && typeof data === 'object' && 'str_draft' in data ? data.str_draft : (data as StrDraft);
    },
    onSuccess: (draft) =>
      qc.setQueryData<TransactionExplanation | null>(explanationKey(id), (prev) =>
        prev ? { ...prev, str_draft: draft } : prev),
  });
};

export const useTransactionNetwork = (id: number | null, enabled = true) =>
  useQuery({
    queryKey: ['transaction', id, 'network'],
    queryFn: () => get<TransactionNetwork>(`/transactions/${id}/network`),
    enabled: enabled && id != null,
    staleTime: 5 * 60 * 1000,
    retry: retryTransient,
  });

export const useInstitutions = () =>
  useQuery({
    queryKey: ['analytics', 'institutions'],
    queryFn: () => get<InstitutionsResponse>('/analytics/institutions'),
    // Stop polling once the endpoint errors (e.g. 404 while the backend stretch is absent).
    refetchInterval: (query) => (query.state.status === 'error' ? false : 15000),
    retry: retryTransient,
  });

export const useLiveRecent = (limit = 50) =>
  useQuery({ queryKey: ['transactions', 'live', limit], queryFn: () => get<LiveResponse>('/transactions/live', { limit }) });

export const useSystemHealth = () =>
  useQuery({ queryKey: ['system', 'health'], queryFn: () => get<SystemHealth>('/system/health'), ...LIVE });
