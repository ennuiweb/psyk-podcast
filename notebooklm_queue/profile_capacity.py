"""Profile-capacity inspection for queue-owned NotebookLM execution."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

PROFILES_FILE_ENV_VAR = "NOTEBOOKLM_PROFILES_FILE"
PROFILE_PRIORITY_ENV_VAR = "NOTEBOOKLM_PROFILE_PRIORITY"
PROFILE_STATE_FILE_ENV_VAR = "NOTEBOOKLM_PROFILE_STATE_FILE"
NOTEBOOKLM_HOME_ENV_VAR = "NOTEBOOKLM_HOME"

DEFAULT_MANUAL_WAIT_SECONDS = 900


def inspect_profile_capacity(
    *,
    profiles_file: Path | None = None,
    profile_priority: str | None = None,
    profile_state_file: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable view of usable NotebookLM profile capacity."""

    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    current_ts = current.timestamp()
    resolved_profiles_file = _resolve_profiles_file(profiles_file)
    resolved_state_file = _resolve_profile_state_file(profile_state_file)
    priority_names = _parse_profile_priority(
        profile_priority if profile_priority is not None else os.environ.get(PROFILE_PRIORITY_ENV_VAR)
    )

    base_payload: dict[str, Any] = {
        "configured": resolved_profiles_file is not None,
        "profiles_file": str(resolved_profiles_file) if resolved_profiles_file else None,
        "profile_state_file": str(resolved_state_file),
        "profile_priority": priority_names,
        "checked_at": current.replace(microsecond=0).isoformat(),
        "has_capacity": True,
        "manual_intervention_required": False,
        "profile_count": 0,
        "active_profile_count": 0,
        "usable_profiles": [],
        "blocked_profiles": [],
        "unknown_priority_profiles": [],
        "status_counts": {},
        "next_available_at": None,
        "wait_seconds": None,
        "profiles": [],
        "warnings": [],
        "errors": [],
    }

    if resolved_profiles_file is None:
        base_payload["reason"] = "profiles_file_not_configured"
        return base_payload

    profiles, profile_errors = _load_profiles(resolved_profiles_file)
    if profile_errors:
        base_payload["errors"] = profile_errors
    if not profiles:
        base_payload.update(
            {
                "has_capacity": False,
                "manual_intervention_required": True,
                "reason": "profiles_unavailable",
                "wait_seconds": _fallback_wait_seconds(),
            }
        )
        return base_payload

    state, state_warnings = _load_profile_state(resolved_state_file)
    base_payload["warnings"] = state_warnings

    ordered_names = _order_profile_names(profiles, priority_names)
    unknown_priority_profiles = [name for name in priority_names if name not in profiles]
    profile_records: list[dict[str, Any]] = []
    usable_profiles: list[str] = []
    blocked_profiles: list[str] = []
    status_counts: dict[str, int] = {}
    cooldown_untils: list[float] = []

    state_profiles = state.get("profiles") if isinstance(state.get("profiles"), dict) else {}
    for name in ordered_names:
        storage_path = profiles[name]
        entry = state_profiles.get(name) if isinstance(state_profiles.get(name), dict) else {}
        record = _profile_record(
            name=name,
            storage_path=storage_path,
            state_entry=entry,
            now_ts=current_ts,
        )
        profile_records.append(record)
        status = str(record["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "usable":
            usable_profiles.append(name)
        else:
            blocked_profiles.append(name)
        if status == "cooldown" and record.get("cooldown_until_epoch"):
            cooldown_untils.append(float(record["cooldown_until_epoch"]))

    has_capacity = bool(usable_profiles)
    next_available_ts = min(cooldown_untils) if cooldown_untils else None
    manual_required = not has_capacity and next_available_ts is None
    next_available_at = (
        datetime.fromtimestamp(next_available_ts, tz=UTC).replace(microsecond=0).isoformat()
        if next_available_ts is not None
        else None
    )
    wait_seconds = None
    if not has_capacity:
        if next_available_ts is not None:
            wait_seconds = max(int(next_available_ts - current_ts), 1)
        else:
            wait_seconds = _fallback_wait_seconds()

    base_payload.update(
        {
            "has_capacity": has_capacity,
            "manual_intervention_required": manual_required,
            "profile_count": len(profiles),
            "active_profile_count": len(ordered_names),
            "usable_profiles": usable_profiles,
            "blocked_profiles": blocked_profiles,
            "unknown_priority_profiles": unknown_priority_profiles,
            "status_counts": dict(sorted(status_counts.items())),
            "next_available_at": next_available_at,
            "wait_seconds": wait_seconds,
            "profiles": profile_records,
            "reason": "capacity_available" if has_capacity else "no_usable_profiles",
        }
    )
    return base_payload


def summarize_profile_capacity(capacity: dict[str, Any]) -> dict[str, Any]:
    """Return the compact fields operators need most often."""

    return {
        "configured": bool(capacity.get("configured")),
        "has_capacity": bool(capacity.get("has_capacity")),
        "reason": capacity.get("reason"),
        "manual_intervention_required": bool(capacity.get("manual_intervention_required")),
        "profile_count": int(capacity.get("profile_count") or 0),
        "active_profile_count": int(capacity.get("active_profile_count") or 0),
        "usable_profiles": list(capacity.get("usable_profiles") or []),
        "blocked_profiles": list(capacity.get("blocked_profiles") or []),
        "status_counts": dict(capacity.get("status_counts") or {}),
        "next_available_at": capacity.get("next_available_at"),
        "wait_seconds": capacity.get("wait_seconds"),
        "profiles_file": capacity.get("profiles_file"),
        "profile_state_file": capacity.get("profile_state_file"),
        "unknown_priority_profiles": list(capacity.get("unknown_priority_profiles") or []),
        "warnings": list(capacity.get("warnings") or []),
        "errors": list(capacity.get("errors") or []),
    }


def _resolve_profiles_file(path: Path | None) -> Path | None:
    if path is not None:
        return Path(path).expanduser().resolve()
    raw = str(os.environ.get(PROFILES_FILE_ENV_VAR) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _resolve_profile_state_file(path: Path | None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    raw = str(os.environ.get(PROFILE_STATE_FILE_ENV_VAR) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    home_override = str(os.environ.get(NOTEBOOKLM_HOME_ENV_VAR) or "").strip()
    if home_override:
        return (Path(home_override).expanduser() / "profile_state.json").resolve()
    return (Path.home() / ".notebooklm" / "profile_state.json").resolve()


def _load_profiles(path: Path) -> tuple[dict[str, Path], list[str]]:
    if not path.exists():
        return {}, [f"profiles_file_missing:{path}"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"profiles_file_invalid:{path}:{exc}"]

    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        return {}, ["profiles_file_schema_invalid"]

    profiles: dict[str, Path] = {}
    base_dir = path.parent
    for raw_name, raw_path in raw.items():
        if not isinstance(raw_name, str) or raw_path is None:
            continue
        name = raw_name.strip()
        if not name:
            continue
        profile_path = Path(str(raw_path)).expanduser()
        if not profile_path.is_absolute():
            profile_path = base_dir / profile_path
        profiles[name] = profile_path.resolve()
    if not profiles:
        return {}, ["profiles_file_empty"]
    return profiles, []


def _load_profile_state(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {"profiles": {}}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"profiles": {}}, [f"profile_state_invalid:{path}:{exc}"]
    if not isinstance(payload, dict):
        return {"profiles": {}}, ["profile_state_schema_invalid"]
    if not isinstance(payload.get("profiles"), dict):
        payload["profiles"] = {}
    return payload, []


def _profile_record(
    *,
    name: str,
    storage_path: Path,
    state_entry: dict[str, Any],
    now_ts: float,
) -> dict[str, Any]:
    cooldown_until = _coerce_float(state_entry.get("cooldown_until"), 0.0)
    last_used = _coerce_float(state_entry.get("last_used"), 0.0)
    last_error = str(state_entry.get("last_error") or "").strip()
    storage_exists = storage_path.exists()
    storage_mtime = _storage_mtime(storage_path) if storage_exists else None
    status = "usable"
    reason = "available"
    cooldown_remaining = 0

    if not storage_exists:
        status = "missing_storage"
        reason = "storage_file_missing"
    elif cooldown_until > now_ts:
        status = "cooldown"
        reason = f"{last_error or 'profile'}_cooldown"
        cooldown_remaining = max(int(cooldown_until - now_ts), 1)
    elif last_error == "auth" and last_used > 0 and (storage_mtime is None or storage_mtime <= last_used):
        status = "auth_stale"
        reason = "storage_not_refreshed_after_auth_failure"

    return {
        "name": name,
        "status": status,
        "reason": reason,
        "storage_path": str(storage_path),
        "storage_exists": storage_exists,
        "storage_mtime_epoch": storage_mtime,
        "last_used_epoch": last_used if last_used else None,
        "last_error": last_error or None,
        "success_count": int(_coerce_float(state_entry.get("success_count"), 0.0)),
        "failure_count": int(_coerce_float(state_entry.get("failure_count"), 0.0)),
        "cooldown_until_epoch": cooldown_until if cooldown_until else None,
        "cooldown_until": (
            datetime.fromtimestamp(cooldown_until, tz=UTC).replace(microsecond=0).isoformat()
            if cooldown_until
            else None
        ),
        "cooldown_remaining_seconds": cooldown_remaining,
    }


def _order_profile_names(profiles: dict[str, Path], priority_names: list[str]) -> list[str]:
    ordered: list[str] = []
    for name in priority_names:
        if name in profiles and name not in ordered:
            ordered.append(name)
    if not ordered and "default" in profiles:
        ordered.append("default")
    for name in sorted(profiles):
        if name not in ordered:
            ordered.append(name)
    return ordered


def _parse_profile_priority(raw: str | None) -> list[str]:
    names: list[str] = []
    for item in str(raw or "").split(","):
        name = item.strip()
        if name and name not in names:
            names.append(name)
    return names


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _storage_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _fallback_wait_seconds() -> int:
    raw = str(os.environ.get("NOTEBOOKLM_QUEUE_PROFILE_CAPACITY_FALLBACK_WAIT_SECONDS") or "").strip()
    if raw:
        try:
            return max(int(raw), 1)
        except ValueError:
            pass
    return DEFAULT_MANUAL_WAIT_SECONDS
