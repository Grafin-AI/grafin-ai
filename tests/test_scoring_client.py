import httpx
import pytest

from garda_ai_backend.services.scoring_client import ScoringClient, ScoringUnavailable

_TXN = {"transaction_id": 1, "from_account": "a", "to_account": "b", "amount": "1.00",
        "payment_format": "ACH", "is_laundering": False, "event_time": "2026-06-25T09:00:00Z"}


def _client(handler) -> ScoringClient:
    transport = httpx.MockTransport(handler)
    return ScoringClient(httpx.AsyncClient(transport=transport), "http://scoring:8000", "tok",
                         retries=2, timeout_s=1.0)


async def test_score_success_and_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["cid"] = request.headers.get("x-correlation-id")
        return httpx.Response(200, json={"results": [{"transaction_id": 1, "fraud_score": 0.9,
                                                      "typology": "Smurfing", "status": "blocked"}]})

    out = await _client(handler).score([_TXN], correlation_id="cid-1")
    assert out[0]["status"] == "blocked"
    assert seen["auth"] == "Bearer tok"
    assert seen["cid"] == "cid-1"


async def test_score_retries_5xx_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ScoringUnavailable):
        await _client(handler).score([_TXN])
    assert calls["n"] == 3  # 1 + 2 retries


async def test_score_4xx_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    with pytest.raises(ScoringUnavailable):
        await _client(handler).score([_TXN])
    assert calls["n"] == 1  # no retry on 4xx
