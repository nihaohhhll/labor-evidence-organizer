"""Database engine, session factory and declarative base."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@event.listens_for(Engine, "connect")
def _sqlite_connection_setup(dbapi_connection, connection_record) -> None:
    """Per-connection PRAGMAs for SQLite (portable build + SQLite tests).

    - foreign_keys=ON: PostgreSQL always enforces ON DELETE CASCADE; SQLite
      defaults to OFF, which would silently skip cascade deletes.
    - busy_timeout: wait instead of failing when another connection holds
      the write lock.
    - journal_mode=WAL: readers don't block the writer (file DBs only).
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.fetchall()  # WAL returns a result row
        except Exception:  # noqa: BLE001 - WAL unsupported (e.g. some shares)
            pass
    finally:
        cursor.close()


def engine_kwargs(url: str, *, echo: bool | None = None) -> dict:
    """Shared create_engine kwargs; SQLite needs relaxed thread checks.

    Exposed so tests and one-off scripts build engines the same way the app
    does (the portable Windows build runs entirely on SQLite).
    """
    kwargs: dict = {"echo": settings.db_echo if echo is None else echo, "pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


def _make_engine(url: str) -> Engine:
    return create_engine(url, **engine_kwargs(url))


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema(engine: Engine) -> None:
    """Create every table (tests + portable SQLite build).

    SQLite rejects `UNIQUE (...) DEFERRABLE INITIALLY DEFERRED` (the
    material-package reorder constraints). Production PostgreSQL uses Alembic
    migrations which keep them; for SQLite DDL we strip the flags at compile
    time — it only affects CREATE TABLE rendering, never runtime queries.
    """
    from sqlalchemy import UniqueConstraint

    from app import models  # noqa: F401  (ensure models are registered)

    if engine.url.get_backend_name() == "sqlite":
        for table in Base.metadata.tables.values():
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint) and constraint.deferrable:
                    constraint.deferrable = None
                    constraint.initially = None
    Base.metadata.create_all(engine)


def create_all() -> None:
    """Create every table. Used by tests; production uses Alembic migrations."""
    create_schema(engine)


def dispose_engine() -> None:
    engine.dispose()
