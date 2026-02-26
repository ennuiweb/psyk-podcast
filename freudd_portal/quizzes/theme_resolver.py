"""Resolve active design system for each request."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from .design_systems import (
    DEFAULT_DESIGN_SYSTEM_KEY,
    DesignSystemDefinition,
    get_design_system_definition,
    normalize_design_system_key,
)

logger = logging.getLogger(__name__)

DESIGN_SYSTEM_QUERY_PARAM = "ds"
DESIGN_SYSTEM_PREVIEW_QUERY_PARAM = "preview"
DESIGN_SYSTEM_SESSION_PREVIEW_KEY = "freudd_design_system_preview"
DESIGN_SYSTEM_PERSIST_QUERY_PARAM = "persist"
_NO_PREFERENCE_CACHE = object()


@dataclass(frozen=True)
class ResolvedDesignSystem:
    key: str
    source: str
    is_preview: bool
    definition: DesignSystemDefinition


def _as_bool(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _default_design_system_key() -> str:
    configured = normalize_design_system_key(getattr(settings, "FREUDD_DESIGN_SYSTEM_DEFAULT", ""))
    return configured or DEFAULT_DESIGN_SYSTEM_KEY


def _cookie_name() -> str:
    configured = str(getattr(settings, "FREUDD_DESIGN_SYSTEM_COOKIE_NAME", "") or "").strip()
    return configured or "freudd_design_system"


def _resolve_query_override(request) -> tuple[str | None, bool]:
    query_key = normalize_design_system_key(request.GET.get(DESIGN_SYSTEM_QUERY_PARAM))
    preview_flag = request.GET.get(DESIGN_SYSTEM_PREVIEW_QUERY_PARAM)
    if preview_flag is not None:
        if _as_bool(preview_flag) and query_key:
            request.session[DESIGN_SYSTEM_SESSION_PREVIEW_KEY] = query_key
        if not _as_bool(preview_flag):
            request.session.pop(DESIGN_SYSTEM_SESSION_PREVIEW_KEY, None)
    if query_key:
        return query_key, _as_bool(preview_flag)
    return None, False


def _resolve_session_override(request) -> str | None:
    key = normalize_design_system_key(request.session.get(DESIGN_SYSTEM_SESSION_PREVIEW_KEY))
    if key:
        return key
    request.session.pop(DESIGN_SYSTEM_SESSION_PREVIEW_KEY, None)
    return None


def _resolve_user_preference(request) -> str | None:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(request, "_cached_design_system_preference_key", _NO_PREFERENCE_CACHE)
    if cached is not _NO_PREFERENCE_CACHE:
        return cached

    try:
        from .models import UserInterfacePreference

        pref = UserInterfacePreference.objects.filter(user=user).only("design_system").first()
    except Exception:
        logger.warning("Could not load user interface preference; falling back to default", exc_info=True)
        request._cached_design_system_preference_key = None
        return None

    key = normalize_design_system_key(pref.design_system if pref else None)
    request._cached_design_system_preference_key = key
    return key


def _resolve_cookie_preference(request) -> str | None:
    return normalize_design_system_key(request.COOKIES.get(_cookie_name()))


def resolve_design_system(request) -> ResolvedDesignSystem:
    query_key, query_is_preview = _resolve_query_override(request)
    if query_key:
        return ResolvedDesignSystem(
            key=query_key,
            source="query",
            is_preview=query_is_preview,
            definition=get_design_system_definition(query_key),
        )

    session_key = _resolve_session_override(request)
    if session_key:
        return ResolvedDesignSystem(
            key=session_key,
            source="session",
            is_preview=True,
            definition=get_design_system_definition(session_key),
        )

    user_key = _resolve_user_preference(request)
    if user_key:
        return ResolvedDesignSystem(
            key=user_key,
            source="user",
            is_preview=False,
            definition=get_design_system_definition(user_key),
        )

    cookie_key = _resolve_cookie_preference(request)
    if cookie_key:
        return ResolvedDesignSystem(
            key=cookie_key,
            source="cookie",
            is_preview=False,
            definition=get_design_system_definition(cookie_key),
        )

    fallback_key = _default_design_system_key()
    return ResolvedDesignSystem(
        key=fallback_key,
        source="default",
        is_preview=False,
        definition=get_design_system_definition(fallback_key),
    )


def clear_session_preview_override(request) -> None:
    request.session.pop(DESIGN_SYSTEM_SESSION_PREVIEW_KEY, None)


def get_cookie_name() -> str:
    return _cookie_name()
