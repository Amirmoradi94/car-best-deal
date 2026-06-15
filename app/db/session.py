from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, sessionmaker as SessionMaker

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db import models  # noqa: F401


def build_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    return _engine_for_url(resolved_settings.database_url)


@lru_cache
def _engine_for_url(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = database_url.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url)


def get_engine() -> Engine:
    return build_engine(get_settings())


@lru_cache
def _session_factory_for_url(database_url: str) -> SessionMaker:
    return sessionmaker(bind=_engine_for_url(database_url), autoflush=False, autocommit=False)


def get_session_factory() -> SessionMaker:
    return _session_factory_for_url(get_settings().database_url)


def init_db(target_engine: Engine | None = None) -> None:
    Base.metadata.create_all(bind=target_engine or get_engine())


def get_session() -> Generator[Session]:
    init_db()
    with get_session_factory()() as session:
        yield session


def clear_session_cache() -> None:
    _session_factory_for_url.cache_clear()
    _engine_for_url.cache_clear()
