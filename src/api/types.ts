// Hand-written mirror of the backend Pydantic response models.
// Regenerate from the live backend with `npm run gen:api` (OpenAPI) when convenient.

export type Status = 'approved' | 'flagged' | 'blocked';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Me {
  id: number;
  email: string;
  role: string;
}

export interface MetricsOverview {
  total_transactions: number;
  flagged: number;
  blocked: number;
  total_amount: number;
  fraud_rate: number;
}

export interface VolumePoint { bucket: string; count: number; flagged: number; }
export interface VolumeResponse { series: VolumePoint[]; }
export interface HeatmapResponse { cells: number[][]; }

export interface TypologyCount { typology: string; count: number; total_amount: number; }
export interface DetectionMetrics { precision: number; recall: number; f1: number; }
export interface FraudAnalytics { distribution: TypologyCount[]; detection: DetectionMetrics; }

export interface ProvinceFraud { name: string; fraud_count: number; change_pct: number; risk_level: string; }
export interface GeoResponse { provinces: ProvinceFraud[]; }

export interface LiveItem {
  seq: number;
  transaction_id: number;
  bank: string;
  type: string;
  amount: number;
  fraud_score: number;
  typology: string | null;
  status: Status;
  surfaced_at: string;
}
export interface LiveResponse { items: LiveItem[]; }

export interface TransactionDetail {
  id: number;
  bank: string;
  amount: number;
  currency: string;
  type: string;
  fraud_score: number;
  typology: string | null;
  status: Status;
  is_laundering: boolean;
  event_time: string;
}

export interface RiskProfile {
  entity_id: string;
  name: string;
  province: string | null;
  risk_level: string | null;
  risk_score: number;
  total_transactions: number;
  flagged_transactions: number;
  total_amount: number;
}
export interface UserRiskResponse { profiles: RiskProfile[]; }

export interface AlertItem {
  id: number;
  event_seq: number;
  severity: string;
  typology: string | null;
  created_at: string;
  acknowledged: boolean;
}
export interface AlertsResponse { alerts: AlertItem[]; }

export interface SystemHealth {
  db_ok: boolean;
  redis_ok: boolean;
  events_surfaced: number;
  model_accuracy_simulated: boolean;
}

export interface SimState { sim_now: string; speed: number; running: boolean; }

// WebSocket live event (worker → backend relay → client)
export interface LiveEvent {
  seq: number;
  transaction_id: number;
  bank: string | null;
  type: string | null;
  amount: number | null;
  fraud_score: number;
  typology: string | null;
  status: Status;
  surfaced_at: string;
  sim_now: string;
}
