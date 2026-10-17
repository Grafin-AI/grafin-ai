import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from garda_ai_backend.api import deps
from garda_ai_backend.config import get_settings
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.schema import Account, Bank, Entity, Transaction, TransactionEvent
from garda_ai_backend.security.tokens import create_access_token
from garda_ai_backend.services.explain.evidence import compute_evidence
from garda_ai_backend.services.explain.llm import parse_narrative

T_TIME = datetime(2025, 9, 1, 3, 0, tzinfo=UTC)  # 03:00 -> night
TARGET = 100

LLM_NARRATIVE = {
    "pattern_matching": "Model GNN menilai pola fan-in. Skor tinggi.",
    "behavior_analysis": "Nominal jauh di atas median. Terjadi dini hari.",
    "network_analysis": "Penerima menerima dari banyak pengirim. Lintas bank.",
    "recommendation": "TUNDA transaksi. Lakukan EDD.",
}


def _auth(role: str = "analyst") -> dict:
    token = create_access_token(subject="1", role=role, secret="test-secret", ttl_min=15)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def explain_dataset(session):
    """Target tx 100: SA -> RH at 03:00, flagged 0.92.

    In-window (24h, inclusive): SA -> R1..R4 (1M each); S1..S5 -> RH (S5 exactly at the
    window start, S1 flagged). Excluded: S7 -> RH 25h before, S6 -> RH and SA -> R5 after.
    """
    session.add_all([Bank(id="10", name="Bank A"), Bank(id="20", name="Bank B")])
    accts = ["SA", "RH", "R1", "R2", "R3", "R4", "R5", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    session.add_all([
        Entity(id=f"E_{a}", name=f"Nama {a}", province="Jawa Timur" if a == "RH" else "Bali")
        for a in accts
    ])
    await session.flush()
    session.add_all([
        Account(
            id=a, bank_id="20" if a == "RH" else "10", entity_id=f"E_{a}",
            risk_score=Decimal("90" if a == "SA" else "10"),
            risk_category="High" if a == "SA" else "Low",
        )
        for a in accts
    ])
    await session.flush()

    rows = [  # id, from, to, amount, offset_hours, status, launder
        (TARGET, "SA", "RH", "10000000", 0, "flagged", False),
        (1, "SA", "R1", "1000000", -1, "approved", True),
        (2, "SA", "R2", "1000000", -2, "approved", True),
        (3, "SA", "R3", "1000000", -3, "approved", True),
        (4, "SA", "R4", "1000000", -4, "approved", True),
        (11, "S1", "RH", "500000", -5, "flagged", True),
        (12, "S2", "RH", "500000", -6, "approved", True),
        (13, "S3", "RH", "500000", -7, "approved", True),
        (14, "S4", "RH", "500000", -8, "approved", True),
        (15, "S5", "RH", "500000", -24, "approved", True),  # exactly at window start
        (16, "S7", "RH", "500000", -25, "blocked", True),  # before the window
        (17, "S6", "RH", "500000", 1, "blocked", True),  # future
        (18, "SA", "R5", "1000000", 2, "blocked", True),  # future
    ]
    for tid, frm, to, amt, off, _, launder in rows:
        session.add(Transaction(
            id=tid, event_time=T_TIME + timedelta(hours=off),
            from_bank_id="10", from_account=frm, to_bank_id="20" if to == "RH" else "10",
            to_account=to, amount_paid=Decimal(amt), payment_currency="IDR",
            amount_received=Decimal(amt), receiving_currency="IDR",
            payment_format="RTGS", is_laundering=launder,
        ))
    await session.flush()
    for tid, _, _, _, off, st, _ in rows:
        session.add(TransactionEvent(
            transaction_id=tid, surfaced_at=datetime(2026, 8, 1, tzinfo=UTC),
            event_time=T_TIME + timedelta(hours=off),
            fraud_score=Decimal("0.92" if tid == TARGET else "0.10"),
            typology="Fan-In" if tid == TARGET else None, status=st,
        ))
    await session.commit()


def _settings(**update):
    if "llm_api_key" in update:
        update["llm_api_key"] = SecretStr(update["llm_api_key"])
    return get_settings().model_copy(update=update)


@pytest_asyncio.fixture
async def make_client(session, redis_url, explain_dataset, monkeypatch):
    """Factory: make_client(settings, handler) -> AsyncClient against the app."""
    from garda_ai_backend.main import app

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    opened: list = []

    async def _override_session():
        yield session

    async def _make(settings=None, handler=None):
        settings = settings or _settings(llm_provider="none")
        app.dependency_overrides[deps.get_session] = _override_session
        app.dependency_overrides[deps.get_settings_dep] = lambda: settings
        if handler is not None:
            llm_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            opened.append(llm_http)
            app.dependency_overrides[deps.get_http_client] = lambda: llm_http
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(c)
        return c

    _make.redis = test_redis
    yield _make
    app.dependency_overrides.clear()
    for c in opened:
        await c.aclose()
    await test_redis.aclose()


def _anthropic_handler(calls: list, text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})
    return handler


# ---------------------------------------------------------------- evidence


async def test_evidence_counts_and_window(session, explain_dataset):
    ev = await compute_evidence(session, TARGET)
    assert ev is not None
    assert "is_laundering" not in ev
    # SA out in window: R1..R4 + the target itself; future SA -> R5 excluded.
    assert ev["sender_out_count_24h"] == 5
    assert ev["sender_distinct_receivers_24h"] == 5
    assert ev["sender_out_amount_24h"] == 14_000_000.0
    # RH in: S1..S5 (S5 at the inclusive start) + target; S7 (25h) and S6 (future) excluded.
    assert ev["receiver_in_count_24h"] == 6
    assert ev["receiver_distinct_senders_24h"] == 6
    assert ev["receiver_in_amount_24h"] == 12_500_000.0
    # Other flagged/blocked events: none for SA in window (R5 is future), S1 for RH.
    assert ev["sender_flagged_24h"] == 0
    assert ev["receiver_flagged_24h"] == 1
    # median(1M x4, 10M) = 1M -> 10x
    assert ev["amount_vs_sender_median"] == 10.0
    assert ev["hour_of_day"] == 3 and ev["is_night"] is True
    assert ev["cross_bank"] is True and ev["self_transfer"] is False
    assert ev["fraud_score"] == 0.92 and ev["status"] == "flagged"
    assert ev["typology"] == "Fan-In" and ev["channel"] == "RTGS"
    assert ev["sender_risk_category"] == "High" and ev["receiver_risk_category"] == "Low"
    assert ev["receiver_province"] == "Jawa Timur" and ev["sender_province"] == "Bali"


async def test_evidence_median_null_below_three(session, explain_dataset):
    ev = await compute_evidence(session, 11)  # S1 has a single outgoing tx
    assert ev["sender_out_count_24h"] == 1
    assert ev["amount_vs_sender_median"] is None


async def test_evidence_unknown_is_none(session, explain_dataset):
    assert await compute_evidence(session, 999) is None


# ---------------------------------------------------------------- endpoint


async def test_rules_when_provider_none(make_client):
    c = await make_client()
    r = await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "transaction_id", "source", "model", "pattern_matching", "behavior_analysis",
        "network_analysis", "recommendation", "risk_factors", "evidence", "generated_at",
    }
    assert body["transaction_id"] == TARGET
    assert body["source"] == "rules" and body["model"] is None
    assert body["recommendation"].startswith("TUNDA")  # flagged, score >= 0.85
    for k in ("pattern_matching", "behavior_analysis", "network_analysis"):
        assert body[k].strip()
    codes = {f["code"] for f in body["risk_factors"]}
    assert {
        "high_model_score", "high_fan_in", "high_fan_out",
        "unusual_amount", "cross_bank", "flagged_counterparty", "high_risk_profile",
    } <= codes
    assert "unusual_hour" not in codes  # flat hourly profile in IBM data: never a factor
    assert "high_velocity" not in codes  # 5 out / 6 in < 10
    assert body["evidence"]["receiver_distinct_senders_24h"] == 6
    assert body["generated_at"].endswith("Z")


async def test_llm_anthropic_valid_json(make_client):
    calls: list[httpx.Request] = []
    s = _settings(llm_provider="anthropic", llm_api_key="sk-test-key")
    c = await make_client(s, _anthropic_handler(calls, json.dumps(LLM_NARRATIVE)))
    r = await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())
    body = r.json()
    assert body["source"] == "llm"
    assert body["model"] == "claude-sonnet-5-5"
    assert body["recommendation"] == LLM_NARRATIVE["recommendation"]
    assert body["risk_factors"]  # rules-derived factors still attached
    req = calls[0]
    assert req.url == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-test-key"
    assert req.headers["anthropic-version"] == "2023-06-01"
    sent = json.loads(req.content)
    assert sent["model"] == "claude-sonnet-5-5"
    assert "PPATK" in sent["system"]
    assert "receiver_distinct_senders_24h" in sent["messages"][0]["content"]


async def test_llm_invalid_json_falls_back_to_rules(make_client):
    calls: list = []
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler(calls, "maaf, saya tidak bisa"))
    body = (await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())).json()
    assert calls and body["source"] == "rules" and body["model"] is None
    assert body["recommendation"].startswith("TUNDA")


async def test_llm_missing_field_falls_back(make_client):
    partial = {k: v for k, v in LLM_NARRATIVE.items() if k != "network_analysis"}
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler([], json.dumps(partial)))
    body = (await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())).json()
    assert body["source"] == "rules"


async def test_llm_timeout_falls_back(make_client):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, handler)
    body = (await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())).json()
    assert body["source"] == "rules"
    # Degraded answer is cached only briefly.
    assert 0 < await make_client.redis.ttl(f"expl:{TARGET}") <= 300


async def test_cache_hit_skips_provider(make_client):
    calls: list = []
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler(calls, json.dumps(LLM_NARRATIVE)))
    url = f"/api/v1/transactions/{TARGET}/explanation"
    first = (await c.get(url, headers=_auth())).json()
    second = (await c.get(url, headers=_auth())).json()
    assert len(calls) == 1
    assert first == second
    ttl = await make_client.redis.ttl(f"expl:{TARGET}")
    assert 23 * 3600 < ttl <= 24 * 3600


async def test_redis_down_still_computes(make_client, monkeypatch):
    c = await make_client()
    dead = build_redis("redis://127.0.0.1:1/0")
    monkeypatch.setattr(deps, "get_redis", lambda: dead)
    r = await c.get(f"/api/v1/transactions/{TARGET}/explanation", headers=_auth())
    assert r.status_code == 200 and r.json()["source"] == "rules"
    await dead.aclose()


async def test_gemini_and_ollama_request_shape(make_client):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        text = json.dumps(LLM_NARRATIVE)
        if "generateContent" in request.url.path:
            return httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}
            )
        return httpx.Response(200, json={"message": {"content": text}})

    url = f"/api/v1/transactions/{TARGET}/explanation"
    c = await make_client(_settings(llm_provider="gemini", llm_api_key="g-key"), handler)
    body = (await c.get(url, headers=_auth())).json()
    assert body["source"] == "llm" and body["model"] == "gemini-2.5-flash"
    assert seen[0].url.path == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert seen[0].url.params["key"] == "g-key"

    await make_client.redis.flushdb()
    c = await make_client(_settings(llm_provider="ollama"), handler)
    body = (await c.get(url, headers=_auth())).json()
    assert body["source"] == "llm" and body["model"] == "llama3.1:8b"
    assert str(seen[1].url) == "http://host.docker.internal:11434/api/chat"
    sent = json.loads(seen[1].content)
    assert sent["stream"] is False and sent["format"] == "json"


async def test_explanation_404(make_client):
    c = await make_client()
    r = await c.get("/api/v1/transactions/999/explanation", headers=_auth())
    assert r.status_code == 404


async def test_explanation_requires_auth(make_client):
    c = await make_client()
    r = await c.get(f"/api/v1/transactions/{TARGET}/explanation")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize("wrap", ["{}", "```json\n{}\n```", "Berikut hasilnya:\n{}\nSelesai."])
def test_parse_narrative_tolerates_wrapping(wrap):
    text = wrap.replace("{}", json.dumps(LLM_NARRATIVE))
    assert parse_narrative(text, "TUNDA") == LLM_NARRATIVE


def test_parse_narrative_prefixes_missing_action_verb():
    out = parse_narrative(json.dumps({**LLM_NARRATIVE, "recommendation": "Tinjau ulang."}), "TINJAU")
    assert out["recommendation"] == "TINJAU: Tinjau ulang."
