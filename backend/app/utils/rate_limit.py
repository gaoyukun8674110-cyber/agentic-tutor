"""Small in-memory sliding-window rate limiter for process-local API guards."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Hashable

RateLimitKey = tuple[Hashable, ...]

_windows: dict[RateLimitKey, deque[float]] = {}


def is_rate_limited(
    key: RateLimitKey,
    *,
    max_attempts: int,
    window_seconds: int,
    now: float | None = None,
) -> bool:
    """Return True when the key has exhausted its allowed window."""
    current_time = time.time() if now is None else now
    window = _windows.setdefault(key, deque())
    while window and current_time - window[0] > window_seconds:
        window.popleft()
    return len(window) >= max_attempts


def record_rate_limit_attempt(key: RateLimitKey, *, now: float | None = None) -> None:
    current_time = time.time() if now is None else now
    _windows.setdefault(key, deque()).append(current_time)


def reset_rate_limit(key: RateLimitKey) -> None:
    _windows.pop(key, None)


def check_rate_limit(
    key: RateLimitKey,
    *,
    max_attempts: int,
    window_seconds: int,
    now: float | None = None,
) -> bool:
    """Record an attempt and return False when the key exceeds the allowed window."""
    if is_rate_limited(key, max_attempts=max_attempts, window_seconds=window_seconds, now=now):
        return False
    record_rate_limit_attempt(key, now=now)
    return True


def clear_rate_limits() -> None:
    """Clear process-local limiter state for tests and maintenance hooks."""
    _windows.clear()
