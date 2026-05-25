"""Origin checks for Google OAuth entrypoints."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def _normalized_origin(value: str) -> str:
    return value.strip().rstrip("/").lower()


def request_origin(request: HttpRequest) -> str:
    scheme = "https" if request.is_secure() else "http"
    return _normalized_origin(f"{scheme}://{request.get_host()}")


def google_auth_origin_allowed(request: HttpRequest) -> bool:
    allowed_origins = {
        _normalized_origin(origin)
        for origin in getattr(settings, "FREUDD_AUTH_GOOGLE_ALLOWED_ORIGINS", [])
        if origin
    }
    if not allowed_origins:
        return True
    return request_origin(request) in allowed_origins


def google_auth_available(request: HttpRequest) -> bool:
    return bool(
        getattr(settings, "FREUDD_AUTH_GOOGLE_ENABLED", False)
    ) and google_auth_origin_allowed(request)
