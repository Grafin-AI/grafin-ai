import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from garda_ai_backend.api import deps
from garda_ai_backend.config import get_settings
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.repositories.explanations import ExplanationsRepository
from garda_ai_backend.schema import (
    Account,
    Bank,
    Entity,
    StoredExplanation,
    Transaction,
    TransactionEvent,
    User,
)
from garda_ai_backend.security.tokens import create_access_token
from garda_ai_backend.services.explain.evidence import compute_evidence
from garda_ai_backend.services.explain import knowledge as kb
from garda_ai_backend.services.explain.llm import parse_narrative
from garda_ai_backend.services.explain.rules import NARRATIVE_FIELDS

T_TIME = datetime(2025, 9, 1, 3, 0, tzinfo=UTC)  # 03:00 -> night
TARGET = 100

LLM_NARRATIVE = {
    "pattern_matching": "Model GNN menilai pola fan-in. Skor tinggi.",
    "behavior_analysis": "Nominal jauh di atas median. Terjadi dini hari.",
    "network_analysis": "Penerima menerima dari banyak pengirim. Lintas bank.",
    "recommendation": "TUNDA transaksi. Lakukan EDD.",
    "reason_code": "ga-gather",
    "confidence": "sedang",
    "references": ["tipologi-fan-in", "bogus-id", "faktor-velositas"],
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

URL = f"/api/v1/transactions/{TARGET}/explanation"
FULL_KEYS = {
    "transaction_id", "source", "model", "pattern_matching", "behavior_analysis",
    "network_analysis", "recommendation", "reason_code", "confidence", "references",
    "risk_factors", "evidence", "generated_at", "persisted", "str_draft",
}


async def _stored(session, tid=TARGET):
    return await ExplanationsRepository(session).get(tid)


async def test_get_before_generation_is_not_generated(make_client):
    c = await make_client()
    r = await c.get(URL, headers=_auth())
    assert r.status_code == 404
    assert r.json() == {"detail": "explanation_not_generated"}


async def test_get_and_post_unknown_transaction(make_client):
    c = await make_client()
    for method in (c.get, c.post):
        r = await method("/api/v1/transactions/999/explanation", headers=_auth())
        assert r.status_code == 404
        assert r.json() == {"detail": "transaction not found"}


async def test_rules_when_provider_none_not_persisted(make_client, session):
    c = await make_client()
    r = await c.post(URL, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == FULL_KEYS
    assert body["transaction_id"] == TARGET
    assert body["source"] == "rules" and body["model"] is None
    assert body["persisted"] is False and body["str_draft"] is None
    assert body["reason_code"] == "GA-FANIN"  # typology Fan-In
    assert body["confidence"] == "Tinggi"  # score 0.92 >= 0.85
    ref_ids = [ref["id"] for ref in body["references"]]
    assert {"uu-tppu-umum", "ppatk-ltkm-indikator"} <= set(ref_ids)
    assert "tipologi-fan-in" in ref_ids
    assert all(ref["title"] for ref in body["references"])
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
    # Not stored: GET still says not generated, so a retry stays possible.
    assert await _stored(session) is None
    assert (await c.get(URL, headers=_auth())).json() == {"detail": "explanation_not_generated"}


async def test_llm_anthropic_valid_json_persisted(make_client, session):
    calls: list[httpx.Request] = []
    s = _settings(llm_provider="anthropic", llm_api_key="sk-test-key")
    c = await make_client(s, _anthropic_handler(calls, json.dumps(LLM_NARRATIVE)))
    r = await c.post(URL, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == FULL_KEYS
    assert body["source"] == "llm" and body["persisted"] is True
    assert body["model"] == "claude-sonnet-5-5"
    assert body["recommendation"] == LLM_NARRATIVE["recommendation"]
    assert body["reason_code"] == "GA-GATHER" and body["confidence"] == "Sedang"
    # bogus + not-provided ids dropped, titles filled server-side
    assert body["references"] == [
        {"id": "tipologi-fan-in", "title": kb.BY_ID["tipologi-fan-in"]["title"]},
    ]
    assert body["risk_factors"]  # rules-derived factors still attached
    req = calls[0]
    assert req.url == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-test-key"
    assert req.headers["anthropic-version"] == "2023-06-01"
    sent = json.loads(req.content)
    assert sent["model"] == "claude-sonnet-5-5"
    assert "PPATK" in sent["system"] and "HANYA" in sent["system"]
    user_prompt = sent["messages"][0]["content"]
    assert "receiver_distinct_senders_24h" in user_prompt
    assert "tipologi-fan-in" in user_prompt and "GA-FANIN" in user_prompt

    row = await _stored(session)
    assert row is not None and row.generated_by == "user-1" and row.str_draft is None
    got = await c.get(URL, headers=_auth())
    assert got.status_code == 200 and got.json() == body
    # Stored: a second POST returns the row without calling the provider.
    again = await c.post(URL, headers=_auth())
    assert again.json() == body and len(calls) == 1


async def test_generated_by_uses_user_email(make_client, session):
    session.add(User(
        id=1, email="analis@ojk.go.id", password_hash="x", role="analyst",
        created_at=datetime.now(UTC),
    ))
    await session.commit()
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler([], json.dumps(LLM_NARRATIVE)))
    assert (await c.post(URL, headers=_auth())).status_code == 200
    assert (await _stored(session)).generated_by == "analis@ojk.go.id"


async def test_llm_invalid_extra_fields_fall_back_deterministically(make_client):
    bad = {**LLM_NARRATIVE, "reason_code": "GA-BOGUS", "confidence": "very high"}
    bad.pop("references")
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler([], json.dumps(bad)))
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "llm" and body["persisted"] is True
    assert body["reason_code"] == "GA-FANIN" and body["confidence"] == "Tinggi"
    ids = [ref["id"] for ref in body["references"]]
    assert ids == [e["id"] for e in kb.retrieve(
        [f["code"] for f in body["risk_factors"]], "Fan-In"
    )]


async def test_llm_invalid_json_falls_back_to_rules(make_client, session):
    calls: list = []
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler(calls, "maaf, saya tidak bisa"))
    body = (await c.post(URL, headers=_auth())).json()
    assert calls and body["source"] == "rules" and body["model"] is None
    assert body["persisted"] is False
    assert body["recommendation"].startswith("TUNDA")
    assert await _stored(session) is None


async def test_llm_missing_field_falls_back(make_client):
    partial = {k: v for k, v in LLM_NARRATIVE.items() if k != "network_analysis"}
    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, _anthropic_handler([], json.dumps(partial)))
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "rules" and body["persisted"] is False


async def test_llm_timeout_falls_back_then_retry_persists(make_client, session):
    state = {"fail": True}

    def handler(request):
        if state["fail"]:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": json.dumps(LLM_NARRATIVE)}]}
        )

    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, handler)
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "rules" and body["persisted"] is False
    state["fail"] = False
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "llm" and body["persisted"] is True
    assert await _stored(session) is not None


async def test_concurrent_generate_returns_first_row(make_client, session, pg_url):
    """A competing request commits its row while our LLM call is in flight: our insert
    must not fail or overwrite, and we return the row that won."""
    other = create_async_engine(pg_url)

    async def handler(request: httpx.Request) -> httpx.Response:
        async with other.begin() as conn:
            await conn.execute(insert(StoredExplanation).values(
                transaction_id=TARGET, source="llm", model="first-model",
                pattern_matching="P", behavior_analysis="B", network_analysis="N",
                recommendation="TUNDA dulu.", reason_code="GA-FANIN", confidence="Tinggi",
                references=[], risk_factors=[], evidence={}, generated_by="other",
                generated_at=datetime(2026, 10, 18, tzinfo=UTC),
            ))
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": json.dumps(LLM_NARRATIVE)}]}
        )

    s = _settings(llm_provider="anthropic", llm_api_key="k")
    c = await make_client(s, handler)
    r = await c.post(URL, headers=_auth())
    await other.dispose()
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "first-model" and body["recommendation"] == "TUNDA dulu."
    assert body["persisted"] is True


async def test_gemini_and_ollama_request_shape(make_client, session):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        text = json.dumps(LLM_NARRATIVE)
        if "generateContent" in request.url.path:
            return httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}
            )
        return httpx.Response(200, json={"message": {"content": text}})

    c = await make_client(_settings(llm_provider="gemini", llm_api_key="g-key"), handler)
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "llm" and body["model"] == "gemini-2.5-flash"
    assert seen[0].url.path == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert seen[0].headers["x-goog-api-key"] == "g-key" and "key" not in seen[0].url.params
    sent = json.loads(seen[0].content)
    assert sent["systemInstruction"]["parts"][0]["text"].startswith("Anda adalah analis")
    assert sent["generationConfig"]["responseMimeType"] == "application/json"

    await session.execute(delete(StoredExplanation))
    await session.commit()
    c = await make_client(_settings(llm_provider="ollama"), handler)
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "llm" and body["model"] == "llama3.1:8b"
    assert str(seen[1].url) == "http://host.docker.internal:11434/api/chat"
    sent = json.loads(seen[1].content)
    assert sent["stream"] is False and sent["format"] == "json"


async def test_gemma_folds_system_prompt_and_skips_json_mode(make_client):
    """Gemma on the Gemini API rejects systemInstruction and JSON mode."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        text = "```json\n" + json.dumps(LLM_NARRATIVE) + "\n```"
        parts = [{"text": "thinking...", "thought": True}, {"text": text}]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]})

    s = _settings(llm_provider="gemini", llm_api_key="g", llm_model="gemma-3-27b-it")
    c = await make_client(s, handler)
    body = (await c.post(URL, headers=_auth())).json()
    assert body["source"] == "llm" and body["model"] == "gemma-3-27b-it"
    assert seen[0].url.path == "/v1beta/models/gemma-3-27b-it:generateContent"
    sent = json.loads(seen[0].content)
    assert "systemInstruction" not in sent
    assert "responseMimeType" not in sent["generationConfig"]
    prompt = sent["contents"][0]["parts"][0]["text"]
    assert prompt.startswith("Anda adalah analis") and "Data transaksi (JSON)" in prompt


async def test_explanation_requires_auth(make_client):
    c = await make_client()
    assert (await c.get(URL)).status_code in (401, 403)
    assert (await c.post(URL)).status_code in (401, 403)


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize("wrap", ["{}", "```json\n{}\n```", "Berikut hasilnya:\n{}\nSelesai."])
def test_parse_narrative_tolerates_wrapping(wrap):
    text = wrap.replace("{}", json.dumps(LLM_NARRATIVE))
    out = parse_narrative(text, "TUNDA")
    assert out == {**LLM_NARRATIVE, "reason_code": "GA-GATHER", "confidence": "Sedang"}


def test_parse_narrative_extra_fields_best_effort():
    base = {k: LLM_NARRATIVE[k] for k in NARRATIVE_FIELDS}
    out = parse_narrative(json.dumps(base), "TUNDA")
    assert out["reason_code"] is None and out["confidence"] is None
    assert out["references"] is None
    out = parse_narrative(json.dumps({**base, "references": "x", "confidence": 1}), "TUNDA")
    assert out["references"] is None and out["confidence"] is None


def test_parse_narrative_prefixes_missing_action_verb():
    out = parse_narrative(json.dumps({**LLM_NARRATIVE, "recommendation": "Tinjau ulang."}), "TINJAU")
    assert out["recommendation"] == "TINJAU: Tinjau ulang."
