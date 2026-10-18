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
  event_time: string;
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
  event_time: string;
  from_bank: string;
  from_bank_name: string | null;
  from_account: string;
  from_entity_id: string | null;
  from_entity_name: string | null;
  to_bank: string;
  to_bank_name: string | null;
  to_account: string;
  to_entity_id: string | null;
  to_entity_name: string | null;
}

export interface RiskFactor {
  code: string;
  label: string;
  detail: string;
}

export interface TransactionExplanation {
  transaction_id: number;
  source: 'llm' | 'rules';
  model: string | null;
  pattern_matching: string;
  behavior_analysis: string;
  network_analysis: string;
  recommendation: string;
  risk_factors: RiskFactor[];
  evidence: Record<string, number | string | boolean | null>;
  generated_at: string;
  /** Fixed code such as GA-FANIN, GA-FANOUT, GA-CYCLE, GA-GATHER, GA-VELOCITY, GA-AMOUNT, GA-NETWORK. */
  reason_code: string;
  /** 'Tinggi' | 'Sedang' | 'Rendah' */
  confidence: string;
  references: PolicyReference[];
  /** false = rules fallback, not stored (retry possible). */
  persisted: boolean;
  str_draft: StrDraft | null;
}

export interface PolicyReference {
  id: string;
  title: string;
}

export interface StrDraftParties {
  pengirim: string;
  penerima: string;
}

/** LTKM (Laporan Transaksi Keuangan Mencurigakan) draft. */
export interface StrDraft {
  nomor_draf: string;
  pihak: StrDraftParties;
  kronologi: string;
  indikator: string[];
  analisis: string;
  rekomendasi: string;
  catatan: string;
}

export type NetworkRole = 'sender' | 'receiver' | 'other';

export interface NetworkNode {
  id: string;
  label: string;
  bank: string;
  role: NetworkRole;
  flagged_count: number;
}

export interface NetworkEdge {
  id: number;
  source: string;
  target: string;
  amount: number;
  currency: string;
  event_time: string;
  status: string;
  fraud_score: number;
  focal: boolean;
}

export interface TransactionNetwork {
  transaction_id: number;
  window_hours: number;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  truncated: boolean;
}

export interface InstitutionStat {
  bank: string;
  transactions: number;
  flagged: number;
  blocked: number;
  flagged_rate: number;
}

export interface InstitutionFlow {
  from_bank: string;
  to_bank: string;
  flagged_count: number;
  amount: number;
}

export interface InstitutionsResponse {
  institutions: InstitutionStat[];
  flows: InstitutionFlow[];
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
  event_time: string;
  acknowledged: boolean;
}
export interface AlertsResponse { alerts: AlertItem[]; }

export interface SystemHealth {
  db_ok: boolean;
  redis_ok: boolean;
  events_surfaced: number;
  model_accuracy_simulated: boolean;
  model_name?: string | null;
}

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
  event_time: string;
}
