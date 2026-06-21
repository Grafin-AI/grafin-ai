from garda_ai_backend.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("GARDA_ENV", "production")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.env == "production"
    assert s.log_level == "INFO"  # default
