from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    # Required — the app must never expose /v1/score without a token (fail fast at startup).
    scoring_token: str = Field(min_length=1)

    scorer: Literal["label_replay", "precomputed", "ml"] = "label_replay"
    # precomputed: scores.csv from `garda-train export-scores` (env GARDA_SCORES_PATH)
    scores_path: Path | None = None
    seed: str = "garda"
    fn_rate: float = 0.05
    fp_rate: float = 0.04
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
