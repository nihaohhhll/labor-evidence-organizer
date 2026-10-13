"""FastAPI application factory and process entrypoint."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import settings
from app.logging_config import configure_logging
from app.rate_limit import RateLimitMiddleware
from app.routes import api_router
from app.security_headers import SecurityHeadersMiddleware

# Redaction is installed at import time so no log emitted before the first
# request can leak a 身份证号 / 银行卡号 (docs/11 §9).
configure_logging(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    if settings.is_production and settings.secret_key.startswith("change-me"):
        logger.warning("SECRET_KEY is still the development default — replace it.")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    """Give every request an id so errors can be correlated with logs."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Security headers sit outside rate limiting so they also cover its 429s;
# CORS is added last so it wraps everything — preflight OPTIONS requests are
# answered there and never reach rate limiting or the handlers. Without CORS
# the browser dev origin (:3000) cannot call the API (:8000) at all — this
# gap was surfaced by the Phase 9-C Playwright suite.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # bearer token only — never cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
    max_age=600,
)


def _envelope(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = detail.get("code", "HTTP_ERROR")
    message = detail.get("message", str(exc.detail))
    return _envelope(exc.status_code, code, message, getattr(request.state, "request_id", ""))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Never echo raw internals; a single actionable message is enough.
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", []))
    msg = first.get("msg", "Invalid request body.")
    return _envelope(
        422,
        "VALIDATION_ERROR",
        f"{loc}: {msg}" if loc else msg,
        getattr(request.state, "request_id", ""),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return _envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.",
                     getattr(request.state, "request_id", ""))


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


app.include_router(api_router, prefix=settings.api_v1_prefix)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
