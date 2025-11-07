"""Helpers for persisting NotebookLM run metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_SUBDIR = Path("notebooklm")
RUNS_SUBDIR = BASE_SUBDIR / "runs"
DOWNLOADS_SUBDIR = BASE_SUBDIR / "downloads"


def ensure_run_dir(show_root: Path) -> Path:
    return _ensure_dir(show_root, RUNS_SUBDIR)


def ensure_download_dir(show_root: Path) -> Path:
    return _ensure_dir(show_root, DOWNLOADS_SUBDIR)


def _ensure_dir(root: Path, suffix: Path) -> Path:
    target = root / suffix
    target.mkdir(parents=True, exist_ok=True)
    return target


def timestamp_slug() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_run(show_root: Path, run_payload: Dict[str, Any], slug: Optional[str] = None) -> Path:
    slug = slug or timestamp_slug()
    run_dir = ensure_run_dir(show_root)
    path = run_dir / f"{slug}.json"
    path.write_text(json.dumps(run_payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def list_runs(show_root: Path) -> List[Path]:
    run_dir = ensure_run_dir(show_root)
    return sorted(run_dir.glob("*.json"))


def load_run(show_root: Path, slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
    run_dir = ensure_run_dir(show_root)
    target: Optional[Path]
    if slug:
        target = run_dir / f"{slug}.json"
    else:
        files = list_runs(show_root)
        target = files[-1] if files else None
    if not target or not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))
