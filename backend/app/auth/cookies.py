"""Refresh-token cookie helpers."""

from typing import Literal, cast

from fastapi import Response

from app.config import settings

CookieSameSite = Literal["lax", "strict", "none"]


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    same_site = cast(CookieSameSite, settings.COOKIE_SAMESITE)
    secure = settings.COOKIE_SECURE if settings.COOKIE_SECURE is not None else not settings.DEBUG
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path=settings.COOKIE_REFRESH_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    same_site = cast(CookieSameSite, settings.COOKIE_SAMESITE)
    secure = settings.COOKIE_SECURE if settings.COOKIE_SECURE is not None else not settings.DEBUG
    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path=settings.COOKIE_REFRESH_PATH,
        secure=secure,
        samesite=same_site,
        httponly=True,
    )
