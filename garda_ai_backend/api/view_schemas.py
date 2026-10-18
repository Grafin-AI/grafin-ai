from typing import Literal

from pydantic import BaseModel


class MetricsOverviewResponse(BaseModel):
    total_transactions: int
    flagged: int
    blocked: int
    total_amount: float
    fraud_rate: float


class VolumePoint(BaseModel):
    bucket: str
    count: int
    flagged: int


class VolumeResponse(BaseModel):
    series: list[VolumePoint]


class HeatmapResponse(BaseModel):
    cells: list[list[int]]


class TypologyCount(BaseModel):
    typology: str
    count: int
    total_amount: float


class DetectionMetrics(BaseModel):
    precision: float
    recall: float
    f1: float


class FraudAnalyticsResponse(BaseModel):
    distribution: list[TypologyCount]
    detection: DetectionMetrics


class ProvinceFraud(BaseModel):
    name: str
    fraud_count: int
    change_pct: float
    risk_level: str


class GeoResponse(BaseModel):
    provinces: list[ProvinceFraud]


class LiveItem(BaseModel):
    seq: int
    transaction_id: int
    bank: str
    type: str
    amount: float
    fraud_score: float
    typology: str | None
    status: str
    surfaced_at: str
    event_time: str


class LiveResponse(BaseModel):
    items: list[LiveItem]


class TransactionDetail(BaseModel):
    id: int
    bank: str
    amount: float
    currency: str
    type: str
    fraud_score: float
    typology: str | None
    status: str
    event_time: str
    from_bank: str
    from_bank_name: str | None
    from_account: str
    from_entity_id: str | None
    from_entity_name: str | None  # masked unless admin + ?unmasked=true
    to_bank: str
    to_bank_name: str | None
    to_account: str
    to_entity_id: str | None
    to_entity_name: str | None  # masked unless admin + ?unmasked=true


class RiskFactor(BaseModel):
    code: str
    label: str
    detail: str


class Reference(BaseModel):
    id: str
    title: str


class StrParty(BaseModel):
    nama: str | None  # masked unless admin + ?unmasked=true
    rekening: str
    bank: str | None


class StrParties(BaseModel):
    pengirim: StrParty
    penerima: StrParty


class StrDraft(BaseModel):
    nomor_draf: str
    pihak: StrParties
    kronologi: str
    indikator: list[str]
    analisis: str
    rekomendasi: str
    catatan: str


class TransactionExplanation(BaseModel):
    transaction_id: int
    source: Literal["llm", "rules"]
    model: str | None
    pattern_matching: str
    behavior_analysis: str
    network_analysis: str
    recommendation: str
    reason_code: str
    confidence: Literal["Tinggi", "Sedang", "Rendah"]
    references: list[Reference]
    risk_factors: list[RiskFactor]
    evidence: dict[str, bool | int | float | str | None]
    generated_at: str
    persisted: bool
    str_draft: StrDraft | None = None


class RiskProfile(BaseModel):
    entity_id: str
    name: str
    province: str | None
    risk_level: str | None
    risk_score: float
    total_transactions: int
    flagged_transactions: int
    total_amount: float


class UserRiskResponse(BaseModel):
    profiles: list[RiskProfile]


class AlertItem(BaseModel):
    id: int
    event_seq: int
    severity: str
    typology: str | None
    created_at: str  # real ingestion (wall-clock) time
    event_time: str  # dataset time of the underlying transaction
    acknowledged: bool


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]


class SystemHealthResponse(BaseModel):
    db_ok: bool
    redis_ok: bool
    events_surfaced: int
    model_accuracy_simulated: bool
    model_name: str | None = None
