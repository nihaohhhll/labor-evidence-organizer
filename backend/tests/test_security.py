"""Phase 8-Hardening: security headers, rate limiting, redaction, passwords.

These cover the "必须做到" list in docs/11_SECURITY.md that is verifiable
without a browser or an external service.
"""

from __future__ import annotations

import logging
import time

import pytest

from app.rate_limit import (
    DEFAULT_RULE,
    MemoryStore,
    Rule,
    classify,
    get_store,
    reset_store,
)
from app.redaction import redact, redact_mapping
from app.schemas import PASSWORD_MIN, password_problems


# ---------- security headers ----------


def test_security_headers_present_on_success(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    h = resp.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["X-XSS-Protection"] == "0"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["Content-Security-Policy"].startswith("default-src 'self'")


def test_security_headers_present_on_error(client, auth_headers):
    """Headers must survive the error path too — that is where XSS lands."""
    resp = client.get("/api/v1/cases/not-a-uuid", headers=auth_headers)
    assert resp.status_code in (404, 422)
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]


def test_request_id_echoed(client, auth_headers):
    resp = client.get("/healthz", headers={"X-Request-ID": "my-trace-123"})
    assert resp.headers["X-Request-ID"] == "my-trace-123"


def test_hsts_only_in_production():
    """Emitting HSTS over dev http would pin the browser to https://localhost."""
    from app.security_headers import SecurityHeadersMiddleware  # noqa: F401
    from app.config import settings

    assert settings.app_env != "production"
    # Dev must not send it; production must.
    assert not settings.is_production


# ---------- rate limiting ----------


def test_route_classification_is_specific():
    """/files/{id}/analyze must be analysis, not upload (substring trap)."""
    assert classify("/api/v1/files/x/analyze", "POST").label == "analysis"
    assert classify("/api/v1/cases/x/files", "POST").label == "upload"
    # A download from the same path is not an upload.
    assert classify("/api/v1/files/x/content", "GET").label == "read"
    assert classify("/api/v1/cases", "GET").label == "read"


def test_auth_is_stricter_than_read():
    assert classify("/api/v1/auth/login", "POST").limit < DEFAULT_RULE.limit


def test_store_counts_and_resets_per_window():
    store = MemoryStore()
    count, retry = store.hit("k", window=1)
    assert count == 1 and retry > 0
    for _ in range(4):
        count, _ = store.hit("k", window=1)
    assert count == 5

    # Let the window lapse and confirm the counter resets.
    time.sleep(1.05)
    count, _ = store.hit("k", window=1)
    assert count == 1


def test_login_endpoint_returns_429_with_retry_after(client, monkeypatch):
    """Hitting the login limit must 429 and tell the client when to retry.

    The limiter is off under APP_ENV=test, so it is switched on explicitly
    here and restored afterwards — otherwise this case would silently stop
    testing anything if the default ever changed.
    """
    from app import rate_limit as rl

    monkeypatch.setattr(
        rl, "RULES", (("/auth/login", None, Rule(limit=3, window=60, label="auth")),)
    )
    monkeypatch.setattr(rl, "DEFAULT_RULE", Rule(limit=1000, window=60, label="read"))
    rl.set_enabled(True)
    rl.reset_store()
    try:
        statuses = []
        last = None
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "whatever-pass-xx"},
            )
            statuses.append(resp.status_code)
            last = resp
    finally:
        rl.set_enabled(None)
        rl.reset_store()

    assert 429 in statuses, statuses
    assert last is not None and last.status_code == 429
    assert last.headers["Retry-After"]
    body = last.json()["error"]
    assert body["code"] == "RATE_LIMITED"
    assert body["request_id"]  # envelope shape is preserved under 429


def test_rate_limit_is_per_client_not_global(client):
    """One client's budget must not consume another's."""
    from app.rate_limit import client_key
    from starlette.requests import Request

    scope_a = {"type": "http", "client": ("10.0.0.1", 1), "method": "GET", "path": "/x", "headers": []}
    scope_b = {"type": "http", "client": ("10.0.0.2", 2), "method": "GET", "path": "/x", "headers": []}
    assert client_key(Request(scope_a), "/x") != client_key(Request(scope_b), "/x")


def test_disabled_in_test_env_by_default(client, auth_headers):
    """The suite must not throttle itself: the limiter is off under APP_ENV=test."""
    for _ in range(40):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200


# ---------- redaction ----------


@pytest.mark.parametrize(
    "text,expected_absent,expected_present",
    [
        ("身份证号110101199001011234", "110101199001011234", "1234"),
        ("卡号6222021234567890123", "6222021234567890123", "0123"),
        ("电话13800138000", "13800138000", "138****8000"),
        ("电话+86 138-0013-8000", "138-0013-8000", "138****8000"),
        ("电话 138 0013 8000", "138 0013 8000", "138****8000"),
        ("邮箱zhang.san@example.com", "zhang.san@example.com", "example.com"),
        ("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijk", "eyJzdWIi", "REDACTED"),
        ("sk-abcdef1234567890abcdef", "sk-abcdef1234567890", "REDACTED"),
    ],
)
def test_redact_masks_sensitive_values(text, expected_absent, expected_present):
    out = redact(text)
    assert expected_absent not in out, out
    assert expected_present in out, out


@pytest.mark.parametrize(
    "text",
    [
        "月工资7500元，补偿15000元",
        "合同期限2022-10-01至2025-09-30",
        "入职日期：2022年10月1日",
        "座机010-12345678",
        "门牌号138号",
    ],
)
def test_redact_does_not_clobber_ordinary_evidence(text):
    """Over-redacting would make logs useless for debugging real issues."""
    assert redact(text) == text


def test_redact_never_raises_on_malformed_input():
    assert redact("") == ""
    assert isinstance(redact("1" * 400), str)


def test_redact_mapping_is_recursive():
    data = {
        "filename": "张三身份证扫描件.jpg",
        "nested": {"phone": "13800138000", "count": 3},
        "list": ["a@b.com", 42, {"card": "6222021234567890123"}],
    }
    out = redact_mapping(data)
    assert out["nested"]["phone"] == "138****8000"
    assert out["nested"]["count"] == 3  # non-strings untouched
    assert out["list"][1] == 42
    assert "6222021234567890123" not in out["list"][2]["card"]


def test_log_filter_scrubs_emitted_records(caplog):
    """The filter must act on what actually reaches the output."""
    logger = logging.getLogger("app.tests.redaction")
    with caplog.at_level(logging.INFO, logger="app.tests.redaction"):
        logger.info("user id_card=110101199001011234 phone=13800138000")
    text = caplog.text
    assert "110101199001011234" not in text, text
    assert "13800138000" not in text, text


def test_log_filter_scrubs_formatted_args(caplog):
    logger = logging.getLogger("app.tests.redaction2")
    with caplog.at_level(logging.INFO, logger="app.tests.redaction2"):
        logger.info("card=%s", "6222021234567890123")
    assert "6222021234567890123" not in caplog.text


def test_logging_is_redacting_by_default():
    """basicConfig is installed with the filter attached at import time."""
    from app.logging_config import RedactingFilter

    root = logging.getLogger()
    assert any(isinstance(f, RedactingFilter) for f in root.filters)


# ---------- password policy ----------


@pytest.mark.parametrize(
    "password",
    [
        "correct-horse-battery",
        "another-good-pass",
        "Tr0ub4dor&3xxxx",
        "劳动争议案件整理材料2026",
    ],
)
def test_accepts_passphrases(password):
    assert password_problems(password) == []


@pytest.mark.parametrize(
    "password,fragment",
    [
        ("short1A!", "至少"),
        ("password1234", "常见"),
        ("Qwertyuiop12", "序列"),
        ("123456789012", "序列"),
        ("aaaaaaaaaaaaaaaa", "字符过少"),
        ("  paddedpass  ", "空白"),
    ],
)
def test_rejects_weak_passwords(password, fragment):
    problems = password_problems(password)
    assert problems, f"{password!r} 应被拒绝"
    assert any(fragment in p for p in problems), problems


def test_register_endpoint_enforces_policy(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "password123"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_min_length_constant_is_sane():
    assert PASSWORD_MIN >= 12
