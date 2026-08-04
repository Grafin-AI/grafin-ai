import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  AlertsResponse, FraudAnalytics, GeoResponse, HeatmapResponse, LiveResponse,
  MetricsOverview, RiskProfile, SystemHealth, TransactionDetail,
  UserRiskResponse, VolumeResponse,
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

export const useLiveRecent = (limit = 50) =>
  useQuery({ queryKey: ['transactions', 'live', limit], queryFn: () => get<LiveResponse>('/transactions/live', { limit }) });

export const useSystemHealth = () =>
  useQuery({ queryKey: ['system', 'health'], queryFn: () => get<SystemHealth>('/system/health'), ...LIVE });
