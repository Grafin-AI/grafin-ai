from grafin_ai_backend.observability import REGISTRY, REQUEST_COUNT, configure_logging


def test_logging_and_metrics_configured():
    configure_logging("INFO")
    REQUEST_COUNT.labels(method="GET", path="/healthz", status="200").inc()
    value = REGISTRY.get_sample_value(
        "grafin_http_requests_total",
        {"method": "GET", "path": "/healthz", "status": "200"},
    )
    assert value == 1.0
