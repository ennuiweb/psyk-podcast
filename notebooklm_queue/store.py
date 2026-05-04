"""Persistent queue store for NotebookLM jobs."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import DEFAULT_STORAGE_ROOT, QUEUE_VERSION, READY_STATES, STATE_QUEUED, TERMINAL_STATES
from .models import JobIdentity

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class QueueLockError(RuntimeError):
    """Raised when a show lock cannot be acquired."""


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_mapping(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


class QueueStore:
    """Manage durable queue state outside git."""

    def __init__(self, root: Path | None = None):
        self.root = (root or DEFAULT_STORAGE_ROOT).resolve()
        self.jobs_root = self.root / "jobs"
        self.indexes_root = self.root / "indexes"
        self.show_indexes_root = self.indexes_root / "shows"
        self.locks_root = self.root / "locks"
        self.runs_root = self.root / "runs"
        self.publish_root = self.root / "publish"
        self.dead_letter_root = self.root / "dead-letter"
        self.global_jobs_index_path = self.indexes_root / "jobs.json"

    def ensure_layout(self) -> None:
        for path in (
            self.jobs_root,
            self.show_indexes_root,
            self.locks_root,
            self.runs_root,
            self.publish_root,
            self.dead_letter_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def job_path(self, show_slug: str, job_id: str) -> Path:
        return self.jobs_root / str(show_slug).strip() / f"{job_id}.json"

    def show_index_path(self, show_slug: str) -> Path:
        return self.show_indexes_root / f"{str(show_slug).strip()}.json"

    def named_lock_path(self, lock_name: str) -> Path:
        return self.locks_root / f"{str(lock_name).strip()}.lock"

    def runs_show_root(self, show_slug: str) -> Path:
        return self.runs_root / str(show_slug).strip()

    def publish_show_root(self, show_slug: str) -> Path:
        return self.publish_root / str(show_slug).strip()

    def load_job(self, *, show_slug: str, job_id: str) -> dict[str, Any]:
        return _load_json(self.job_path(show_slug, job_id))

    def load_job_by_id(self, job_id: str) -> dict[str, Any]:
        registry = self._load_global_jobs_index()
        raw = _coerce_mapping(registry.get("jobs", {})).get(job_id)
        record = _coerce_mapping(raw)
        show_slug = str(record.get("show_slug") or "").strip()
        if not show_slug:
            return {}
        return self.load_job(show_slug=show_slug, job_id=job_id)

    def upsert_job(
        self,
        identity: JobIdentity,
        *,
        initial_state: str = STATE_QUEUED,
        actor: str = "system",
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
        priority: int = 100,
        blocked_reason: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_layout()
        now = utc_now_iso()
        job_id = identity.stable_key()
        existing = self.load_job(show_slug=identity.show_slug, job_id=job_id)
        if existing:
            changed = False
            merged_metadata = dict(_coerce_mapping(existing.get("metadata")))
            for key, value in _coerce_mapping(metadata).items():
                if merged_metadata.get(key) != value:
                    merged_metadata[key] = value
                    changed = True
            if blocked_reason is not None and existing.get("blocked_reason") != blocked_reason:
                existing["blocked_reason"] = blocked_reason
                changed = True
            if priority != int(existing.get("priority") or 100):
                existing["priority"] = int(priority)
                changed = True
            if merged_metadata != _coerce_mapping(existing.get("metadata")):
                existing["metadata"] = merged_metadata
                changed = True
            if changed:
                existing["updated_at"] = now
                self.save_job(existing)
            return existing

        payload: dict[str, Any] = {
            "version": QUEUE_VERSION,
            "job_id": job_id,
            **identity.to_payload(),
            "state": initial_state,
            "priority": int(priority),
            "attempt_count": 0,
            "created_at": now,
            "updated_at": now,
            "discovered_at": now,
            "claimed_at": None,
            "completed_at": now if initial_state in TERMINAL_STATES else None,
            "next_retry_at": None,
            "last_error": None,
            "blocked_reason": blocked_reason,
            "metadata": dict(_coerce_mapping(metadata)),
            "artifacts": {},
            "publish": {},
            "history": [
                {
                    "state": initial_state,
                    "transitioned_at": now,
                    "actor": actor,
                    "note": note,
                    "error": None,
                    "retry_at": None,
                    "details": {},
                }
            ],
        }
        self.save_job(payload)
        return payload

    def save_job(self, payload: dict[str, Any]) -> None:
        self.ensure_layout()
        show_slug = str(payload.get("show_slug") or "").strip()
        job_id = str(payload.get("job_id") or "").strip()
        if not show_slug or not job_id:
            raise ValueError("job payload must include show_slug and job_id")
        _write_json_atomic(self.job_path(show_slug, job_id), payload)
        self._update_indexes_for_job(payload)

    def transition_job(
        self,
        *,
        show_slug: str,
        job_id: str,
        state: str,
        actor: str = "system",
        note: str | None = None,
        error: str | None = None,
        retry_at: str | None = None,
        details: dict[str, Any] | None = None,
        expected_states: set[str] | None = None,
        increment_attempt: bool = False,
    ) -> dict[str, Any]:
        payload = self.load_job(show_slug=show_slug, job_id=job_id)
        if not payload:
            raise FileNotFoundError(f"Unknown job: {show_slug}/{job_id}")
        current_state = str(payload.get("state") or "").strip()
        if expected_states and current_state not in expected_states:
            raise ValueError(f"Job {job_id} is in state {current_state}, expected one of {sorted(expected_states)}")

        now = utc_now_iso()
        payload["state"] = state
        payload["updated_at"] = now
        payload["last_error"] = error
        payload["next_retry_at"] = retry_at
        if increment_attempt:
            payload["attempt_count"] = max(int(payload.get("attempt_count") or 0), 0) + 1
            payload["claimed_at"] = now
        if state in TERMINAL_STATES:
            payload["completed_at"] = now
        elif state in READY_STATES:
            payload["completed_at"] = None
        history = payload.get("history")
        if not isinstance(history, list):
            history = []
            payload["history"] = history
        history.append(
            {
                "state": state,
                "transitioned_at": now,
                "actor": actor,
                "note": note,
                "error": error,
                "retry_at": retry_at,
                "details": dict(_coerce_mapping(details)),
            }
        )
        self.save_job(payload)
        if state == "dead_letter":
            dead_letter_path = self.dead_letter_root / show_slug / f"{job_id}.json"
            _write_json_atomic(dead_letter_path, payload)
        return payload

    def list_jobs(self, *, show_slug: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        if show_slug:
            payload = _load_json(self.show_index_path(show_slug))
            entries = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if state and str(entry.get("state") or "") != state:
                    continue
                jobs.append(entry)
            return jobs

        registry = self._load_global_jobs_index()
        raw_jobs = _coerce_mapping(registry.get("jobs", {}))
        for job_id in sorted(raw_jobs.keys()):
            entry = _coerce_mapping(raw_jobs.get(job_id))
            if state and str(entry.get("state") or "") != state:
                continue
            if entry:
                jobs.append(entry)
        return jobs

    def summarize_jobs(self, *, show_slug: str | None = None) -> dict[str, Any]:
        jobs = self.list_jobs(show_slug=show_slug)
        counter = Counter()
        for job in jobs:
            counter[str(job.get("state") or "unknown")] += 1
        return {
            "root": str(self.root),
            "show_slug": show_slug,
            "job_count": len(jobs),
            "state_counts": dict(sorted(counter.items())),
        }

    def claim_next_job(
        self,
        *,
        show_slug: str,
        ready_states: set[str] | None = None,
        target_state: str,
        actor: str = "system",
    ) -> dict[str, Any] | None:
        ready = ready_states or READY_STATES
        candidates: list[dict[str, Any]] = []
        for entry in self.list_jobs(show_slug=show_slug):
            state = str(entry.get("state") or "").strip()
            if state not in ready:
                continue
            next_retry_at = str(entry.get("next_retry_at") or "").strip()
            if next_retry_at and next_retry_at > utc_now_iso():
                continue
            candidates.append(entry)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                int(item.get("priority") or 100),
                str(item.get("created_at") or ""),
                str(item.get("job_id") or ""),
            )
        )
        winner = candidates[0]
        return self.transition_job(
            show_slug=show_slug,
            job_id=str(winner["job_id"]),
            state=target_state,
            actor=actor,
            note=f"Claimed from ready states: {', '.join(sorted(ready))}",
            expected_states=ready,
            increment_attempt=True,
        )

    def retry_ready_jobs(
        self,
        *,
        show_slug: str | None = None,
        actor: str = "system",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        now = utc_now_iso()
        updated: list[dict[str, Any]] = []
        for entry in self.list_jobs(show_slug=show_slug, state="retry_scheduled"):
            next_retry_at = str(entry.get("next_retry_at") or "").strip()
            if next_retry_at and next_retry_at > now:
                continue
            updated.append(
                self.transition_job(
                    show_slug=str(entry["show_slug"]),
                    job_id=str(entry["job_id"]),
                    state=STATE_QUEUED,
                    actor=actor,
                    note="Retry window reached; re-queued automatically.",
                    expected_states={"retry_scheduled"},
                )
            )
            if limit is not None and len(updated) >= max(int(limit), 0):
                break
        return updated

    def reconcile_indexes(self, *, show_slug: str | None = None) -> dict[str, Any]:
        self.ensure_layout()
        with self.acquire_global_lock("indexes", blocking=True):
            shows = [show_slug] if show_slug else self._discover_show_slugs()
            all_jobs: dict[str, dict[str, Any]] = {}
            updated_show_count = 0
            for current_show in shows:
                if not current_show:
                    continue
                jobs = []
                for path in sorted((self.jobs_root / current_show).glob("*.json")):
                    payload = _load_json(path)
                    if not payload:
                        continue
                    jobs.append(self._job_index_entry(payload))
                    all_jobs[str(payload.get("job_id") or "")] = self._job_index_entry(payload)
                index_payload = {
                    "version": QUEUE_VERSION,
                    "show_slug": current_show,
                    "generated_at": utc_now_iso(),
                    "job_count": len(jobs),
                    "jobs": jobs,
                }
                _write_json_atomic(self.show_index_path(current_show), index_payload)
                updated_show_count += 1
            if show_slug:
                registry = self._load_global_jobs_index()
                merged = _coerce_mapping(registry.get("jobs", {}))
                for job_id, entry in all_jobs.items():
                    if job_id:
                        merged[job_id] = entry
                global_payload = {
                    "version": QUEUE_VERSION,
                    "generated_at": utc_now_iso(),
                    "job_count": len(merged),
                    "jobs": dict(sorted(merged.items())),
                }
            else:
                global_payload = {
                    "version": QUEUE_VERSION,
                    "generated_at": utc_now_iso(),
                    "job_count": len(all_jobs),
                    "jobs": dict(sorted(all_jobs.items())),
                }
            _write_json_atomic(self.global_jobs_index_path, global_payload)
            return {
                "root": str(self.root),
                "show_count": updated_show_count,
                "job_count": int(global_payload.get("job_count") or 0),
                "show_slug": show_slug,
            }

    def save_run_manifest(
        self,
        *,
        show_slug: str,
        job_id: str,
        payload: dict[str, Any],
        run_id: str,
    ) -> str:
        self.ensure_layout()
        path = self.runs_show_root(show_slug) / f"{run_id}-{job_id}.json"
        _write_json_atomic(path, payload)
        return str(path.relative_to(self.root))

    def save_publish_manifest(
        self,
        *,
        show_slug: str,
        job_id: str,
        payload: dict[str, Any],
        bundle_id: str,
    ) -> str:
        self.ensure_layout()
        path = self.publish_show_root(show_slug) / f"{bundle_id}-{job_id}.json"
        _write_json_atomic(path, payload)
        return str(path.relative_to(self.root))

    @contextmanager
    def acquire_named_lock(self, lock_name: str, *, blocking: bool = False, details: dict[str, Any] | None = None):
        self.ensure_layout()
        if fcntl is None:  # pragma: no cover
            raise QueueLockError("fcntl is unavailable on this platform")
        lock_path = self.named_lock_path(lock_name)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as exc:
                raise QueueLockError(f"Lock is already held for {lock_name}") from exc
            handle.seek(0)
            handle.truncate()
            payload = {"pid": os.getpid(), "lock_name": lock_name, "locked_at": utc_now_iso()}
            payload.update(dict(_coerce_mapping(details)))
            handle.write(json.dumps(payload))
            handle.flush()
            try:
                yield lock_path
            finally:
                handle.seek(0)
                handle.truncate()
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def acquire_show_lock(self, show_slug: str, *, blocking: bool = False):
        with self.acquire_named_lock(str(show_slug).strip(), blocking=blocking, details={"show_slug": show_slug}) as lock_path:
            yield lock_path

    @contextmanager
    def acquire_global_lock(self, scope: str = "global", *, blocking: bool = False):
        with self.acquire_named_lock(
            f"__global__-{str(scope).strip()}",
            blocking=blocking,
            details={"scope": scope},
        ) as lock_path:
            yield lock_path

    def _update_indexes_for_job(self, payload: dict[str, Any]) -> None:
        show_slug = str(payload.get("show_slug") or "").strip()
        job_id = str(payload.get("job_id") or "").strip()
        if not show_slug or not job_id:
            return
        with self.acquire_global_lock("indexes", blocking=True):
            show_index = _load_json(self.show_index_path(show_slug))
            entries = show_index.get("jobs") if isinstance(show_index.get("jobs"), list) else []
            by_id = {
                str(entry.get("job_id") or ""): entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("job_id")
            }
            by_id[job_id] = self._job_index_entry(payload)
            ordered = [by_id[key] for key in sorted(by_id.keys())]
            _write_json_atomic(
                self.show_index_path(show_slug),
                {
                    "version": QUEUE_VERSION,
                    "show_slug": show_slug,
                    "generated_at": utc_now_iso(),
                    "job_count": len(ordered),
                    "jobs": ordered,
                },
            )
            registry = self._load_global_jobs_index()
            jobs = _coerce_mapping(registry.get("jobs", {}))
            jobs[job_id] = self._job_index_entry(payload)
            _write_json_atomic(
                self.global_jobs_index_path,
                {
                    "version": QUEUE_VERSION,
                    "generated_at": utc_now_iso(),
                    "job_count": len(jobs),
                    "jobs": dict(sorted(jobs.items())),
                },
            )

    def _load_global_jobs_index(self) -> dict[str, Any]:
        return _load_json(self.global_jobs_index_path)

    def _discover_show_slugs(self) -> list[str]:
        if not self.jobs_root.exists():
            return []
        return sorted(path.name for path in self.jobs_root.iterdir() if path.is_dir())

    def _job_index_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": str(payload.get("job_id") or ""),
            "show_slug": str(payload.get("show_slug") or ""),
            "subject_slug": str(payload.get("subject_slug") or ""),
            "lecture_key": str(payload.get("lecture_key") or ""),
            "content_types": list(payload.get("content_types") or []),
            "config_hash": str(payload.get("config_hash") or ""),
            "campaign": payload.get("campaign"),
            "state": str(payload.get("state") or ""),
            "priority": int(payload.get("priority") or 100),
            "attempt_count": int(payload.get("attempt_count") or 0),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "next_retry_at": payload.get("next_retry_at"),
            "blocked_reason": payload.get("blocked_reason"),
            "last_error": payload.get("last_error"),
        }
