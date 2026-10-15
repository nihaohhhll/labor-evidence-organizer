"""Shared pytest fixtures.

The test database is a *separate* PostgreSQL database so a failing test can
never corrupt development data, and each test gets a clean schema. Storage is
pointed at a per-test temp directory for the same reason.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

# Configure the test environment before the app package is imported.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JOB_BACKEND", "inline")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("OCR_PROVIDER", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, engine_kwargs, get_db, create_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.storage import get_storage, reset_storage  # noqa: E402

settings = get_settings()

test_engine = create_engine(settings.test_database_url, **engine_kwargs(settings.test_database_url, echo=False))


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Drop and recreate the test schema once per test session."""
    Base.metadata.drop_all(test_engine)
    create_schema(test_engine)
    yield
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table between tests so tests stay independent."""
    yield
    with test_engine.begin() as conn:
        if settings.test_database_url.startswith("sqlite"):
            # SQLite has no TRUNCATE; delete children first (reversed order).
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
        else:
            tables = ", ".join(f'"{t}"' for t in reversed(Base.metadata.sorted_tables))
            if tables:
                conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def isolated_storage():
    """Point the storage backend at a throwaway directory per test."""
    root = tempfile.mkdtemp(prefix="leo-test-storage-")
    os.environ["STORAGE_LOCAL_ROOT"] = root
    get_settings.cache_clear()
    reset_storage()
    yield root
    reset_storage()
    get_settings.cache_clear()
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def db_session():
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """HTTP client wired to the isolated test database."""

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Register a user and return their Authorization headers."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "tester@example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def second_user_headers(client):
    """A second, unrelated account used for cross-tenant access tests."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "another-good-pass"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def case_id(client, auth_headers) -> str:
    """A case owned by the default test user."""
    resp = client.post(
        "/api/v1/cases",
        json={"name": "测试案件", "description": "测试"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
