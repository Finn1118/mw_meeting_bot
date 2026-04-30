from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8")

    recall_api_key: str = Field(min_length=1)
    recall_region: str = "us-east-1"
    recall_webhook_secret: str | None = None
    recall_bot_name: str = "Notetaker"
    poll_interval_seconds: int = 5

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/meetings.db"
    blobs_dir: str = "./backend/app/blobs"
    public_webhook_base_url: str | None = None

    vite_api_base: str = "http://127.0.0.1:8000"

    @field_validator("recall_webhook_secret", "public_webhook_base_url", mode="before")
    @classmethod
    def blank_optional_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
