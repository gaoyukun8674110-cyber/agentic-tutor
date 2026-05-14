"""Refresh-token cookie helpers."""
from fastapi import Response

from app.config import settings


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.COOKIE_REFRESH_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path=settings.COOKIE_REFRESH_PATH,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        httponly=True,
    )
