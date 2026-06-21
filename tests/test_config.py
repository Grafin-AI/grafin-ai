from garda_ai_backend.config import Settings, get_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("GARDA_ENV", "production")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.env == "production"
    assert s.log_level == "INFO"  # default


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.delenv("GARDA_ENV", raising=False)
    monkeypatch.delenv("GARDA_LOG_LEVEL", raising=False)
    s = Settings()
    assert s.env == "development"
    assert s.log_level == "INFO"


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
