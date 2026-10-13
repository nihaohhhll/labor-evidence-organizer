"""Auth endpoint tests: happy paths and the anti-enumeration guarantees."""

from __future__ import annotations


def test_register_returns_token_and_user(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "A@Example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # Email must be normalised so login is case-insensitive.
    assert body["user"]["email"] == "a@example.com"


def test_register_rejects_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "correct-horse-battery"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_rejects_short_password(client):
    resp = client.post(
        "/api/v1/auth/register", json={"email": "short@example.com", "password": "abc"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_succeeds_with_correct_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "correct-horse-battery"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


def test_login_wrong_password_and_unknown_email_look_identical(client):
    """Neither case may reveal whether the account exists."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "known@example.com", "password": "correct-horse-battery"},
    )
    wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "not-the-password"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "not-the-password"},
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["code"] == unknown.json()["error"]["code"]


def test_me_requires_valid_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bogus"}).status_code
        == 401
    )


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "tester@example.com"


def test_password_is_never_stored_in_plaintext(client, db_session):
    from sqlalchemy import select

    from app.models.user import User

    client.post(
        "/api/v1/auth/register",
        json={"email": "hash@example.com", "password": "correct-horse-battery"},
    )
    user = db_session.scalar(select(User).where(User.email == "hash@example.com"))
    assert user is not None
    assert user.password_hash != "correct-horse-battery"
    assert user.password_hash.startswith("$2")
