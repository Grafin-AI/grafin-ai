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
