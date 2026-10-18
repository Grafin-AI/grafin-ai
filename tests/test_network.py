from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from test_explanation import TARGET, _auth, explain_dataset, make_client  # noqa: F401

from garda_ai_backend.repositories import network as net
from garda_ai_backend.schema import Account, Bank, Entity, Transaction, TransactionEvent

NET_URL = f"/api/v1/transactions/{TARGET}/network"


async def test_network_two_hops_window_and_shape(make_client):
    c = await make_client()
    r = await c.get(NET_URL, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"transaction_id", "window_hours", "nodes", "edges", "truncated"}
    assert body["transaction_id"] == TARGET and body["window_hours"] == 24
    assert body["truncated"] is False
    nodes = {n["id"]: n for n in body["nodes"]}
    # SA -> R1..R4 and S1..S5 -> RH in window; R5/S6 (future) and S7 (25h before) out.
    assert set(nodes) == {"SA", "RH", "R1", "R2", "R3", "R4", "S1", "S2", "S3", "S4", "S5"}
    assert nodes["SA"]["role"] == "sender" and nodes["RH"]["role"] == "receiver"
    assert nodes["R1"]["role"] == "other"
    assert nodes["RH"]["bank"] == "Bank B" and nodes["SA"]["bank"] == "Bank A"
    # RH: target (flagged) + S1 (flagged) in window; S7 blocked is outside the window.
    assert nodes["RH"]["flagged_count"] == 2 and nodes["S1"]["flagged_count"] == 1
    assert nodes["R1"]["flagged_count"] == 0
    assert set(nodes["SA"]) == {"id", "label", "bank", "role", "flagged_count"}
    edges = body["edges"]
    assert len(edges) == 10
    assert edges[0]["id"] == TARGET and edges[0]["focal"] is True
    assert sum(e["focal"] for e in edges) == 1
    e = edges[0]
    assert e["source"] == "SA" and e["target"] == "RH" and e["amount"] == 10_000_000.0
    assert e["currency"] == "IDR" and e["status"] == "flagged" and e["fraud_score"] == 0.92
    assert e["event_time"].startswith("2025-09-01T03:00:00")


async def test_network_masking(make_client):
    c = await make_client()
    analyst = (await c.get(f"{NET_URL}?unmasked=true", headers=_auth())).json()
    labels = {n["id"]: n["label"] for n in analyst["nodes"]}
    assert labels["SA"] == "**" and labels["RH"] == "**"  # <=4 chars: fully masked
    admin = (await c.get(f"{NET_URL}?unmasked=true", headers=_auth("admin"))).json()
    assert {n["id"]: n["label"] for n in admin["nodes"]}["SA"] == "SA"
    masked_admin = (await c.get(NET_URL, headers=_auth("admin"))).json()
    assert {n["id"]: n["label"] for n in masked_admin["nodes"]}["SA"] == "**"


async def test_network_404_and_auth(make_client):
    c = await make_client()
    r = await c.get("/api/v1/transactions/999/network", headers=_auth())
    assert r.status_code == 404 and r.json() == {"detail": "transaction not found"}
    assert (await c.get(NET_URL)).status_code in (401, 403)


T0 = datetime(2025, 9, 2, 12, tzinfo=UTC)
HUB_ID = 5000


@pytest_asyncio.fixture
async def hub_dataset(session, explain_dataset):  # noqa: F811
    """Focal X -> Y (id 5000). 100 senders P000..P099 -> Y (scores rising with i),
    and each P_i receives from Q_i (hop 2)."""
    session.add(Bank(id="30", name="Bank C"))
    accts = ["ACCTX000", "ACCTY000"] + [f"ACCTP{i:03d}" for i in range(100)] + [
        f"ACCTQ{i:03d}" for i in range(100)
    ]
    session.add_all([Entity(id=f"E_{a}", name=f"Nama {a}") for a in accts])
    await session.flush()
    session.add_all([Account(id=a, bank_id="30", entity_id=f"E_{a}") for a in accts])
    await session.flush()
    rows = [(HUB_ID, "ACCTX000", "ACCTY000", "0.99", 0)]
    rows += [(6000 + i, f"ACCTP{i:03d}", "ACCTY000", f"{i / 200:.3f}", -1) for i in range(100)]
    rows += [(7000 + i, f"ACCTQ{i:03d}", f"ACCTP{i:03d}", "0.90", -2) for i in range(100)]
    for tid, frm, to, _, off in rows:
        session.add(Transaction(
            id=tid, event_time=T0 + timedelta(hours=off), from_bank_id="30",
            from_account=frm, to_bank_id="30", to_account=to, amount_paid=Decimal("100"),
            payment_currency="IDR", amount_received=Decimal("100"),
            receiving_currency="IDR", payment_format="ACH", is_laundering=False,
        ))
    await session.flush()
    for tid, _, _, score, off in rows:
        session.add(TransactionEvent(
            transaction_id=tid, surfaced_at=T0, event_time=T0 + timedelta(hours=off),
            fraud_score=Decimal(score), typology=None, status="approved",
        ))
    await session.commit()


async def test_network_caps_keep_focal_and_focal_touching(make_client, hub_dataset):
    c = await make_client()
    body = (await c.get(f"/api/v1/transactions/{HUB_ID}/network", headers=_auth())).json()
    assert body["truncated"] is True
    assert len(body["nodes"]) == net.NODE_CAP
    assert len(body["edges"]) <= net.EDGE_CAP
    assert body["edges"][0]["id"] == HUB_ID and body["edges"][0]["focal"] is True
    # Every kept edge touches a focal account (they outrank the 0.90 hop-2 edges), and
    # the senders kept are the highest-scoring ones.
    assert all("ACCTY000" in (e["source"], e["target"]) for e in body["edges"])
    senders = {e["source"] for e in body["edges"][1:]}
    assert senders == {f"ACCTP{i:03d}" for i in range(100 - (net.NODE_CAP - 2), 100)}
    assert {n["label"] for n in body["nodes"]} >= {"****X000", "****Y000"}


async def test_network_edge_cap(make_client, hub_dataset, monkeypatch):
    monkeypatch.setattr(net, "EDGE_CAP", 5)
    monkeypatch.setattr(net, "NODE_CAP", 1000)
    c = await make_client()
    body = (await c.get(f"/api/v1/transactions/{HUB_ID}/network", headers=_auth())).json()
    assert body["truncated"] is True and len(body["edges"]) == 5
    assert body["edges"][0]["focal"] is True
