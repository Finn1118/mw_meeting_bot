from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    recall_api_key: str = Field(min_length=1)
    recall_region: str = "us-east-1"
    recall_webhook_secret: str | None = None
    recall_bot_name: str = "Notetaker"
    poll_interval_seconds: int = 5
    enable_poller: bool = True
    enable_webhooks: bool = False

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/meetings.db"
    blobs_dir: str = "./backend/app/blobs"
    public_webhook_base_url: str | None = None
    enable_google_calendar: bool = True
    calendar_auto_dispatch_interval_seconds: int = 60
    calendar_auto_dispatch_lookahead_minutes: int = 5
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://127.0.0.1:8000/api/auth/google/callback"
    frontend_base_url: str = "http://127.0.0.1:5173"
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173"]
    )

    vite_api_base: str = "http://127.0.0.1:8000"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "recall_webhook_secret",
        "public_webhook_base_url",
        "google_oauth_client_id",
        "google_oauth_client_secret",
        mode="before",
    )
    @classmethod
    def blank_optional_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
