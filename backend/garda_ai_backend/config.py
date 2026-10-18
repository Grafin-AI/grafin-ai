from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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

    # --- Ingest write-path (Phase 2) ---
    scoring_url: str
    scoring_token: str = Field(min_length=1)
    ingest_token: str = Field(min_length=16)
    scoring_timeout_s: float = 5.0
    scoring_retries: int = 2
    # Name of the trained model behind the scoring service (e.g. "GraphSAGE-GNN v1").
    # Empty = Phase 1 label-replay, so accuracy figures are simulated.
    model_name: str = ""

    # --- Transaction explanations (LLM narrative; "none" = deterministic rules only) ---
    llm_provider: Literal["none", "anthropic", "gemini", "ollama"] = "none"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""  # empty = provider default (see services/explain/llm.py)
    llm_base_url: str = ""  # empty = provider default
    llm_timeout_s: float = 20.0
    llm_tools: bool = True  # gemini: function-calling grounding round(s) before the JSON answer

    # --- Explanation / LTKM draft store ("firestore" = Google Cloud Firestore via ADC) ---
    explanation_store: Literal["postgres", "firestore"] = "postgres"
    firestore_project: str | None = None  # None = ADC / environment default project
    firestore_database: str = "(default)"

    # --- CORS: comma-separated allowed origins; empty = no CORS middleware ---
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
