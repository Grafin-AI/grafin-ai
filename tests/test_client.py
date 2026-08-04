import httpx
import pytest

from garda_ai_sim.client import IngestClient, IngestError, IngestSummary, IngestUnavailable


async def test_maps_response_and_sends_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["cid"] = request.headers.get("X-Correlation-ID")
        return httpx.Response(200, json={"results": [{"ingested": True}, {"ingested": False}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x/api/v1/ingest", "tok")
        summary = await client.send([{"transaction_id": 1}], correlation_id="cid-1")

    assert summary == IngestSummary(ingested=1, duplicate=1)
    assert seen["auth"] == "Bearer tok"
    assert seen["cid"] == "cid-1"


async def test_malformed_2xx_raises_ingest_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": "not-a-list"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x", "tok")
        with pytest.raises(IngestError):
            await client.send([], correlation_id="cid")


async def test_4xx_raises_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x", "tok", retries=3)
        with pytest.raises(IngestError):
            await client.send([], correlation_id="cid")
    assert calls == 1  # 4xx is not retried


async def test_5xx_retries_then_unavailable(monkeypatch):
    import garda_ai_sim.client as client_mod

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x", "tok", retries=2)
        with pytest.raises(IngestUnavailable):
            await client.send([], correlation_id="cid")
    assert calls == 3  # initial + 2 retries
