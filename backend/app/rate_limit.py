"""Rate limiting (docs/13 Phase 8 限流, docs/11_SECURITY.md).

A fixed-window counter keyed by (client IP, route class). Chosen over a token
bucket because it needs no external store and is trivially auditable; when the
deployment moves to multiple workers, swap `MemoryStore` for a Redis-backed
implementation — `RateLimitStore` is the seam.

Limits are deliberately stricter for expensive or abuse-prone routes:
authentication (credential stuffing), uploads (disk exhaustion), analysis and
export (CPU). Read-only routes get a generous ceiling so normal browsing never
hits it.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rule:
    """A fixed window: at most `limit` requests per `window` seconds."""

    limit: int
    window: int
    label: str


# Route-class → limit. Matched in order; **first hit wins**, so the more
# specific fragments must come first. Note that `/files/{id}/analyze` also
# contains `/files` — a naive ordering would classify analysis as an upload.
#
# Method matters: POST /cases/{id}/files is an upload, whereas
# GET /files/{id}/content is just a download and should not burn upload budget.
#
# The auth limits are the most important: they are what actually blunts
# credential stuffing. Upload/analysis/export limits stop one user from
# exhausting disk or CPU.
RULES: tuple[tuple[str, str | None, Rule], ...] = (
    ("/auth/login", None, Rule(limit=10, window=60, label="auth")),
    ("/auth/register", None, Rule(limit=5, window=60, label="auth")),
    # Analysis before files, otherwise "/files" swallows "/files/{id}/analyze".
    ("/reanalyze", None, Rule(limit=10, window=60, label="analysis")),
    ("/analyze", None, Rule(limit=10, window=60, label="analysis")),
    ("/exports", None, Rule(limit=10, window=60, label="export")),
    ("/events/build", None, Rule(limit=10, window=60, label="analysis")),
    ("/files", "POST", Rule(limit=30, window=60, label="upload")),
)

# Applied when nothing above matched.
DEFAULT_RULE = Rule(limit=300, window=60, label="read")


class RateLimitStore:
    """Minimal counter contract, so Redis can replace memory later."""

    def hit(self, key: str, window: int) -> tuple[int, float]:
        """Increment `key` and return (count, seconds_until_window_reset)."""
        raise NotImplementedError


class MemoryStore(RateLimitStore):
    """Process-local fixed-window counters.

    A lock guards the dict because ASGI handlers can interleave between
    `incr` and the periodic prune below.
    """

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self._lock = threading.Lock()
        self._ops = 0

    def hit(self, key: str, window: int) -> tuple[int, float]:
        now = time.monotonic()
        with self._lock:
            count, reset_at = self._counts[key]
            if now >= reset_at:
                count, reset_at = 0, now + window
            count += 1
            self._counts[key] = (count, reset_at)

            # Opportunistic prune so a long-lived process cannot grow unbounded.
            self._ops += 1
            if self._ops % 10_000 == 0:
                for k, (_, exp) in list(self._counts.items()):
                    if now >= exp:
                        del self._counts[k]

            return count, max(0.0, reset_at - now)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


_store: RateLimitStore = MemoryStore()

# Mutable so a test can enable the limiter on a live app without rebuilding
# the middleware stack. Defaults to "off under APP_ENV=test" so the rest of
# the suite never throttles itself.
_enabled_override: bool | None = None


def limiter_enabled() -> bool:
    """Whether limiting is active for this request.

    An explicit override wins; otherwise limiting is off in the test env.
    """
    if _enabled_override is not None:
        return _enabled_override
    return settings.app_env != "test"


def set_enabled(value: bool | None) -> None:
    """Force the limiter on/off. `None` restores the environment default."""
    global _enabled_override
    _enabled_override = value


def get_store() -> RateLimitStore:
    return _store


def reset_store() -> None:
    """Drop counters — used by tests so windows never leak between cases."""
    global _store
    _store = MemoryStore()


def classify(path: str, method: str = "GET") -> Rule:
    """Return the rule governing `path`.

    `method` participates because the same path can be an expensive write or
    a cheap read (e.g. `/files/{id}/content` is a download, not an upload).
    """
    upper = method.upper()
    for fragment, required_method, rule in RULES:
        if fragment not in path:
            continue
        if required_method is not None and upper != required_method:
            continue
        return rule
    return DEFAULT_RULE


def client_key(request: Request, path: str) -> str:
    """Identify the caller.

    Authenticated requests key on the user id so one account cannot exhaust
    the budget of everyone behind a shared NAT; everything else keys on the
    client IP.
    """
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id:
        return f"user:{user_id}"
    # X-Forwarded-For is attacker-controlled unless a trusted proxy sets it,
    # so only the socket peer is used here.
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}:{path}"


def _envelope(request: Request, retry_after: float) -> JSONResponse:
    """429 body, still carrying a request_id.

    Rate limiting short-circuits *before* the request-id middleware runs, so
    the id has to be minted here. docs/06 requires `request_id` on every error
    envelope; dropping it would make a 429 the one uncorrelatable response.
    """
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "请求过于频繁，请稍后再试。",
                "request_id": request_id,
            }
        },
        headers={
            "Retry-After": str(max(1, int(retry_after + 0.999))),
            "X-Request-ID": request_id,
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests that exceed their route class's fixed window."""

    async def dispatch(self, request: Request, call_next):
        if not limiter_enabled() or request.method == "OPTIONS":
            return await call_next(request)

        rule = classify(request.url.path, request.method)
        key = client_key(request, request.url.path)
        count, retry_after = get_store().hit(f"{rule.label}:{key}", rule.window)

        request.state.rate_limit_remaining = max(0, rule.limit - count)

        if count > rule.limit:
            # Log the class, not the raw path: logging every distinct path
            # would let one attacker inflate log volume without bound.
            logger.warning("rate limited class=%s key=%s", rule.label, key)
            return _envelope(request, retry_after)

        return await call_next(request)
