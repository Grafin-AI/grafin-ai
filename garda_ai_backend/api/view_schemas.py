from datetime import datetime

from pydantic import BaseModel


class SimStateResponse(BaseModel):
    sim_now: datetime
    speed: float
    running: bool


class SimControlRequest(BaseModel):
    running: bool | None = None
    speed: float | None = None
    sim_now: datetime | None = None


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
    is_laundering: bool
    event_time: str


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
    created_at: str
    acknowledged: bool


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
