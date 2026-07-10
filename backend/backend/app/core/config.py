import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DEFAULT_DATABASE_URL = f"sqlite:///{(DATA_DIR / 'agentqa.db').as_posix()}"


class Settings(BaseSettings):
    app_name: str = "AgentQA Cloud"
    environment: str = "local"
    database_url: str = Field(default=DEFAULT_DATABASE_URL, alias="DATABASE_URL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_input_cost_per_million: float = Field(
        default=0.30, alias="GEMINI_INPUT_COST_PER_MILLION"
    )
    gemini_output_cost_per_million: float = Field(
        default=2.50, alias="GEMINI_OUTPUT_COST_PER_MILLION"
    )
    gemini_min_request_interval_seconds: float = Field(
        default=5.0,
        alias="GEMINI_MIN_REQUEST_INTERVAL_SECONDS",
    )
    semantic_judge_provider: str = Field(default="disabled", alias="SEMANTIC_JUDGE_PROVIDER")
    semantic_judge_api_key: str | None = Field(default=None, alias="SEMANTIC_JUDGE_API_KEY")
    semantic_judge_model: str = Field(default="gemini-2.5-flash", alias="SEMANTIC_JUDGE_MODEL")
    semantic_judge_timeout_seconds: float = Field(
        default=30.0, alias="SEMANTIC_JUDGE_TIMEOUT_SECONDS"
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )
    cors_allow_credentials: bool = Field(default=False, alias="CORS_ALLOW_CREDENTIALS")
    trace_redact_keys: str = Field(
        default="authorization,cookie,set-cookie,api_key,apikey,password,secret,token",
        alias="TRACE_REDACT_KEYS",
    )
    authentication_mode: str = Field(default="local-development-only", alias="AUTHENTICATION_MODE")

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

    @property
    def trace_redact_key_set(self) -> set[str]:
        return {key.strip().casefold() for key in self.trace_redact_keys.split(",") if key.strip()}

    @model_validator(mode="after")
    def validate_cors(self) -> "Settings":
        if "*" in self.cors_origin_list and self.cors_allow_credentials:
            raise ValueError("CORS wildcard origins cannot be combined with credentials")
        if self.gemini_input_cost_per_million < 0 or self.gemini_output_cost_per_million < 0:
            raise ValueError("Provider pricing cannot be negative")
        if self.gemini_min_request_interval_seconds < 0:
            raise ValueError("Gemini request interval cannot be negative")
        judge_provider = self.semantic_judge_provider.casefold().strip()
        judge_provider = self.semantic_judge_provider.casefold().strip()
        if judge_provider not in {"disabled", "gemini"}:
            raise ValueError("SEMANTIC_JUDGE_PROVIDER must be 'disabled' or 'gemini'")
        if judge_provider == "gemini" and not (self.semantic_judge_api_key or "").strip():
            raise ValueError("SEMANTIC_JUDGE_API_KEY is required when semantic judging uses Gemini")
        if self.semantic_judge_timeout_seconds <= 0:
            raise ValueError("Semantic judge timeout must be positive")
        self.semantic_judge_provider = judge_provider
        return self


@lru_cache
def get_settings() -> Settings:
    env_file = (
        None if os.environ.get("ENVIRONMENT", "").casefold() in {"test", "testing"} else ENV_FILE
    )
    return Settings(_env_file=env_file)
