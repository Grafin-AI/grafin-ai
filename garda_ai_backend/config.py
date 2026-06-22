from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    database_url: str
    env: str = "development"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    @model_validator(mode="after")
    def _require_strong_jwt_secret_outside_dev(self) -> "Settings":
        # Fail closed: never run a non-development env with the default or a
        # too-short JWT secret (HS256 needs >= 32 bytes per RFC 7518).
        if self.env != "development" and (
            self.jwt_secret == _DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError(
                "GARDA_JWT_SECRET must be set to a random secret of >= 32 characters "
                "when GARDA_ENV is not 'development'"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
