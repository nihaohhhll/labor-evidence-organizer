"""Database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine(url: str) -> Engine:
    return create_engine(
        url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        future=True,
    )


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create every table. Used by tests; production uses Alembic migrations."""
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(engine)


def dispose_engine() -> None:
    engine.dispose()
