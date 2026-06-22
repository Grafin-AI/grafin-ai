import pytest
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_metrics_exposed(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "garda_http_requests_total" in r.text
