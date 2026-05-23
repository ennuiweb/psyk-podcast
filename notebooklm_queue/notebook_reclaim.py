"""Bounded NotebookLM notebook-capacity reclaim for queue profiles."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
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
from .store import QueueLockError, QueueStore, _write_json_atomic

ClientFactory = Callable[[Path], Awaitable[Any]]

DEFAULT_TARGET_FREE_SLOTS = 25
DEFAULT_MAX_DELETIONS = 25
DEFAULT_REQUEST_LOG_ROOTS = (
    "notebooklm-podcast-auto/personlighedspsykologi/output",
    "notebooklm-podcast-auto/personlighedspsykologi-da/output",
    "notebooklm-podcast-auto/bioneuro/output",
)


@dataclass(frozen=True, slots=True)
class NotebookReclaimOptions:
    profiles_file: Path | None = None
    profile_priority: str | None = None
    profile_state_file: Path | None = None
    profiles: tuple[str, ...] = ()
    repo_root: Path = field(default_factory=Path.cwd)
    request_log_roots: tuple[Path, ...] = ()
    target_free_slots: int = DEFAULT_TARGET_FREE_SLOTS
    max_deletions: int = DEFAULT_MAX_DELETIONS
    dry_run: bool = True
    actor: str = "operator"
    use_lock: bool = True
    blocking_lock: bool = False


def reclaim_notebooks(
    *,
    store: QueueStore,
    options: NotebookReclaimOptions | None = None,
    client_factory: ClientFactory | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete oldest safe owned notebooks until configured headroom exists."""

    opts = options or NotebookReclaimOptions()
    if opts.use_lock:
        try:
            with store.acquire_global_lock(
                PROFILE_CAPACITY_LOCK_SCOPE,
                blocking=opts.blocking_lock,
            ):
                return _reclaim_notebooks_unlocked(
                    store=store,
                    options=opts,
                    client_factory=client_factory or _default_client_factory,
                    now=now,
                )
        except QueueLockError as exc:
            checked_at = _now(now).replace(microsecond=0).isoformat()
            payload = {
                "checked_at": checked_at,
                "actor": opts.actor,
                "locked": False,
                "lock_scope": PROFILE_CAPACITY_LOCK_SCOPE,
                "dry_run": bool(opts.dry_run),
                "status": "lock_held",
                "error": str(exc),
                "profiles": [],
                "summary": {"lock_held": 1},
            }
            _persist_reclaim_report(store=store, payload=payload)
            return payload

    return _reclaim_notebooks_unlocked(
        store=store,
        options=opts,
        client_factory=client_factory or _default_client_factory,
        now=now,
    )


def _reclaim_notebooks_unlocked(
    *,
    store: QueueStore,
    options: NotebookReclaimOptions,
    client_factory: ClientFactory,
    now: datetime | None,
) -> dict[str, Any]:
    current = _now(now)
    profiles_file = _resolve_profiles_file(options.profiles_file)
    state_file = _resolve_profile_state_file(options.profile_state_file)
    priority = _parse_profile_priority(
        options.profile_priority
        if options.profile_priority is not None
        else os.environ.get(PROFILE_PRIORITY_ENV_VAR)
    )
    requested_profiles = [name for name in options.profiles if name]
    repo_root = Path(options.repo_root).expanduser().resolve()
    request_log_roots = _request_log_roots(repo_root, options.request_log_roots)

    result: dict[str, Any] = {
        "checked_at": current.replace(microsecond=0).isoformat(),
        "actor": options.actor,
        "locked": bool(options.use_lock),
        "lock_scope": PROFILE_CAPACITY_LOCK_SCOPE if options.use_lock else None,
        "dry_run": bool(options.dry_run),
        "profiles_file": str(profiles_file) if profiles_file else None,
        "profile_state_file": str(state_file),
        "requested_profiles": requested_profiles,
        "repo_root": str(repo_root),
        "request_log_roots": [str(path) for path in request_log_roots],
        "target_free_slots": max(int(options.target_free_slots), 0),
        "max_deletions": max(int(options.max_deletions), 0),
        "status": "ok",
        "profiles": [],
        "summary": {},
        "errors": [],
    }

    if profiles_file is None:
        result["status"] = "not_configured"
        result["errors"].append("profiles_file_not_configured")
        result["summary"] = {"not_configured": 1}
        _persist_reclaim_report(store=store, payload=result)
        return result

    profiles, profile_errors = _load_profiles(profiles_file)
    if profile_errors:
        result["errors"].extend(profile_errors)
    if not profiles:
        result["status"] = "profiles_unavailable"
        result["summary"] = {"profiles_unavailable": 1}
        _persist_reclaim_report(store=store, payload=result)
        return result

    state, state_warnings = _load_profile_state(state_file)
    if state_warnings:
        result["warnings"] = state_warnings

    ordered_names = _order_profile_names(profiles, priority)
    if requested_profiles:
        unknown = [name for name in requested_profiles if name not in profiles]
        result["unknown_profiles"] = unknown
        requested = set(requested_profiles)
        ordered_names = [name for name in ordered_names if name in requested]

    profile_results: list[dict[str, Any]] = []
    for name in ordered_names:
        storage_path = profiles[name]
        profile_result = _run_async(
            _reclaim_one_profile(
                name=name,
                storage_path=storage_path,
                client_factory=client_factory,
                request_log_roots=request_log_roots,
                target_free_slots=max(int(options.target_free_slots), 0),
                max_deletions=max(int(options.max_deletions), 0),
                dry_run=bool(options.dry_run),
            )
        )
        profile_results.append(profile_result)
        _record_profile_reclaim_result(
            state,
            name,
            profile_result=profile_result,
            now=current,
        )

    state["updated_at"] = current.replace(microsecond=0).isoformat()
    state["updated_by"] = "notebooklm_queue.reclaim_notebooks"
    _write_json_atomic(state_file, state)

    result["profiles"] = profile_results
    result["summary"] = _summarize_results(profile_results)
    if any(item["status"] == "failed" for item in profile_results):
        result["status"] = "partial_failure"
    if profile_results and all(item["status"] == "failed" for item in profile_results):
        result["status"] = "failed"
    _persist_reclaim_report(store=store, payload=result)
    return result


async def _reclaim_one_profile(
    *,
    name: str,
    storage_path: Path,
    client_factory: ClientFactory,
    request_log_roots: tuple[Path, ...],
    target_free_slots: int,
    max_deletions: int,
    dry_run: bool,
) -> dict[str, Any]:
    base = {
        "name": name,
        "storage_path": str(storage_path),
        "storage_exists": storage_path.exists(),
        "dry_run": dry_run,
    }
    if not storage_path.exists():
        return {
            **base,
            "status": "failed",
            "error_type": "missing_storage",
            "error": f"storage file missing: {storage_path}",
        }
    if max_deletions <= 0 or target_free_slots <= 0:
        return {
            **base,
            "status": "skipped_disabled",
            "owned_count_before": None,
            "limit": None,
            "deleted_count": 0,
            "skipped_count": 0,
        }

    try:
        client_context = await client_factory(storage_path)
        async with client_context as client:
            notebooks = await client.notebooks.list()
            limit = await _account_notebook_limit(client)
            owned = [notebook for notebook in notebooks if getattr(notebook, "is_owner", True)]
            owned_count = len(owned)
            free_slots_before = limit - owned_count if limit is not None else None
            base.update(
                {
                    "owned_count_before": owned_count,
                    "limit": limit,
                    "free_slots_before": free_slots_before,
                }
            )
            if limit is None:
                return {
                    **base,
                    "status": "skipped_limit_unknown",
                    "deleted_count": 0,
                    "skipped_count": 0,
                }
            if free_slots_before is not None and free_slots_before >= target_free_slots:
                return {
                    **base,
                    "status": "skipped_has_headroom",
                    "deleted_count": 0,
                    "skipped_count": 0,
                    "owned_count_after": owned_count,
                    "free_slots_after": free_slots_before,
                }

            deletion_budget = min(max_deletions, target_free_slots - free_slots_before)
            deleted: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for candidate in sorted(owned, key=_notebook_sort_key):
                if len(deleted) >= deletion_budget:
                    break
                blocker = await _reclaim_blocker_for_notebook(
                    client=client,
                    notebook_id=str(getattr(candidate, "id", "") or ""),
                    request_log_roots=request_log_roots,
                )
                if blocker:
                    skipped.append(_notebook_payload(candidate, reason=blocker))
                    continue
                payload = _notebook_payload(candidate)
                if not dry_run:
                    await client.notebooks.delete(candidate.id)
                deleted.append(payload)

            owned_after = owned_count - (0 if dry_run else len(deleted))
            free_after = limit - owned_after
            status = "dry_run" if dry_run else "reclaimed"
            if not dry_run and not deleted and skipped:
                status = "blocked_no_safe_candidates"
            return {
                **base,
                "status": status,
                "deleted_count": len(deleted),
                "skipped_count": len(skipped),
                "deleted_notebooks": deleted,
                "skipped_notebooks": skipped,
                "owned_count_after": owned_after,
                "free_slots_after": free_after,
                "target_reached": free_after >= target_free_slots if not dry_run else None,
            }
    except Exception as exc:  # noqa: BLE001 - report exact operational failure.
        return {
            **base,
            "status": "failed",
            "error_type": "reclaim_error",
            "error": str(exc),
        }


async def _default_client_factory(storage_path: Path) -> Any:
    from notebooklm import NotebookLMClient

    return await NotebookLMClient.from_storage(storage_path)


async def _account_notebook_limit(client: Any) -> int | None:
    getter = getattr(client.notebooks, "_get_account_limits", None)
    if not callable(getter):
        return None
    limits = await getter()
    value = getattr(limits, "notebook_limit", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _reclaim_blocker_for_notebook(
    *,
    client: Any,
    notebook_id: str,
    request_log_roots: tuple[Path, ...],
) -> str | None:
    if not notebook_id:
        return "missing notebook id"

    artifacts_api = getattr(client, "artifacts", None)
    if artifacts_api is not None:
        try:
            artifacts = await artifacts_api.list(notebook_id)
        except Exception as exc:  # noqa: BLE001 - conservative deletion guard.
            return f"could not inspect artifacts safely ({exc})"
        pending = [
            artifact
            for artifact in artifacts
            if getattr(artifact, "is_processing", False) or getattr(artifact, "is_pending", False)
        ]
        if pending:
            labels = ", ".join(
                f"{getattr(artifact, 'title', None) or getattr(artifact, 'id', '')} "
                f"[{getattr(artifact, 'status_str', '')}]"
                for artifact in pending[:3]
            )
            return f"pending artifacts still exist: {labels}"

    undownloaded_logs = _find_undownloaded_request_logs(request_log_roots, notebook_id)
    if undownloaded_logs:
        sample = ", ".join(str(path) for path in undownloaded_logs[:3])
        return f"local request logs still point to missing outputs: {sample}"
    return None


def _find_undownloaded_request_logs(search_roots: tuple[Path, ...], notebook_id: str) -> list[Path]:
    matches: list[Path] = []
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for log_path in search_root.rglob("*.request.json"):
            try:
                payload = json.loads(log_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("notebook_id") or "").strip() != notebook_id:
                continue
            output_value = str(payload.get("output_path") or "").strip()
            if not output_value:
                matches.append(log_path)
                continue
            output_path = Path(output_value).expanduser()
            if not output_path.is_absolute():
                output_path = (search_root / output_path).resolve()
            if not output_path.exists():
                matches.append(log_path)
                continue
            try:
                if output_path.is_file() and output_path.stat().st_size > 0:
                    continue
            except OSError:
                pass
            matches.append(log_path)
    return matches


def _request_log_roots(repo_root: Path, configured: tuple[Path, ...]) -> tuple[Path, ...]:
    roots = configured or tuple(Path(value) for value in DEFAULT_REQUEST_LOG_ROOTS)
    resolved: list[Path] = []
    for root in roots:
        path = Path(root).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        resolved.append(path.resolve())
    return tuple(resolved)


def _notebook_sort_key(notebook: Any) -> tuple[datetime, str, str]:
    created_at = getattr(notebook, "created_at", None)
    normalized = created_at if isinstance(created_at, datetime) else datetime.max
    return (normalized, str(getattr(notebook, "title", "") or ""), str(getattr(notebook, "id", "") or ""))


def _notebook_payload(notebook: Any, *, reason: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(getattr(notebook, "id", "") or ""),
        "title": str(getattr(notebook, "title", "") or ""),
    }
    created_at = getattr(notebook, "created_at", None)
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.replace(microsecond=0).isoformat()
    if reason:
        payload["reason"] = reason
    return payload


def _record_profile_reclaim_result(
    state: dict[str, Any],
    profile: str,
    *,
    profile_result: dict[str, Any],
    now: datetime,
) -> None:
    profiles = state.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        state["profiles"] = profiles
    entry = profiles.get(profile)
    if not isinstance(entry, dict):
        entry = {}
        profiles[profile] = entry
    entry["last_reclaim_attempt"] = now.timestamp()
    entry["last_reclaim_status"] = profile_result.get("status")
    entry["last_reclaim_deleted_count"] = int(profile_result.get("deleted_count") or 0)
    entry["last_reclaim_dry_run"] = bool(profile_result.get("dry_run"))
    if profile_result.get("status") == "failed":
        entry["last_reclaim_error"] = profile_result.get("error")
    else:
        entry["last_reclaim_error"] = None


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in results:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return dict(sorted(summary.items()))


def _persist_reclaim_report(*, store: QueueStore, payload: dict[str, Any]) -> None:
    store.ensure_layout()
    report_root = store.root / "notebook-reclaim"
    report_root.mkdir(parents=True, exist_ok=True)
    checked_at = str(payload.get("checked_at") or _now(None).isoformat())
    stamp = checked_at.replace(":", "").replace("-", "").replace("+", "Z").replace(".", "")
    suffix = _report_suffix(payload)
    report_path = _unique_report_path(report_root / f"{stamp}-{suffix}.json")
    latest_path = report_root / "latest.json"
    payload["report_path"] = str(report_path)
    _write_json_atomic(report_path, payload)
    _write_json_atomic(latest_path, payload)


def _report_suffix(payload: dict[str, Any]) -> str:
    requested = [str(item).strip() for item in payload.get("requested_profiles") or [] if str(item).strip()]
    if not requested:
        requested = ["all"]
    raw = "-".join(requested[:3])
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in raw)[:120] or "profiles"


def _unique_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}.{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to allocate notebook reclaim report path for {path}")


def _now(value: datetime | None) -> datetime:
    return (value or datetime.now(tz=UTC)).astimezone(UTC)


def _run_async(awaitable: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("reclaim_notebooks cannot run inside an active event loop")
