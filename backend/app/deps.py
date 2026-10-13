"""Shared FastAPI dependencies (auth, pagination, error envelope)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the authenticated user or raise 401.

    No token / bad token / unknown user all produce the same 401 so that the
    endpoint never reveals whether an account exists.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": "Invalid or missing credentials."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise unauthorized from None

    sub = payload.get("sub")
    if not sub:
        raise unauthorized
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError:
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return str(rid) if rid else ""


def error_envelope(code: str, message: str, request_id: str = "") -> dict[str, Any]:
    """Uniform error body required by docs/06_API_SPEC.md."""
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def owned_case_or_404(db: Session, case_id: uuid.UUID, user_id: uuid.UUID):
    """Resolve a case owned by `user_id`, translating the service error.

    Services raise `FileServiceError` because they must not depend on HTTP.
    Routes use this helper so every ownership miss becomes a 404 with the
    right envelope instead of an unhandled 500.
    """
    from app.services.files import FileServiceError, get_owned_case

    try:
        return get_owned_case(db, case_id, user_id)
    except FileServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from None


def owned_file_or_404(db: Session, file_id: uuid.UUID, user_id: uuid.UUID):
    """Same translation for files."""
    from app.services.files import FileServiceError, get_owned_file

    try:
        return get_owned_file(db, file_id, user_id)
    except FileServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from None
