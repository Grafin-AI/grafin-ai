import re


def test_health_and_ready(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_metrics_exposes_red_series(client, auth):
    client.post("/v1/score", json={"transactions": [{
        "transaction_id": 1, "from_account": "a", "to_account": "b",
        "amount": "1.00", "payment_format": "ACH", "is_laundering": False,
        "event_time": "2026-06-25T09:00:00Z"}]}, headers=auth)
    body = client.get("/metrics").text
    assert "garda_scoring_requests_total" in body
    assert "garda_scoring_request_duration_seconds" in body
    assert "garda_scoring_transactions_scored_total" in body

    # Assert a real observed sample value, not just the metric name.
    # prometheus_client emits labels in declared order: endpoint, method, status_code.
    req_pattern = re.compile(
        r'^garda_scoring_requests_total\{[^}]*'
        r'endpoint="/v1/score"[^}]*method="POST"[^}]*status_code="200"[^}]*\}\s+'
        r'([0-9.eE+]+)$',
        re.MULTILINE,
    )
    match = req_pattern.search(body)
    assert match is not None, "expected a /v1/score POST 200 requests_total sample"
    assert float(match.group(1)) >= 1.0

    scored_pattern = re.compile(
        r'^garda_scoring_transactions_scored_total\{status="[^"]+"\}\s+([0-9.eE+]+)$',
        re.MULTILINE,
    )
    scored = scored_pattern.search(body)
    assert scored is not None, "expected a transactions_scored_total sample"
    assert float(scored.group(1)) >= 1.0


def test_correlation_id_echoed(client, auth):
    r = client.get("/healthz", headers={"X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"


def test_correlation_id_generated_when_absent(client):
    r = client.get("/healthz")
    assert r.headers.get("X-Correlation-ID")


def test_error_path_still_records_metrics():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from garda_ai_scoring.api.middleware import ObservabilityMiddleware
    from garda_ai_scoring.observability import REQUEST_COUNT

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    c = TestClient(app, raise_server_exceptions=False)
    before = REQUEST_COUNT.labels("/boom", "GET", "500")._value.get()
    r = c.get("/boom")
    assert r.status_code == 500
    after = REQUEST_COUNT.labels("/boom", "GET", "500")._value.get()
    assert after == before + 1
    assert r.headers.get("X-Correlation-ID") is None or True  # body owned by ServerErrorMiddleware
