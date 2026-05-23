"""Refresh and validate NotebookLM profile storage for queue workers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .orchestrator import PROFILE_CAPACITY_LOCK_SCOPE
from .profile_capacity import (
    PROFILE_PRIORITY_ENV_VAR,
    _load_profile_state,
    _load_profiles,
    _order_profile_names,
    _parse_profile_priority,
    _resolve_profile_state_file,
    _resolve_profiles_file,
)
from .profile_state import profile_auth_is_unrecovered
from .store import QueueLockError, QueueStore, _write_json_atomic

RefreshCallable = Callable[[str, Path], Awaitable[None]]
ProbeCallable = Callable[[str, Path], Awaitable[None]]

AUTH_ERROR_SIGNALS = (
    "authentication expired",
    "redirected to",
    "run 'notebooklm login'",
    "storage state file not found",
    "required cookies",
    "failed to extract",
)


@dataclass(frozen=True, slots=True)
class ProfileRefreshOptions:
    profiles_file: Path | None = None
    profile_priority: str | None = None
    profile_state_file: Path | None = None
    profiles: tuple[str, ...] = ()
    min_refresh_age_seconds: int = 900
    force: bool = False
    actor: str = "operator"
    use_lock: bool = True
    blocking_lock: bool = False
    reclaim_on_auth_recovery: bool = False
    reclaim_on_recovery: bool = False
    reclaim_target_free_slots: int = 25
    reclaim_max_deletions: int = 25
    reclaim_dry_run: bool = True
    probe_after_refresh: bool = True
    probe_timeout_seconds: int = 60


def refresh_profiles(
    *,
    store: QueueStore,
    options: ProfileRefreshOptions | None = None,
    refresher: RefreshCallable | None = None,
    prober: ProbeCallable | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh configured NotebookLM profile storage and repair profile state."""

    opts = options or ProfileRefreshOptions()
    if opts.use_lock:
        try:
            with store.acquire_global_lock(
                PROFILE_CAPACITY_LOCK_SCOPE,
                blocking=opts.blocking_lock,
            ):
                return _refresh_profiles_unlocked(
                    store=store,
                    options=opts,
                    refresher=refresher or _default_refresh_profile,
                    prober=prober or _default_probe_profile,
                    now=now,
                )
        except QueueLockError as exc:
            checked_at = _now(now).replace(microsecond=0).isoformat()
            payload = {
                "checked_at": checked_at,
                "actor": opts.actor,
                "locked": False,
                "lock_scope": PROFILE_CAPACITY_LOCK_SCOPE,
                "status": "lock_held",
                "error": str(exc),
                "profiles": [],
                "summary": {"lock_held": 1},
            }
            _persist_refresh_report(store=store, payload=payload)
            return payload

    return _refresh_profiles_unlocked(
        store=store,
        options=opts,
        refresher=refresher or _default_refresh_profile,
        prober=prober or _default_probe_profile,
        now=now,
    )


def _refresh_profiles_unlocked(
    *,
    store: QueueStore,
    options: ProfileRefreshOptions,
    refresher: RefreshCallable,
    prober: ProbeCallable,
    now: datetime | None,
) -> dict[str, Any]:
    current = _now(now)
    now_ts = current.timestamp()
    profiles_file = _resolve_profiles_file(options.profiles_file)
    state_file = _resolve_profile_state_file(options.profile_state_file)
    priority = _parse_profile_priority(
        options.profile_priority
        if options.profile_priority is not None
        else os.environ.get(PROFILE_PRIORITY_ENV_VAR)
    )
    requested_profiles = [name for name in options.profiles if name]

    result: dict[str, Any] = {
        "checked_at": current.replace(microsecond=0).isoformat(),
        "actor": options.actor,
        "locked": bool(options.use_lock),
        "lock_scope": PROFILE_CAPACITY_LOCK_SCOPE if options.use_lock else None,
        "profiles_file": str(profiles_file) if profiles_file else None,
        "profile_state_file": str(state_file),
        "requested_profiles": requested_profiles,
        "min_refresh_age_seconds": max(int(options.min_refresh_age_seconds), 0),
        "force": bool(options.force),
        "status": "ok",
        "profiles": [],
        "summary": {},
        "errors": [],
    }

    if profiles_file is None:
        result["status"] = "not_configured"
        result["errors"].append("profiles_file_not_configured")
        result["summary"] = {"not_configured": 1}
        _persist_refresh_report(store=store, payload=result)
        return result

    profiles, profile_errors = _load_profiles(profiles_file)
    if profile_errors:
        result["errors"].extend(profile_errors)
    if not profiles:
        result["status"] = "profiles_unavailable"
        result["summary"] = {"profiles_unavailable": 1}
        _persist_refresh_report(store=store, payload=result)
        return result

    state, state_warnings = _load_profile_state(state_file)
    if state_warnings:
        result["warnings"] = state_warnings

    ordered_names = _order_profile_names(profiles, priority)
    if requested_profiles:
        unknown = [name for name in requested_profiles if name not in profiles]
        result["unknown_profiles"] = unknown
        ordered_names = [name for name in ordered_names if name in set(requested_profiles)]

    profile_results: list[dict[str, Any]] = []
    for name in ordered_names:
        storage_path = profiles[name]
        profile_result = _refresh_one_profile(
            name=name,
            storage_path=storage_path,
            state=state,
            refresher=refresher,
            prober=prober,
            now_ts=now_ts,
            min_refresh_age_seconds=max(int(options.min_refresh_age_seconds), 0),
            force=bool(options.force),
            probe_after_refresh=bool(options.probe_after_refresh),
            probe_timeout_seconds=max(int(options.probe_timeout_seconds), 1),
        )
        profile_results.append(profile_result)

    state["updated_at"] = current.replace(microsecond=0).isoformat()
    state["updated_by"] = "notebooklm_queue.refresh_profiles"
    _write_json_atomic(state_file, state)

    reclaim_reports = []
    if options.reclaim_on_recovery or options.reclaim_on_auth_recovery:
        actor_suffix = "profile-recovery" if options.reclaim_on_recovery else "auth-recovery"
        for profile in _profiles_recovered_for_reclaim(
            profile_results,
            include_cooldown=bool(options.reclaim_on_recovery),
        ):
            reclaim_reports.append(
                _reclaim_recovered_profile(
                    store=store,
                    options=options,
                    profiles_file=profiles_file,
                    profile_state_file=state_file,
                    profile=profile,
                    actor_suffix=actor_suffix,
                )
            )

    result["profiles"] = profile_results
    if reclaim_reports:
        result["reclaim_reports"] = reclaim_reports
    result["summary"] = _summarize_results(profile_results)
    if any(item["status"] == "failed" for item in profile_results):
        result["status"] = "partial_failure"
    if profile_results and all(item["status"] == "failed" for item in profile_results):
        result["status"] = "failed"
    _persist_refresh_report(store=store, payload=result)
    return result


def _refresh_one_profile(
    *,
    name: str,
    storage_path: Path,
    state: dict[str, Any],
    refresher: RefreshCallable,
    prober: ProbeCallable,
    now_ts: float,
    min_refresh_age_seconds: int,
    force: bool,
    probe_after_refresh: bool,
    probe_timeout_seconds: int,
) -> dict[str, Any]:
    entry = _profile_state_entry(state, name)
    storage_exists = storage_path.exists()
    base = {
        "name": name,
        "storage_path": str(storage_path),
        "storage_exists": storage_exists,
    }
    if not storage_exists:
        _record_refresh_failure(
            entry,
            now_ts=now_ts,
            error_type="missing_storage",
            error=f"storage file missing: {storage_path}",
            mark_auth_error=True,
        )
        return {
            **base,
            "status": "failed",
            "error_type": "missing_storage",
            "error": f"storage file missing: {storage_path}",
        }

    if not force and profile_auth_is_unrecovered(
        state_entry=entry,
        storage_path=storage_path,
    ):
        return {
            **base,
            "status": "skipped_auth_stale",
            "reason": "storage_not_updated_after_auth_failure",
            "storage_mtime_epoch": _storage_mtime(storage_path),
        }

    last_refreshed = _coerce_float(entry.get("last_refreshed"), 0.0)
    if (
        not force
        and min_refresh_age_seconds > 0
        and last_refreshed > 0
        and now_ts - last_refreshed < min_refresh_age_seconds
        and str(entry.get("last_error") or "").strip() != "auth"
    ):
        return {
            **base,
            "status": "skipped_recent",
            "last_refreshed_epoch": last_refreshed,
        }

    before_mtime = _storage_mtime(storage_path)
    previous_error = str(entry.get("last_error") or "").strip() or None
    previous_cooldown_until = _coerce_float(entry.get("cooldown_until"), 0.0)
    try:
        _run_async(refresher(name, storage_path))
    except Exception as exc:  # noqa: BLE001 - operator report needs the exact failure.
        error_type = _classify_refresh_error(exc)
        _record_refresh_failure(
            entry,
            now_ts=now_ts,
            error_type=error_type,
            error=str(exc),
            mark_auth_error=error_type == "auth",
        )
        return {
            **base,
            "status": "failed",
            "error_type": error_type,
            "error": str(exc),
            "storage_mtime_epoch": before_mtime,
        }

    after_mtime = _storage_mtime(storage_path)
    _record_keepalive_success(entry, now_ts=now_ts)
    probe_payload: dict[str, Any] = {}
    if probe_after_refresh:
        try:
            if prober is _default_probe_profile:
                _run_async(
                    _default_probe_profile(
                        name,
                        storage_path,
                        timeout_seconds=probe_timeout_seconds,
                    )
                )
            else:
                _run_async(prober(name, storage_path))
        except Exception as exc:  # noqa: BLE001 - operator report needs the exact failure.
            error_type = _classify_refresh_error(exc)
            _record_probe_failure(
                entry,
                now_ts=now_ts,
                error_type=error_type,
                error=str(exc),
                mark_auth_error=error_type == "auth",
            )
            return {
                **base,
                "status": "failed",
                "phase": "probe",
                "error_type": error_type,
                "error": str(exc),
                "storage_mtime_before_epoch": before_mtime,
                "storage_mtime_after_epoch": after_mtime,
            }
        _record_probe_success(entry, now_ts=now_ts)
        probe_payload["probe_status"] = "success"
    else:
        _record_refresh_success(entry, now_ts=now_ts)
        probe_payload["probe_status"] = "skipped"
    return {
        **base,
        "status": "refreshed",
        "storage_mtime_before_epoch": before_mtime,
        "storage_mtime_after_epoch": after_mtime,
        **probe_payload,
        "recovered_from_error": previous_error,
        "previous_cooldown_until_epoch": previous_cooldown_until if previous_cooldown_until else None,
        "recovered_from_cooldown": (
            previous_error not in (None, "auth")
            and previous_cooldown_until > 0
            and previous_cooldown_until <= now_ts
        ),
    }


def _profiles_recovered_for_reclaim(
    profile_results: list[dict[str, Any]],
    *,
    include_cooldown: bool,
) -> list[str]:
    profiles: list[str] = []
    for item in profile_results:
        if item.get("status") != "refreshed":
            continue
        recovered_from_auth = item.get("recovered_from_error") == "auth"
        recovered_from_cooldown = include_cooldown and bool(item.get("recovered_from_cooldown"))
        if recovered_from_auth or recovered_from_cooldown:
            profiles.append(str(item["name"]))
    return profiles


def _reclaim_recovered_profile(
    *,
    store: QueueStore,
    options: ProfileRefreshOptions,
    profiles_file: Path,
    profile_state_file: Path,
    profile: str,
    actor_suffix: str,
) -> dict[str, Any]:
    from .notebook_reclaim import NotebookReclaimOptions, reclaim_notebooks

    return reclaim_notebooks(
        store=store,
        options=NotebookReclaimOptions(
            profiles_file=profiles_file,
            profile_priority=options.profile_priority,
            profile_state_file=profile_state_file,
            profiles=(profile,),
            target_free_slots=int(options.reclaim_target_free_slots),
            max_deletions=int(options.reclaim_max_deletions),
            dry_run=bool(options.reclaim_dry_run),
            actor=f"{options.actor}:{actor_suffix}",
            use_lock=False,
        ),
    )


async def _default_refresh_profile(_name: str, storage_path: Path) -> None:
    previous_auth_json = os.environ.pop("NOTEBOOKLM_AUTH_JSON", None)
    try:
        from notebooklm.auth import fetch_tokens_with_domains

        await fetch_tokens_with_domains(storage_path, profile=None)
    finally:
        if previous_auth_json is not None:
            os.environ["NOTEBOOKLM_AUTH_JSON"] = previous_auth_json


async def _default_probe_profile(
    _name: str,
    storage_path: Path,
    *,
    timeout_seconds: int | None = None,
) -> None:
    notebooklm_bin = str(os.environ.get("NOTEBOOKLM_PROFILE_REFRESH_NOTEBOOKLM_BIN") or "").strip()
    if not notebooklm_bin:
        notebooklm_bin = str(Path(sys.executable).with_name("notebooklm"))
    timeout = timeout_seconds
    if timeout is None:
        timeout = _int_env("NOTEBOOKLM_PROFILE_REFRESH_PROBE_TIMEOUT_SECONDS", 60)
    cmd = [notebooklm_bin, "--storage", str(storage_path), "list", "--json"]
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=max(timeout, 1),
        check=False,
    )
    if result.returncode != 0:
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        raise RuntimeError(output or f"profile probe failed with exit code {result.returncode}")


def _record_refresh_success(entry: dict[str, Any], *, now_ts: float) -> None:
    entry["last_refreshed"] = now_ts
    entry["last_refresh_status"] = "success"
    entry["last_refresh_error"] = None
    entry["refresh_success_count"] = int(entry.get("refresh_success_count") or 0) + 1
    entry["last_refresh_error_type"] = None
    if str(entry.get("last_error") or "").strip() == "auth":
        entry["last_error"] = None
        entry["cooldown_until"] = 0


def _record_keepalive_success(entry: dict[str, Any], *, now_ts: float) -> None:
    entry["last_refreshed"] = now_ts
    entry["last_refresh_status"] = "success"
    entry["last_refresh_error"] = None
    entry["refresh_success_count"] = int(entry.get("refresh_success_count") or 0) + 1
    entry["last_refresh_error_type"] = None


def _record_probe_success(entry: dict[str, Any], *, now_ts: float) -> None:
    entry["last_probe_attempt"] = now_ts
    entry["last_probe_success"] = now_ts
    entry["last_probe_status"] = "success"
    entry["last_probe_error"] = None
    entry["last_probe_error_type"] = None
    entry["probe_success_count"] = int(entry.get("probe_success_count") or 0) + 1
    if str(entry.get("last_error") or "").strip() == "auth":
        entry["last_error"] = None
        entry["cooldown_until"] = 0


def _record_probe_failure(
    entry: dict[str, Any],
    *,
    now_ts: float,
    error_type: str,
    error: str,
    mark_auth_error: bool,
) -> None:
    entry["last_probe_attempt"] = now_ts
    entry["last_probe_status"] = "failed"
    entry["last_probe_error_type"] = error_type
    entry["last_probe_error"] = error
    entry["probe_failure_count"] = int(entry.get("probe_failure_count") or 0) + 1
    if mark_auth_error:
        entry["last_error"] = "auth"
        entry["last_used"] = max(_coerce_float(entry.get("last_used"), 0.0), now_ts)


def _record_refresh_failure(
    entry: dict[str, Any],
    *,
    now_ts: float,
    error_type: str,
    error: str,
    mark_auth_error: bool,
) -> None:
    entry["last_refresh_attempt"] = now_ts
    entry["last_refresh_status"] = "failed"
    entry["last_refresh_error_type"] = error_type
    entry["last_refresh_error"] = error
    entry["refresh_failure_count"] = int(entry.get("refresh_failure_count") or 0) + 1
    if mark_auth_error:
        entry["last_error"] = "auth"
        entry["last_used"] = max(_coerce_float(entry.get("last_used"), 0.0), now_ts)


def _profile_state_entry(state: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = state.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        state["profiles"] = profiles
    entry = profiles.get(profile)
    if not isinstance(entry, dict):
        entry = {}
        profiles[profile] = entry
    return entry


def _classify_refresh_error(exc: Exception) -> str:
    message = str(exc).lower()
    if any(signal in message for signal in AUTH_ERROR_SIGNALS):
        return "auth"
    if "429" in message or "rate limit" in message:
        return "rate_limit"
    if "storage file missing" in message or isinstance(exc, FileNotFoundError):
        return "missing_storage"
    return "transient"


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in results:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return dict(sorted(summary.items()))


def _persist_refresh_report(*, store: QueueStore, payload: dict[str, Any]) -> None:
    store.ensure_layout()
    report_root = store.root / "profile-refresh"
    report_root.mkdir(parents=True, exist_ok=True)
    checked_at = str(payload.get("checked_at") or _now(None).isoformat())
    stamp = (
        checked_at.replace(":", "")
        .replace("-", "")
        .replace("+", "Z")
        .replace(".", "")
    )
    report_path = report_root / f"{stamp}.json"
    latest_path = report_root / "latest.json"
    payload["report_path"] = str(report_path)
    _write_json_atomic(report_path, payload)
    _write_json_atomic(latest_path, payload)

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


def _now(value: datetime | None) -> datetime:
    return (value or datetime.now(tz=UTC)).astimezone(UTC)


def _run_async(awaitable: Awaitable[None]) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(awaitable)
        return
    raise RuntimeError("refresh_profiles cannot run inside an active event loop")


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
