from garda_ai_scoring.scoring.factory import get_scorer
from garda_ai_scoring.scoring.types import ScoringContext, TxnInput

_TXN = {
    "transaction_id": 123,
    "from_account": "0009abc",
    "to_account": "0011def",
    "amount": "15000.00",
    "payment_format": "ACH",
    "is_laundering": True,
    "event_time": "2026-06-25T09:00:00Z",
}


def test_score_requires_token(client):
    r = client.post("/v1/score", json={"transactions": [_TXN]})
    assert r.status_code == 401


def test_expected_query_param_cannot_bypass_auth(client, auth):
    # The old `expected` query-param bypass must stay closed.
    r = client.post("/v1/score?expected=attacker",
                    json={"transactions": [_TXN]},
                    headers={"Authorization": "Bearer attacker"})
    assert r.status_code == 401


def test_score_batch_happy_path(client, auth):
    body = {"transactions": [_TXN, {**_TXN, "transaction_id": 124, "is_laundering": False}]}
    r = client.post("/v1/score", json=body, headers=auth)
    assert r.status_code == 200
    results = r.json()["results"]
    assert [x["transaction_id"] for x in results] == [123, 124]
    for x in results:
        assert 0.0 <= x["fraud_score"] <= 1.0
        assert x["status"] in {"approved", "flagged", "blocked"}


async def test_score_matches_domain_exactly(client, auth):
    from datetime import datetime
    from decimal import Decimal

    r = client.post("/v1/score", json={"transactions": [_TXN]}, headers=auth)
    got = r.json()["results"][0]
    scorer = get_scorer("label_replay")
    expected = await scorer.score(
        TxnInput(
            transaction_id=123,
            from_account="0009abc",
            to_account="0011def",
            amount=Decimal("15000.00"),
            payment_format="ACH",
            is_laundering=True,
            event_time=datetime.fromisoformat("2026-06-25T09:00:00+00:00"),
        ),
        ScoringContext(from_risk_category=None),
    )
    assert got["fraud_score"] == expected.fraud_score
    assert got["status"] == expected.status
    assert got["typology"] == expected.typology


def test_risk_category_changes_score(client, auth):
    low = client.post("/v1/score", json={"transactions": [{**_TXN, "from_risk_category": "Low"}]},
                      headers=auth).json()["results"][0]["fraud_score"]
    high = client.post("/v1/score", json={"transactions": [{**_TXN, "from_risk_category": "High"}]},
                       headers=auth).json()["results"][0]["fraud_score"]
    assert high >= low


def test_empty_batch(client, auth):
    r = client.post("/v1/score", json={"transactions": []}, headers=auth)
    assert r.status_code == 200
    assert r.json() == {"results": []}


def test_malformed_body_422(client, auth):
    r = client.post("/v1/score", json={"transactions": [{"transaction_id": "nope"}]}, headers=auth)
    assert r.status_code == 422
