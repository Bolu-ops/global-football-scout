from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://gfs:change-me@localhost:5432/gfs"
    redis_url: str = "redis://localhost:6379/0"

    football_data_org_api_key: str = ""
    api_football_key: str = ""
    sportmonks_api_token: str = ""
    kaggle_username: str = ""
    kaggle_key: str = ""

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    minimum_minutes: int = 900
    excluded_top_leagues_count: int = 3
    excluded_competition_ids: str = ""
    similarity_result_count: int = 10
    percentile_min_pool_size: int = 30

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    data_dir: Path = Field(default=PROJECT_ROOT / "data")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def excluded_competition_id_list(self) -> list[int]:
        return [int(x) for x in self.excluded_competition_ids.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
