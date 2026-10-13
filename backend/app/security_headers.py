"""Security response headers (docs/11_SECURITY.md).

Set once in middleware so every response carries them, including error
envelopes. HSTS is only emitted in production: sending it over plain HTTP in
development would pin the browser to https://localhost and break local work.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# The frontend is served from a different origin in dev (3000 vs 8000), so
# connect-src must allow both. `default-src 'self'` still blocks injected
# scripts and remote font/img loads.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 "
    "http://127.0.0.1:3000 http://localhost:3000; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a conservative security header set to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Never let a browser MIME-sniff an upload into HTML/JS.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Stop the legacy XSS auditor, which is itself exploitable.
        response.headers.setdefault("X-XSS-Protection", "0")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", _CSP)

        # Cross-origin isolation for the API: no credentials, no sniffing.
        if request.url.path.startswith(settings.api_v1_prefix):
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")

        if settings.is_production:
            # Two years, subdomains included; only meaningful over HTTPS.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
            response.headers.setdefault("Cache-Control", "no-store")

        return response
