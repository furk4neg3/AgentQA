from __future__ import annotations

import os
import socket
import sys

os.environ["ENVIRONMENT"] = "test"
os.environ["GEMINI_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CORS_ORIGINS"] = "http://testserver"

import pytest
from app.core.config import Settings
from app.db.seed import seed_database
from app.db.session import Base, dispose_engines
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def isolated_settings_and_network(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Never load a developer .env or allow a test to reach a real provider."""

    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{tmp_path / 'agentqa-test.db'}",
        GEMINI_API_KEY=None,
        CORS_ORIGINS="http://testserver",
        CORS_ALLOW_CREDENTIALS=False,
        AUTHENTICATION_MODE="local-development-only",
    )

    def test_settings() -> Settings:
        return settings

    # Several modules import get_settings directly; replace only already-loaded
    # application references so collection itself remains side-effect free.
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("app.") and hasattr(module, "get_settings"):
            monkeypatch.setattr(module, "get_settings", test_settings)

    def reject_network(_socket, address):
        raise AssertionError(f"Network access is forbidden in tests: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    yield
    dispose_engines()


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    try:
        with TestingSessionLocal() as session:
            seed_database(session)
            yield session
    finally:
        engine.dispose()
