from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    ingest_url: str = "http://localhost:8000/api/v1/ingest"
    ingest_token: str = Field(min_length=1)  # required, non-empty
    data_dir: str = "../garda-ai-data/HI-Small"
    trans_files: list[str] = ["HI-Small_Trans_part1.csv", "HI-Small_Trans_part2.csv"]
    batch_size: int = Field(default=100, gt=0, le=1000)
    speed: float = Field(default=60.0, gt=0)
    max_gap_s: float = Field(default=2.0, ge=0)
    limit: int | None = None
    dry_run: bool = False
    request_timeout_s: float = 30.0
    retries: int = 3
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
