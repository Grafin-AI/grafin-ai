import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def token() -> str:
    return "test-token"


@pytest.fixture
def client(token, monkeypatch):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", token)
    from garda_ai_scoring.config import get_settings

    get_settings.cache_clear()
    from garda_ai_scoring.api.app import app

    return TestClient(app)


@pytest.fixture
def auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
