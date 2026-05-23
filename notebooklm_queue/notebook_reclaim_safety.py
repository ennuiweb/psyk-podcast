"""Shared NotebookLM notebook deletion safety checks."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


async def reclaim_blocker_for_notebook(
    *,
    client: Any,
    notebook_id: str,
    request_log_roots: tuple[Path, ...],
) -> str | None:
    """Return a human-readable reason when a notebook should not be deleted."""

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

    undownloaded_logs = find_undownloaded_request_logs(request_log_roots, notebook_id)
    if undownloaded_logs:
        sample = ", ".join(str(path) for path in undownloaded_logs[:3])
        return f"local request logs still point to missing outputs: {sample}"
    return None


def find_undownloaded_request_logs(search_roots: tuple[Path, ...], notebook_id: str) -> list[Path]:
    """Find local request logs for a notebook whose target output is absent or empty."""

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


def notebook_sort_key(notebook: Any) -> tuple[datetime, str, str]:
    """Sort oldest notebooks first with deterministic tie-breakers."""

    created_at = getattr(notebook, "created_at", None)
    normalized = created_at if isinstance(created_at, datetime) else datetime.max
    return (normalized, str(getattr(notebook, "title", "") or ""), str(getattr(notebook, "id", "") or ""))


def notebook_payload(notebook: Any, *, reason: str | None = None) -> dict[str, Any]:
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
