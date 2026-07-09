from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_name: str = "AgentQA Cloud"
    environment: str = "local"
    database_url: str = Field(default="sqlite:///./agentqa.db", alias="DATABASE_URL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.1-flash-lite", alias="GEMINI_MODEL")
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()