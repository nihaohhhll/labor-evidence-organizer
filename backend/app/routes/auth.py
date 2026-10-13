"""Authentication routes: register and login."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, DbDep
from app.models.user import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth")


def _issue_token(user: User) -> TokenOut:
    token = create_access_token(str(user.id))
    return TokenOut(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DbDep) -> TokenOut:
    """Create a local account and return an access token."""
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        # Registration reveals less than login would: same generic message
        # shape, but 409 so the client can guide the user to sign in.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_TAKEN",
                "message": "An account with this email already exists.",
            },
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        auth_provider="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbDep) -> TokenOut:
    """Exchange credentials for an access token."""
    user = db.scalar(select(User).where(User.email == body.email))
    # Same message + status whether the email or the password is wrong, so
    # the endpoint cannot be used to enumerate accounts.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."},
        )
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    """Return the authenticated user."""
    return user
