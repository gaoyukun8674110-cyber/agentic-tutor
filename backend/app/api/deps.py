"""Shared API dependencies."""
from typing import Annotated

from fastapi import Depends, Header, status
from sqlalchemy.orm import Session

from app.auth.exceptions import InvalidTokenError, TokenExpiredError
from app.auth.tokens import decode_access_token
from app.database import get_db
from app.models.user import User
from app.utils.errors import api_error


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> User:
    """Validate a Bearer access token and return the active user."""
    token = _extract_bearer(authorization)
    if not token:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing access token")
    try:
        claims = decode_access_token(token)
    except TokenExpiredError:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "token_expired", "Access token expired")
    except InvalidTokenError:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Invalid access token")

    user = db.query(User).filter(User.username == claims["sub"]).first()
    if not user or not user.is_active:
        raise api_error(status.HTTP_403_FORBIDDEN, "forbidden", "User not allowed")
    return user


def require_matching_user(user_id: str, current_user: User) -> None:
    """Reject attempts to access another user's path-scoped resource."""
    if user_id != current_user.username:
        raise api_error(status.HTTP_403_FORBIDDEN, "forbidden", "User is not authorized for this resource")
