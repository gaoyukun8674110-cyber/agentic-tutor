"""Access and refresh token helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import ExpiredSignatureError
from jwt import InvalidTokenError as JwtInvalidTokenError

from app.auth.exceptions import InvalidTokenError, TokenExpiredError
from app.config import settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def _jwt_secret() -> str:
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be configured before issuing tokens")
    return settings.JWT_SECRET


def encode_access_token(username: str, ttl_seconds: int | None = None) -> str:
    issued_at = utc_now()
    expires_at = issued_at + timedelta(seconds=ttl_seconds or settings.ACCESS_TOKEN_TTL_SECONDS)
    payload = {
        "sub": username,
        "type": "access",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token expired") from exc
    except JwtInvalidTokenError as exc:
        raise InvalidTokenError("Invalid access token") from exc

    if claims.get("type") != "access" or not claims.get("sub"):
        raise InvalidTokenError("Invalid access token")
    return claims


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
