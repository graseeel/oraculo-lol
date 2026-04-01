from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import project_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=project_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="dev", alias="ORACULO_ENV")
    log_level: str = Field(default="INFO", alias="ORACULO_LOG_LEVEL")
    log_format: str = Field(default="human", alias="ORACULO_LOG_FORMAT")  # human|json

    data_dir: Path = Field(default=Path("data"), alias="ORACULO_DATA_DIR")
    db_path: Path = Field(default=Path("data/oraculo.sqlite3"), alias="ORACULO_DB_PATH")

    pandascore_api_key: str = Field(default="", alias="PANDASCORE_API_KEY")
    liquipedia_api_key: str = Field(default="", alias="LIQUIPEDIA_API_KEY")
    riot_api_key: str = Field(default="", alias="RIOT_API_KEY")

    llm_provider: str = Field(default="", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")

    # X (Twitter) — API v2 Free tier, OAuth 1.0a
    twitter_api_key: str = Field(default="", alias="TWITTER_API_KEY")
    twitter_api_secret: str = Field(default="", alias="TWITTER_API_SECRET")
    twitter_access_token: str = Field(default="", alias="TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = Field(default="", alias="TWITTER_ACCESS_TOKEN_SECRET")

    # Threads (Meta)
    threads_user_id: str = Field(default="", alias="THREADS_USER_ID")
    threads_access_token: str = Field(default="", alias="THREADS_ACCESS_TOKEN")

    def abs_data_dir(self) -> Path:
        p = self.data_dir
        return (project_root() / p) if not p.is_absolute() else p

    def abs_db_path(self) -> Path:
        p = self.db_path
        return (project_root() / p) if not p.is_absolute() else p


def load_settings() -> Settings:
    return Settings()