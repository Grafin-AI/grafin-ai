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


def test_correlation_id_echoed(client, auth):
    r = client.get("/healthz", headers={"X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"
