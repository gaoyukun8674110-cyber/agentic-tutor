"""Authentication API routes."""
from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth.cookies import clear_refresh_cookie, set_refresh_cookie
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import encode_access_token, generate_refresh_token, hash_refresh_token, iso_now, utc_now
from app.config import settings
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import RefreshToken, User
from app.utils.errors import api_error

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)
    email: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("username must be 3-64 characters and contain only letters, numbers, _ or -")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be a valid email address")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


def _user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _create_refresh_token(db: Session, user: User, request: Request) -> str:
    raw_token = generate_refresh_token()
    now = utc_now()
    expires_at = now + timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        issued_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
        created_at=now.isoformat(),
        user_agent=request.headers.get("user-agent"),
        client_ip=_client_ip(request),
    )
    db.add(record)
    return raw_token


def _refresh_record(db: Session, raw_token: str) -> RefreshToken | None:
    return db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token)).first()


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise api_error(status.HTTP_409_CONFLICT, "username_taken", "Username is already taken")

    if payload.email:
        existing_email = db.query(User).filter(User.email == str(payload.email)).first()
        if existing_email:
            raise api_error(status.HTTP_409_CONFLICT, "email_taken", "Email is already taken")

    now = iso_now()
    user = User(
        username=payload.username,
        email=str(payload.email) if payload.email else None,
        password_hash=hash_password(payload.password),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": _user_payload(user)}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise api_error(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid credentials")
    if not user.is_active:
        raise api_error(status.HTTP_403_FORBIDDEN, "account_disabled", "Account is disabled")

    now = iso_now()
    user.last_login_at = now
    user.updated_at = now
    refresh_token = _create_refresh_token(db, user, request)
    db.commit()

    set_refresh_cookie(response, refresh_token)
    return {
        "access_token": encode_access_token(user.username),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL_SECONDS,
        "user": _user_payload(user),
    }


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.COOKIE_REFRESH_NAME),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not refresh_token:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "missing_refresh", "Missing refresh token")

    record = _refresh_record(db, refresh_token)
    if not record:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "invalid_refresh", "Invalid refresh token")
    if record.revoked_at:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "revoked_refresh", "Refresh token has been revoked")
    if utc_now().isoformat() > record.expires_at:
        record.revoked_at = iso_now()
        db.commit()
        raise api_error(status.HTTP_401_UNAUTHORIZED, "expired_refresh", "Refresh token expired")
    if not record.user or not record.user.is_active:
        raise api_error(status.HTTP_403_FORBIDDEN, "account_disabled", "Account is disabled")

    record.revoked_at = iso_now()
    new_refresh_token = _create_refresh_token(db, record.user, request)
    db.commit()
    set_refresh_cookie(response, new_refresh_token)
    return {
        "access_token": encode_access_token(record.user.username),
        "expires_in": settings.ACCESS_TOKEN_TTL_SECONDS,
    }


@router.post("/logout")
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.COOKIE_REFRESH_NAME),
    db: Session = Depends(get_db),
) -> Response:
    if refresh_token:
        record = _refresh_record(db, refresh_token)
        if record and not record.revoked_at:
            record.revoked_at = iso_now()
            db.commit()
    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict[str, object]:
    return {"user": _user_payload(current_user)}
