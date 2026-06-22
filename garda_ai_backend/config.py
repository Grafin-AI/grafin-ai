from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    database_url: str
    env: str = "development"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
