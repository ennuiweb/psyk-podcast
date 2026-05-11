"""Shared failure classification for queue-owned NotebookLM execution and alerts."""

from __future__ import annotations

from dataclasses import dataclass

AUTH_ERROR_TOKENS = (
    "authentication expired",
    "auth expired",
    "auth invalid",
    "invalid authentication",
    "not logged in",
    "run 'notebooklm login'",
    "redirected to",
)

RATE_LIMIT_ERROR_TOKENS = (
    "rate limit",
    "quota exceeded",
    "resource_exhausted",
    "too many requests",
)

PROFILE_COOLDOWN_ERROR_TOKENS = (
    "no usable profiles found after filtering missing/cooldown entries",
    "is on cooldown",
)

TRANSIENT_NOTEBOOKLM_ERROR_TOKENS = (
    "generator timed out before writing a usable request log",
    "rpc create_artifact failed",
    "rpc create_notebook failed",
    "null result data (possible server error",
    "sources not ready after waiting",
)


@dataclass(frozen=True, slots=True)
class FailureMode:
    code: str
    timed_retry: bool
    blocked: bool = False
    alert_kind: str | None = None


FAILURE_MODE_AUTH_STALE = FailureMode(
    code="auth_stale",
    timed_retry=False,
    blocked=True,
    alert_kind="auth_stale",
)
FAILURE_MODE_RATE_LIMIT = FailureMode(code="rate_limit", timed_retry=True)
FAILURE_MODE_PROFILE_COOLDOWN = FailureMode(code="profile_cooldown", timed_retry=True)
FAILURE_MODE_TRANSIENT_NOTEBOOKLM = FailureMode(code="transient_notebooklm", timed_retry=True)


def _lowered(text: str | None) -> str:
    return str(text or "").lower()


def _has_status_code_context(text: str, code: int, *, extra_phrases: tuple[str, ...] = ()) -> bool:
    import re

    code_pattern = rf"(?:http|status|code|rpc[_ ]code)\s*[:=]?\s*{code}\b"
    if re.search(code_pattern, text):
        return True
    return any(f"{code} {phrase}" in text for phrase in extra_phrases)


def looks_like_auth_error(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in AUTH_ERROR_TOKENS) or _has_status_code_context(
        lowered,
        401,
        extra_phrases=("unauthorized",),
    ) or _has_status_code_context(
        lowered,
        403,
        extra_phrases=("forbidden",),
    )


def looks_like_rate_limit(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in RATE_LIMIT_ERROR_TOKENS) or _has_status_code_context(
        lowered,
        429,
        extra_phrases=("too many requests",),
    )


def looks_like_profile_cooldown_exhaustion(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in PROFILE_COOLDOWN_ERROR_TOKENS)


def looks_like_transient_notebooklm_failure(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in TRANSIENT_NOTEBOOKLM_ERROR_TOKENS)


def classify_failure_mode(text: str | None) -> FailureMode | None:
    if looks_like_auth_error(text):
        return FAILURE_MODE_AUTH_STALE
    if looks_like_rate_limit(text):
        return FAILURE_MODE_RATE_LIMIT
    if looks_like_profile_cooldown_exhaustion(text):
        return FAILURE_MODE_PROFILE_COOLDOWN
    if looks_like_transient_notebooklm_failure(text):
        return FAILURE_MODE_TRANSIENT_NOTEBOOKLM
    return None
