from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAFIN_", env_file=".env", extra="ignore")

    database_url: str
    data_dir: str = "../grafin-ai-data/HI-Small"
    batch_size: int = 5000
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
