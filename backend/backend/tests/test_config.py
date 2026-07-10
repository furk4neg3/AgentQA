from pathlib import Path

import pytest
from app.core.config import Settings


def test_default_database_path_is_absolute_and_predictable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite:////")
    assert Path(settings.database_url.removeprefix("sqlite:///")).name == "agentqa.db"
    assert "/backend/data/" in settings.database_url


def test_cors_rejects_wildcard_origins_with_credentials() -> None:
    with pytest.raises(ValueError, match="wildcard"):
        Settings(cors_origins="*", cors_allow_credentials=True, _env_file=None)


def test_semantic_judge_requires_separate_configuration() -> None:
    with pytest.raises(ValueError, match="SEMANTIC_JUDGE_API_KEY"):
        Settings(
            semantic_judge_provider="gemini",
            semantic_judge_api_key=None,
            _env_file=None,
        )

    settings = Settings(
        semantic_judge_provider="GEMINI",
        semantic_judge_api_key="judge-only-test-key",
        semantic_judge_model="judge-model",
        _env_file=None,
    )
    assert settings.semantic_judge_provider == "gemini"
    assert settings.semantic_judge_model == "judge-model"
