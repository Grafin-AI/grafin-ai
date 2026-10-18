"""Firestore explanation store + CORS setting. No network: an in-memory fake client."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from google.api_core.exceptions import AlreadyExists
from httpx import ASGITransport, AsyncClient

from grafin_ai_backend.config import Settings
from grafin_ai_backend.main import configure_cors
from grafin_ai_backend.repositories import explanations_firestore as fs
from grafin_ai_backend.repositories.explanations import (
    ExplanationsRepository,
    explanations_repository,
)


class _Snap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, store: dict, key: tuple[str, str], fail_set: bool) -> None:
        self._store, self._key, self._fail_set = store, key, fail_set

    async def get(self) -> _Snap:
        return _Snap(self._store.get(self._key))

    async def create(self, data: dict[str, Any]) -> None:
        if self._key in self._store:
            raise AlreadyExists("exists")
        self._store[self._key] = dict(data)

    async def update(self, data: dict[str, Any]) -> None:
        self._store[self._key].update(data)

    async def set(self, data: dict[str, Any]) -> None:
        if self._fail_set:
            raise RuntimeError("firestore down")
        self._store[self._key] = dict(data)


class _Collection:
    def __init__(self, client: "FakeAsyncClient", name: str) -> None:
        self._client, self._name = client, name

    def document(self, doc_id: str) -> _Doc:
        return _Doc(self._client.store, (self._name, doc_id), self._client.fail_set)


class FakeAsyncClient:
    def __init__(self, fail_set: bool = False) -> None:
        self.store: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_set = fail_set

    def collection(self, name: str) -> _Collection:
        return _Collection(self, name)


def _values(tid: int = 7, recommendation: str = "TUNDA transaksi.") -> dict[str, Any]:
    return {
        "transaction_id": tid,
        "source": "llm",
        "model": "gemini-2.5-flash",
        "pattern_matching": "pola",
        "behavior_analysis": "perilaku",
        "network_analysis": "jaringan",
        "recommendation": recommendation,
        "reason_code": "FAN_IN",
        "confidence": "high",
        "references": [{"id": "r1", "title": "t"}],
        "risk_factors": [{"code": "high_model_score"}],
        "evidence": {"fraud_score": 0.9},
        "generated_by": "analyst@example.com",
        "generated_at": datetime(2025, 9, 1, tzinfo=UTC),
    }


def _settings(**kw: Any) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@h:5432/d",
        scoring_url="http://scoring",
        scoring_token="t",
        ingest_token="x" * 16,
        **kw,
    )


async def test_get_missing_returns_none():
    repo = fs.FirestoreExplanationsRepository(None, FakeAsyncClient())
    assert await repo.get(1) is None


async def test_insert_if_absent_creates_doc_with_created_at():
    client = FakeAsyncClient()
    repo = fs.FirestoreExplanationsRepository(None, client)
    row = await repo.insert_if_absent(_values())
    assert row.transaction_id == 7
    assert row.recommendation == "TUNDA transaksi."
    assert row.str_draft is None
    stored = client.store[("transaction_explanations", "7")]
    assert isinstance(stored["created_at"], datetime)
    assert stored["evidence"] == {"fraud_score": 0.9}


async def test_insert_twice_keeps_the_first():
    client = FakeAsyncClient()
    repo = fs.FirestoreExplanationsRepository(None, client)
    await repo.insert_if_absent(_values(recommendation="first"))
    row = await repo.insert_if_absent(_values(recommendation="second"))
    assert row.recommendation == "first"
    assert (await repo.get(7)).recommendation == "first"


async def test_str_draft_first_wins_and_is_mirrored():
    client = FakeAsyncClient()
    repo = fs.FirestoreExplanationsRepository(None, client, model_name="gemini-2.5-flash")
    await repo.insert_if_absent(_values())
    at = datetime(2025, 9, 2, tzinfo=UTC)
    row = await repo.set_str_draft_if_absent(7, {"nomor_draf": "A"}, at)
    assert row.str_draft == {"nomor_draf": "A"}
    row = await repo.set_str_draft_if_absent(7, {"nomor_draf": "B"}, at)
    assert row.str_draft == {"nomor_draf": "A"}
    mirrored = client.store[("str_drafts", "7")]
    assert mirrored["draft"] == {"nomor_draf": "A"}
    assert mirrored["model"] == "gemini-2.5-flash"
    assert mirrored["generated_at"] == at


async def test_str_draft_mirror_failure_does_not_raise():
    client = FakeAsyncClient(fail_set=True)
    repo = fs.FirestoreExplanationsRepository(None, client)
    await repo.insert_if_absent(_values())
    row = await repo.set_str_draft_if_absent(7, {"nomor_draf": "A"}, datetime.now(UTC))
    assert row.str_draft == {"nomor_draf": "A"}
    assert ("str_drafts", "7") not in client.store


def test_default_store_is_postgres():
    s = _settings()
    assert s.explanation_store == "postgres"
    assert s.firestore_database == "(default)"
    assert isinstance(explanations_repository(None, s), ExplanationsRepository)
    assert isinstance(explanations_repository(None), ExplanationsRepository)


def test_firestore_store_selected_by_setting(monkeypatch):
    fake = FakeAsyncClient()
    monkeypatch.setattr(fs, "_client", fake)
    repo = explanations_repository(None, _settings(explanation_store="firestore"))
    assert isinstance(repo, fs.FirestoreExplanationsRepository)
    assert repo._client is fake


def test_firestore_client_created_lazily_once(monkeypatch):
    from google.cloud import firestore

    created: list[dict] = []

    class _Stub:
        def __init__(self, **kw: Any) -> None:
            created.append(kw)

    monkeypatch.setattr(fs, "_client", None)
    monkeypatch.setattr(firestore, "AsyncClient", _Stub)
    s = _settings(explanation_store="firestore", firestore_project="grafin-test-project")
    first = fs.get_firestore_client(s)
    assert fs.get_firestore_client(s) is first
    assert created == [{"project": "grafin-test-project", "database": "(default)"}]


def test_settings_read_store_env(monkeypatch):
    monkeypatch.setenv("GRAFIN_EXPLANATION_STORE", "firestore")
    monkeypatch.setenv("GRAFIN_FIRESTORE_PROJECT", "grafin-test-project")
    monkeypatch.setenv("GRAFIN_FIRESTORE_DATABASE", "grafin")
    monkeypatch.setenv("GRAFIN_CORS_ORIGINS", "https://a.web.app, https://b.firebaseapp.com,")
    s = _settings()
    assert (s.explanation_store, s.firestore_project, s.firestore_database) == (
        "firestore", "grafin-test-project", "grafin",
    )
    assert s.cors_origin_list == ["https://a.web.app", "https://b.firebaseapp.com"]


async def _preflight(app: FastAPI, origin: str):
    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.options("/ping", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        })


async def test_cors_allows_configured_origin():
    app = FastAPI()
    configure_cors(app, _settings(cors_origins="https://grafin-test-project.web.app"))
    r = await _preflight(app, "https://grafin-test-project.web.app")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://grafin-test-project.web.app"
    r = await _preflight(app, "https://evil.example")
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("origins", ["", " , "])
async def test_cors_empty_adds_no_middleware(origins):
    app = FastAPI()
    configure_cors(app, _settings(cors_origins=origins))
    r = await _preflight(app, "https://grafin-test-project.web.app")
    assert "access-control-allow-origin" not in r.headers
