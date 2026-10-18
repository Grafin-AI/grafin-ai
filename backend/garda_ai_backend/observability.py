import logging

import structlog
from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()
REQUEST_COUNT = Counter(
    "garda_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)
INGEST_TRANSACTIONS = Counter(
    "garda_ingest_transactions_total",
    "Transactions received by /ingest, by result",
    ["result"],  # bounded: inserted | duplicate
    registry=REGISTRY,
)
INGEST_SCORING_LATENCY = Histogram(
    "garda_ingest_scoring_latency_seconds",
    "Latency of the scoring-service call from /ingest",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY,
)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
    )
