from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    log_bucket: str = ""
    state_bucket: str = ""
    public_base_url: str = ""
    max_history_messages: int = Field(default=12, ge=0, le=50)
    max_dataset_bytes: int = Field(default=25_000_000, ge=1_000, le=100_000_000)
    agent_max_tool_rounds: int = Field(default=10, ge=1, le=30)

    @model_validator(mode="after")
    def normalize_urls(self) -> "Settings":
        self.public_base_url = self.public_base_url.rstrip("/")
        return self

    def missing_runtime_values(self) -> list[str]:
        required = {
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "TELEGRAM_WEBHOOK_SECRET": self.telegram_webhook_secret,
            "OPENAI_API_KEY": self.openai_api_key,
            "LOG_BUCKET": self.log_bucket,
            "STATE_BUCKET": self.state_bucket,
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()

