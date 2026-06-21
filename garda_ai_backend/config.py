from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    database_url: str
    env: str = "development"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
