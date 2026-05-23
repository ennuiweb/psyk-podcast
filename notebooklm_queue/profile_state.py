"""Shared NotebookLM profile-state classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


MAX_VALIDATION_AGE_ENV_VAR = "NOTEBOOKLM_PROFILE_MAX_VALIDATION_AGE_SECONDS"


@dataclass(frozen=True, slots=True)
class ProfileStateStatus:
    status: str
    reason: str
    cooldown_remaining_seconds: int = 0


def classify_profile_state(
    *,
    state_entry: dict[str, Any],
    storage_path: Path,
    now_ts: float,
    max_validation_age_seconds: int | None = None,
) -> ProfileStateStatus:
    """Return the queue-visible status for one NotebookLM profile."""

    storage_exists = storage_path.exists()
    if not storage_exists:
        return ProfileStateStatus(status="missing_storage", reason="storage_file_missing")

    if _last_auth_probe_failed(state_entry):
        return ProfileStateStatus(status="auth_stale", reason="last_probe_failed_auth")

    if _last_auth_refresh_failed(state_entry):
        return ProfileStateStatus(status="auth_stale", reason="last_refresh_failed_auth")

    last_error = str(state_entry.get("last_error") or "").strip()
    if last_error == "auth":
        last_used = _coerce_float(state_entry.get("last_used"), 0.0)
        storage_mtime = _storage_mtime(storage_path)
        if last_used <= 0 or storage_mtime is None or storage_mtime <= last_used:
            return ProfileStateStatus(
                status="auth_stale",
                reason="storage_not_refreshed_after_auth_failure",
            )

    cooldown_until = _coerce_float(state_entry.get("cooldown_until"), 0.0)
    if cooldown_until > now_ts:
        return ProfileStateStatus(
            status="cooldown",
            reason=f"{last_error or 'profile'}_cooldown",
            cooldown_remaining_seconds=max(int(cooldown_until - now_ts), 1),
        )

    validation_age = _validation_age_seconds(
        state_entry=state_entry,
        now_ts=now_ts,
        max_validation_age_seconds=max_validation_age_seconds,
    )
    if validation_age is not None and validation_age > 0:
        return ProfileStateStatus(status="refresh_required", reason="validation_expired")

    return ProfileStateStatus(status="usable", reason="available")


def profile_auth_is_stale(
    *,
    state_entry: dict[str, Any],
    storage_path: Path,
    now_ts: float | None = None,
) -> bool:
    return (
        classify_profile_state(
            state_entry=state_entry,
            storage_path=storage_path,
            now_ts=float(now_ts or 0.0),
            max_validation_age_seconds=0,
        ).status
        == "auth_stale"
    )


def profile_auth_is_unrecovered(
    *,
    state_entry: dict[str, Any],
    storage_path: Path,
) -> bool:
    """Return true when auth failed and the storage file has not changed since."""

    auth_failure_ts = max(
        _coerce_float(state_entry.get("last_used"), 0.0),
        _coerce_float(state_entry.get("last_probe_attempt"), 0.0),
        _coerce_float(state_entry.get("last_refresh_attempt"), 0.0),
    )
    has_auth_marker = (
        str(state_entry.get("last_error") or "").strip() == "auth"
        or _last_auth_probe_failed(state_entry)
        or _last_auth_refresh_failed(state_entry)
    )
    if not has_auth_marker:
        return False

    storage_mtime = _storage_mtime(storage_path)
    if storage_mtime is None:
        return True
    if auth_failure_ts <= 0:
        return True
    return storage_mtime <= auth_failure_ts


def max_validation_age_from_env(default: int = 0) -> int:
    raw = str(os.environ.get(MAX_VALIDATION_AGE_ENV_VAR) or "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        return default


def _last_auth_refresh_failed(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get("last_refresh_status") or "").strip() == "failed"
        and str(entry.get("last_refresh_error_type") or "").strip() == "auth"
    )


def _last_auth_probe_failed(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get("last_probe_status") or "").strip() == "failed"
        and str(entry.get("last_probe_error_type") or "").strip() == "auth"
    )


def _validation_age_seconds(
    *,
    state_entry: dict[str, Any],
    now_ts: float,
    max_validation_age_seconds: int | None,
) -> int | None:
    max_age = max_validation_age_seconds
    if max_age is None:
        max_age = max_validation_age_from_env()
    if max_age <= 0:
        return None
    last_validated = max(
        _coerce_float(state_entry.get("last_probe_success"), 0.0),
        _coerce_float(state_entry.get("last_refreshed"), 0.0),
    )
    if last_validated <= 0:
        return max_age + 1
    age = int(now_ts - last_validated)
    return age if age > max_age else None


def _storage_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
