import logging

import structlog
from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "garda_scoring_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status_code"],
    registry=REGISTRY,
)
REQUEST_DURATION = Histogram(
    "garda_scoring_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint", "method"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    registry=REGISTRY,
)
TRANSACTIONS_SCORED = Counter(
    "garda_scoring_transactions_scored_total",
    "Transactions scored, by result status",
    ["status"],  # bounded: approved | flagged | blocked
    registry=REGISTRY,
)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )
