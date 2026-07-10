from collections.abc import Generator
from pathlib import Path
from threading import Lock

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}
_cache_lock = Lock()


def get_engine(database_url: str | None = None) -> Engine:
    """Return a cached engine without reading settings at module import time."""

    resolved_url = database_url or get_settings().database_url
    _ensure_sqlite_parent(resolved_url)
    with _cache_lock:
        existing = _engines.get(resolved_url)
        if existing is not None:
            return existing

        engine = create_engine(resolved_url, future=True, **_engine_kwargs(resolved_url))
        if resolved_url.startswith("sqlite"):
            event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        _engines[resolved_url] = engine
        return engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    resolved_url = database_url or get_settings().database_url
    with _cache_lock:
        existing = _session_factories.get(resolved_url)
        if existing is not None:
            return existing

    factory = sessionmaker(
        bind=get_engine(resolved_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    with _cache_lock:
        return _session_factories.setdefault(resolved_url, factory)


def dispose_engines() -> None:
    """Dispose cached engines. Intended for tests and controlled shutdown."""

    with _cache_lock:
        engines = list(_engines.values())
        _engines.clear()
        _session_factories.clear()
    for engine in engines:
        engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return
    # URI-mode SQLite URLs manage their own path semantics.
    if url.database.startswith("file:"):
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
