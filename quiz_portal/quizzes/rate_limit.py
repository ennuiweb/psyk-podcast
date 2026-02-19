"""Simple IP-based request throttling helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.core.cache import cache
from django.http import HttpRequest


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


def get_client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def evaluate_rate_limit(
    request: HttpRequest,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    if limit <= 0 or window_seconds <= 0:
        return RateLimitResult(allowed=True, retry_after_seconds=0)

    key = f"rate-limit:{scope}:{get_client_ip(request)}"
    now = int(time.time())
    state = cache.get(key)

    if not isinstance(state, dict) or state.get("reset_at", 0) <= now:
        reset_at = now + window_seconds
        cache.set(key, {"count": 1, "reset_at": reset_at}, timeout=window_seconds)
        return RateLimitResult(allowed=True, retry_after_seconds=0)

    count = int(state.get("count", 0))
    reset_at = int(state.get("reset_at", now + window_seconds))
    retry_after = max(reset_at - now, 1)

    if count >= limit:
        return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

    state["count"] = count + 1
    cache.set(key, state, timeout=retry_after)
    return RateLimitResult(allowed=True, retry_after_seconds=0)
