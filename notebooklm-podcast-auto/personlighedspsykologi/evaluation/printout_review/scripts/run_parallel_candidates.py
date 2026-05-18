#!/usr/bin/env python3
"""Run printout candidate generation in a resumable parallel pool."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_candidates
from notebooklm_queue import personlighedspsykologi_printouts as printout_engine
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

PARALLEL_STATE_NAME = "parallel-run.json"
PARALLEL_WORK_DIRNAME = "parallel"
RUNNER_SCHEMA_VERSION = 1
TERMINATION_GRACE_SECONDS = 5
COMPLETE_STATUSES = {"written", "rerendered_existing", "skipped_existing"}
TERMINAL_ENTRY_STATUSES = {"written", "error", "cancelled"}
STATE_LOCK = threading.Lock()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _resolve(path_value: str | Path, *, base: Path | None = None) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return ((base or REPO_ROOT) / path).resolve()


def _state_path_for_manifest(manifest_path: Path) -> Path:
    return manifest_path.parent / PARALLEL_STATE_NAME


def _parallel_work_dir_for_manifest(manifest_path: Path) -> Path:
    return manifest_path.parent / PARALLEL_WORK_DIRNAME


def _preferred_python_path() -> Path:
    preferred = REPO_ROOT / ".venv" / "bin" / "python"
    return preferred.resolve() if preferred.exists() else Path(sys.executable).resolve()


def _candidate_output_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    value = str(manifest.get("candidate_output_root") or "").strip()
    if value:
        return Path(value).expanduser().resolve()
    run_dir = manifest_path.parent
    evaluation_root = run_dir.parents[1]
    return (evaluation_root / printout_engine.REVIEW_OUTPUT_DIRNAME).resolve()


def _expected_stems(*, include_exam_bridge: bool) -> tuple[str, ...]:
    if include_exam_bridge:
        return printout_engine.V3_RENDER_STEMS
    return tuple(stem for stem in printout_engine.V3_RENDER_STEMS if stem != "05-exam-bridge")


def _semantic_config_for_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "master_manifest_path": str(state.get("master_manifest_path") or ""),
        "candidate_output_root": str(state.get("candidate_output_root") or ""),
        "provider": str(state.get("provider") or ""),
        "model": str(state.get("model") or ""),
        "render_pdf": bool(state.get("render_pdf", True)),
        "include_exam_bridge": bool(state.get("include_exam_bridge", False)),
        "force": bool(state.get("force", False)),
        "rerender_existing": bool(state.get("rerender_existing", False)),
        "source_ids": sorted(str(item) for item in state.get("source_ids", [])),
    }


def _semantic_config_hash(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_entry_from_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        manifest = _read_json(manifest_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        return {}
    entry = entries[0]
    return entry if isinstance(entry, dict) else {}


def _artifact_json_path(candidate_output_root: Path, source_id: str, *, provider: str, model: str) -> Path:
    scoped = printout_engine.artifact_json_path_for_source_id(
        candidate_output_root,
        source_id=source_id,
        provider=provider,
        model=model,
    )
    if scoped.exists():
        return scoped
    return printout_engine.artifact_json_path_for_source_id(candidate_output_root, source_id=source_id)


def _expected_pdf_paths(
    *,
    candidate_output_root: Path,
    provider: str,
    model: str,
    source_id: str,
    include_exam_bridge: bool,
) -> list[Path]:
    artifact = {
        "generator": {"provider": provider, "model": model},
        "source": {"source_id": source_id},
    }
    return [
        candidate_output_root / printout_engine._review_pdf_filename(artifact, stem)
        for stem in _expected_stems(include_exam_bridge=include_exam_bridge)
    ]


def verify_source_artifacts(
    *,
    candidate_output_root: Path,
    provider: str,
    model: str,
    source_id: str,
    source_manifest_path: Path,
    render_pdf: bool,
    include_exam_bridge: bool,
) -> dict[str, Any]:
    entry = _candidate_entry_from_manifest(source_manifest_path)
    candidate = entry.get("candidate") if isinstance(entry.get("candidate"), dict) else {}
    manifest_status = str(candidate.get("status") or "missing_manifest")
    json_path = _artifact_json_path(candidate_output_root, source_id, provider=provider, model=model)
    expected_pdf_paths = _expected_pdf_paths(
        candidate_output_root=candidate_output_root,
        provider=provider,
        model=model,
        source_id=source_id,
        include_exam_bridge=include_exam_bridge,
    )
    present_pdf_paths = [path for path in expected_pdf_paths if path.exists() and path.is_file() and path.stat().st_size > 0]
    missing_pdf_paths = [path for path in expected_pdf_paths if path not in present_pdf_paths]
    artifact_exists = json_path.exists() and json_path.is_file()
    if render_pdf:
        complete = artifact_exists and manifest_status in COMPLETE_STATUSES and not missing_pdf_paths
    else:
        complete = artifact_exists and manifest_status in COMPLETE_STATUSES
    return {
        "source_id": source_id,
        "status": "complete" if complete else "incomplete",
        "manifest_status": manifest_status,
        "artifact_json_path": str(json_path),
        "artifact_json_exists": artifact_exists,
        "expected_pdf_count": len(expected_pdf_paths) if render_pdf else 0,
        "present_pdf_count": len(present_pdf_paths) if render_pdf else 0,
        "missing_pdf_paths": [str(path) for path in missing_pdf_paths] if render_pdf else [],
        "manifest_path": str(source_manifest_path),
        "error": str(candidate.get("error") or ""),
        "attempt_count": int(candidate.get("attempt_count") or 0),
        "transient_error_count": int(candidate.get("transient_error_count") or 0),
    }


def _selected_master_entries(master_manifest: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    selected = {item.strip() for item in source_ids if item.strip()}
    entries = [entry for entry in master_manifest.get("entries", []) if isinstance(entry, dict)]
    if selected:
        entries = [entry for entry in entries if str(entry.get("source_id") or "").strip() in selected]
    if not entries:
        raise SystemExit("no manifest entries matched the selected source ids")
    return entries


def _reset_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(entry)
    source_id = str(clone.get("source_id") or "").strip()
    candidate = clone.setdefault("candidate", {})
    candidate.update(
        {
            "status": "pending",
            "error": "",
            "output_dir": "",
            "json_path": "",
            "markdown_paths": [],
            "pdf_paths": [],
            "source_id": source_id,
            "started_at": "",
            "finished_at": "",
            "duration_seconds": None,
            "attempt_count": 0,
            "transient_error_count": 0,
            "last_transient_error": "",
        }
    )
    candidate["prompt_capture_paths"] = {
        "system": f"prompts/{source_id}.system.txt",
        "user": f"prompts/{source_id}.user.txt",
    }
    return clone


def _write_source_manifest(
    *,
    master_manifest_path: Path,
    master_manifest: dict[str, Any],
    source_entry: dict[str, Any],
    candidate_output_root: Path,
) -> Path:
    source_id = str(source_entry.get("source_id") or "").strip()
    if not source_id:
        raise SystemExit("manifest entry is missing source_id")
    source_run_dir = _parallel_work_dir_for_manifest(master_manifest_path) / source_id
    source_manifest_path = source_run_dir / "manifest.json"
    source_manifest = copy.deepcopy(master_manifest)
    source_manifest["schema_version"] = int(source_manifest.get("schema_version") or 1)
    source_manifest["run_name"] = f"{master_manifest.get('run_name') or master_manifest_path.parent.name}/parallel/{source_id}"
    source_manifest["updated_at"] = utc_now_iso()
    source_manifest["status"] = "planned"
    source_manifest["candidate_output_root"] = str(candidate_output_root)
    source_manifest["selection"] = {
        **(source_manifest.get("selection") if isinstance(source_manifest.get("selection"), dict) else {}),
        "source_ids": [source_id],
    }
    source_manifest["summary"] = {
        "source_count": 1,
        "written_count": 0,
        "rerendered_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "pending_count": 1,
    }
    source_manifest["entries"] = [_reset_candidate(source_entry)]
    _write_json(source_manifest_path, source_manifest)
    notes_path = source_run_dir / "notes" / f"{source_id}.md"
    if not notes_path.exists():
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(f"# {source_id}\n\n## Review Notes\n\n", encoding="utf-8")
    return source_manifest_path


def _initialize_state(args: argparse.Namespace, *, overwrite: bool) -> dict[str, Any]:
    master_manifest_path = _resolve(args.manifest)
    if not master_manifest_path.exists():
        raise SystemExit(f"manifest not found: {master_manifest_path}")
    state_path = _state_path_for_manifest(master_manifest_path)
    if state_path.exists() and not overwrite:
        raise SystemExit(f"parallel state already exists: {state_path}; use resume or start --replace-state")
    master_manifest = _read_json(master_manifest_path)
    candidate_output_root = _candidate_output_root(master_manifest_path, master_manifest)
    entries = _selected_master_entries(master_manifest, args.source_id)
    provider = str(args.provider or "gemini")
    model = str(args.model or generate_candidates._default_model_for_provider(provider))
    now = utc_now_iso()
    state_entries: dict[str, Any] = {}
    for entry in entries:
        source_id = str(entry.get("source_id") or "").strip()
        source_manifest_path = _write_source_manifest(
            master_manifest_path=master_manifest_path,
            master_manifest=master_manifest,
            source_entry=entry,
            candidate_output_root=candidate_output_root,
        )
        state_entries[source_id] = {
            "source_id": source_id,
            "manifest_path": str(source_manifest_path),
            "status": "pending",
            "pid": None,
            "pgid": None,
            "returncode": None,
            "started_at": "",
            "finished_at": "",
            "duration_seconds": None,
            "error": "",
        }
    state = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "status": "planned",
        "runner_pid": None,
        "cancel_requested_at": "",
        "master_manifest_path": str(master_manifest_path),
        "candidate_output_root": str(candidate_output_root),
        "provider": provider,
        "model": model,
        "workers": int(args.workers),
        "render_pdf": not bool(args.no_pdf),
        "include_exam_bridge": bool(args.include_exam_bridge),
        "force": bool(args.force),
        "rerender_existing": bool(args.rerender_existing),
        "source_ids": list(state_entries),
        "entries": state_entries,
    }
    state["semantic_config"] = _semantic_config_for_state(state)
    state["semantic_config_hash"] = _semantic_config_hash(state["semantic_config"])
    _write_json(state_path, state)
    return state


def _load_or_initialize_state(args: argparse.Namespace) -> dict[str, Any]:
    master_manifest_path = _resolve(args.manifest)
    state_path = _state_path_for_manifest(master_manifest_path)
    if state_path.exists():
        state = _read_json(state_path)
        stored_config = state.get("semantic_config")
        if not isinstance(stored_config, dict):
            stored_config = _semantic_config_for_state(state)
            state["semantic_config"] = stored_config
            state["semantic_config_hash"] = _semantic_config_hash(stored_config)
        requested_diffs: list[str] = []
        if args.provider and str(args.provider) != str(state.get("provider") or ""):
            requested_diffs.append("provider")
        if args.model and str(args.model) != str(state.get("model") or ""):
            requested_diffs.append("model")
        if args.source_id:
            requested_sources = sorted(item.strip() for item in args.source_id if item.strip())
            if requested_sources != sorted(str(item) for item in state.get("source_ids", [])):
                requested_diffs.append("source-id")
        if args.force is not None and bool(args.force) != bool(state.get("force", False)):
            requested_diffs.append("force")
        if args.rerender_existing is not None and bool(args.rerender_existing) != bool(state.get("rerender_existing", False)):
            requested_diffs.append("rerender-existing")
        if args.no_pdf is not None and (not bool(args.no_pdf)) != bool(state.get("render_pdf", True)):
            requested_diffs.append("no-pdf")
        if args.include_exam_bridge is not None and bool(args.include_exam_bridge) != bool(state.get("include_exam_bridge", False)):
            requested_diffs.append("include-exam-bridge")
        if requested_diffs:
            raise SystemExit(
                "resume cannot change semantic run options: "
                + ", ".join(requested_diffs)
                + ". Start a fresh run or replace state instead."
            )
        state["workers"] = int(args.workers)
        state["updated_at"] = utc_now_iso()
        _write_json(state_path, state)
        return state
    return _initialize_state(args, overwrite=True)


def _state_path(state: dict[str, Any]) -> Path:
    return _state_path_for_manifest(Path(str(state["master_manifest_path"])))


def _save_state(state: dict[str, Any]) -> None:
    with STATE_LOCK:
        state["updated_at"] = utc_now_iso()
        _write_json(_state_path(state), state)


def _request_cancel(state: dict[str, Any]) -> None:
    if not state.get("cancel_requested_at"):
        state["cancel_requested_at"] = utc_now_iso()
    state["status"] = "cancel_requested"
    _save_state(state)


def _state_cancel_requested(state: dict[str, Any]) -> bool:
    return bool(state.get("cancel_requested_at")) or str(state.get("status") or "") in {
        "cancel_requested",
        "cancelled",
    }


def _refresh_cancel_request(state: dict[str, Any]) -> bool:
    try:
        disk_state = _read_json(_state_path(state))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _state_cancel_requested(state)
    if disk_state.get("cancel_requested_at") or disk_state.get("status") in {"cancel_requested", "cancelled"}:
        state["cancel_requested_at"] = disk_state.get("cancel_requested_at") or state.get("cancel_requested_at") or utc_now_iso()
        state["status"] = "cancel_requested"
        return True
    return _state_cancel_requested(state)


def _mark_unfinished_cancelled(state: dict[str, Any], source_ids: list[str] | None = None) -> None:
    selected = set(source_ids or state.get("source_ids", []))
    for source_id in selected:
        entry = state.get("entries", {}).get(source_id)
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in TERMINAL_ENTRY_STATUSES:
            entry["status"] = "cancelled"
            entry["finished_at"] = entry.get("finished_at") or utc_now_iso()
            entry["pid"] = None
            entry["pgid"] = None


def _pid_is_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _terminate_process_group(pgid: int | None, *, sig: int = signal.SIGTERM) -> None:
    if not pgid:
        return
    try:
        os.killpg(int(pgid), sig)
    except (PermissionError, ProcessLookupError):
        return


def _terminate_state_workers(state: dict[str, Any]) -> int:
    running = [
        entry
        for entry in state.get("entries", {}).values()
        if isinstance(entry, dict) and _pid_is_alive(entry.get("pid"))
    ]
    for entry in running:
        _terminate_process_group(entry.get("pgid"), sig=signal.SIGTERM)
    deadline = time.time() + TERMINATION_GRACE_SECONDS
    while time.time() < deadline:
        if not any(_pid_is_alive(entry.get("pid")) for entry in running):
            break
        time.sleep(0.2)
    for entry in running:
        if _pid_is_alive(entry.get("pid")):
            _terminate_process_group(entry.get("pgid"), sig=signal.SIGKILL)
        entry["status"] = "cancelled"
        entry["finished_at"] = utc_now_iso()
        entry["returncode"] = -signal.SIGTERM
        entry["terminated_at"] = entry["finished_at"]
        entry["pid"] = None
        entry["pgid"] = None
    _save_state(state)
    return len(running)


def _worker_command(state: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    command = [
        str(_preferred_python_path()),
        str(SCRIPT_DIR / "generate_candidates.py"),
        "--manifest",
        str(entry["manifest_path"]),
        "--provider",
        str(state["provider"]),
        "--model",
        str(state["model"]),
        "--skip-preflight",
    ]
    if state.get("force"):
        command.append("--force")
    if state.get("rerender_existing"):
        command.append("--rerender-existing")
    if not state.get("render_pdf", True):
        command.append("--no-pdf")
    if state.get("include_exam_bridge"):
        command.append("--include-exam-bridge")
    return command


def _run_preflight_if_needed(args: argparse.Namespace, state: dict[str, Any]) -> None:
    if args.skip_preflight:
        return
    command = [
        str(_preferred_python_path()),
        str(SCRIPT_DIR / "generate_candidates.py"),
        "--manifest",
        str(next(iter(state["entries"].values()))["manifest_path"]),
        "--provider",
        str(state["provider"]),
        "--model",
        str(state["model"]),
        "--preflight-only",
    ]
    if not state.get("render_pdf", True):
        command.append("--no-pdf")
    subprocess.run(command, check=True)


def _verify_state(state: dict[str, Any]) -> dict[str, Any]:
    candidate_output_root = Path(str(state["candidate_output_root"]))
    source_results = []
    for source_id in state.get("source_ids", []):
        entry = state.get("entries", {}).get(source_id, {})
        source_results.append(
            verify_source_artifacts(
                candidate_output_root=candidate_output_root,
                provider=str(state["provider"]),
                model=str(state["model"]),
                source_id=str(source_id),
                source_manifest_path=Path(str(entry.get("manifest_path") or "")),
                render_pdf=bool(state.get("render_pdf", True)),
                include_exam_bridge=bool(state.get("include_exam_bridge", False)),
            )
        )
    complete_count = sum(1 for item in source_results if item["status"] == "complete")
    running_count = sum(
        1
        for entry in state.get("entries", {}).values()
        if isinstance(entry, dict) and entry.get("status") == "running" and _pid_is_alive(entry.get("pid"))
    )
    expected_pdf_count = sum(int(item["expected_pdf_count"]) for item in source_results)
    present_pdf_count = sum(int(item["present_pdf_count"]) for item in source_results)
    return {
        "status": "complete" if source_results and complete_count == len(source_results) else "incomplete",
        "source_count": len(source_results),
        "complete_source_count": complete_count,
        "running_count": running_count,
        "expected_pdf_count": expected_pdf_count,
        "present_pdf_count": present_pdf_count,
        "sources": source_results,
    }


def _run_one_source(state: dict[str, Any], source_id: str) -> dict[str, Any]:
    if _state_cancel_requested(state):
        state_entry = state["entries"][source_id]
        state_entry["status"] = "cancelled"
        state_entry["finished_at"] = utc_now_iso()
        _save_state(state)
        return {"source_id": source_id, "returncode": 130, "cancelled": True}
    state_entry = state["entries"][source_id]
    command = _worker_command(state, state_entry)
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    state_entry["status"] = "running"
    state_entry["pid"] = process.pid
    state_entry["pgid"] = os.getpgid(process.pid)
    state_entry["started_at"] = utc_now_iso()
    state_entry["finished_at"] = ""
    state_entry["returncode"] = None
    state_entry["error"] = ""
    _save_state(state)
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{source_id}] {line.rstrip()}", flush=True)
    returncode = process.wait()
    state_entry["returncode"] = returncode
    state_entry["finished_at"] = utc_now_iso()
    state_entry["duration_seconds"] = round(time.monotonic() - started, 2)
    state_entry["pid"] = None
    state_entry["pgid"] = None
    if _state_cancel_requested(state):
        state_entry["status"] = "cancelled"
    else:
        state_entry["status"] = "written" if returncode == 0 else "error"
    if returncode != 0 and state_entry["status"] != "cancelled":
        state_entry["error"] = f"generate_candidates exited with {returncode}"
    _save_state(state)
    return {
        "source_id": source_id,
        "returncode": returncode,
        "duration_seconds": state_entry["duration_seconds"],
    }


def _run_pool(args: argparse.Namespace, state: dict[str, Any]) -> int:
    verification = _verify_state(state)
    incomplete = [item["source_id"] for item in verification["sources"] if item["status"] != "complete"]
    if not incomplete:
        state["status"] = "complete"
        state["runner_pid"] = None
        _save_state(state)
        print(json.dumps({"status": "complete", "source_count": verification["source_count"]}, indent=2))
        return 0
    _run_preflight_if_needed(args, state)
    state["status"] = "running"
    state["runner_pid"] = os.getpid()
    _save_state(state)

    interrupted = False

    def _handle_signal(signum: int, frame: object) -> None:
        del frame
        nonlocal interrupted
        interrupted = True
        _request_cancel(state)
        _terminate_state_workers(state)
        raise KeyboardInterrupt(f"received signal {signum}")

    original_int = signal.signal(signal.SIGINT, _handle_signal)
    original_term = signal.signal(signal.SIGTERM, _handle_signal)
    results: list[dict[str, Any]] = []
    pending = deque(incomplete)
    future_to_source: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
    cancelled = False
    executor: concurrent.futures.ThreadPoolExecutor | None = None
    try:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=int(state["workers"]))
        while pending or future_to_source:
            if _refresh_cancel_request(state):
                cancelled = True
                break
            while pending and len(future_to_source) < int(state["workers"]) and not _state_cancel_requested(state):
                source_id = pending.popleft()
                future_to_source[executor.submit(_run_one_source, state, source_id)] = source_id
            if not future_to_source:
                continue
            done, _ = concurrent.futures.wait(
                future_to_source,
                timeout=0.5,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                source_id = future_to_source.pop(future)
                try:
                    results.append(future.result())
                except Exception as exc:
                    entry = state["entries"][source_id]
                    entry["status"] = "error"
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                    entry["finished_at"] = utc_now_iso()
                    entry["pid"] = None
                    entry["pgid"] = None
                    results.append({"source_id": source_id, "returncode": 99, "error": entry["error"]})
                    _save_state(state)
    except KeyboardInterrupt:
        cancelled = True
        _request_cancel(state)
        _terminate_state_workers(state)
        _mark_unfinished_cancelled(state, list(pending) + list(future_to_source.values()))
        state["status"] = "cancelled" if interrupted else "interrupted"
        state["runner_pid"] = None
        _save_state(state)
        return 130
    finally:
        if cancelled:
            for future in future_to_source:
                future.cancel()
            _terminate_state_workers(state)
        if executor is not None:
            executor.shutdown(wait=not cancelled, cancel_futures=True)
        signal.signal(signal.SIGINT, original_int)
        signal.signal(signal.SIGTERM, original_term)
    if cancelled:
        _mark_unfinished_cancelled(state, list(pending) + list(future_to_source.values()))
        state["status"] = "cancelled"
        state["runner_pid"] = None
        _save_state(state)
        print(json.dumps({"status": "cancelled", "results": results}, indent=2, ensure_ascii=False))
        return 130

    verification = _verify_state(state)
    state["status"] = "complete" if verification["status"] == "complete" else "partial"
    state["runner_pid"] = None
    _save_state(state)
    print(
        json.dumps(
            {
                "status": state["status"],
                "results": sorted(results, key=lambda item: str(item["source_id"])),
                "verification": {
                    key: verification[key]
                    for key in ("source_count", "complete_source_count", "running_count", "expected_pdf_count", "present_pdf_count")
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if state["status"] == "complete" else 1


def _print_status(args: argparse.Namespace, *, fail_on_incomplete: bool) -> int:
    master_manifest_path = _resolve(args.manifest)
    state_path = _state_path_for_manifest(master_manifest_path)
    if not state_path.exists():
        raise SystemExit(f"parallel state not found: {state_path}")
    state = _read_json(state_path)
    verification = _verify_state(state)
    print(json.dumps({"state_path": str(state_path), **verification}, indent=2, ensure_ascii=False))
    return 1 if fail_on_incomplete and verification["status"] != "complete" else 0


def _cancel(args: argparse.Namespace) -> int:
    master_manifest_path = _resolve(args.manifest)
    state_path = _state_path_for_manifest(master_manifest_path)
    if not state_path.exists():
        raise SystemExit(f"parallel state not found: {state_path}")
    state = _read_json(state_path)
    _request_cancel(state)
    runner_pid = int(state.get("runner_pid") or 0)
    if runner_pid and runner_pid != os.getpid() and _pid_is_alive(runner_pid):
        try:
            os.kill(runner_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    count = _terminate_state_workers(state)
    _mark_unfinished_cancelled(state)
    state["status"] = "cancelled"
    state["runner_pid"] = None
    _save_state(state)
    print(json.dumps({"status": "cancelled", "terminated_workers": count}, indent=2))
    return 0


def _add_common_run_args(
    parser: argparse.ArgumentParser,
    *,
    provider_default: str | None,
    boolean_default: bool | None = False,
) -> None:
    parser.add_argument("--manifest", required=True, help="Master printout review manifest.json.")
    parser.add_argument("--workers", type=int, default=3, help="Maximum concurrent source workers.")
    parser.add_argument("--source-id", action="append", default=[], help="Restrict to one source id; repeatable.")
    parser.add_argument("--provider", choices=generate_candidates.SUPPORTED_PROVIDERS, default=provider_default)
    parser.add_argument("--model")
    parser.add_argument("--force", action="store_true", default=boolean_default, help="Pass --force to source workers.")
    parser.add_argument(
        "--rerender-existing",
        action="store_true",
        default=boolean_default,
        help="Pass --rerender-existing to source workers.",
    )
    parser.add_argument("--no-pdf", action="store_true", default=boolean_default, help="Pass --no-pdf to source workers.")
    parser.add_argument(
        "--include-exam-bridge",
        action="store_true",
        default=boolean_default,
        help="Pass --include-exam-bridge to source workers.",
    )
    parser.add_argument("--skip-preflight", action="store_true", help="Skip the single provider/toolchain preflight before running workers.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create a fresh parallel state and run incomplete sources.")
    _add_common_run_args(start, provider_default="gemini", boolean_default=False)
    start.add_argument("--replace-state", action="store_true", help="Replace an existing parallel state file.")

    resume = subparsers.add_parser("resume", help="Resume incomplete sources from an existing parallel state.")
    _add_common_run_args(resume, provider_default=None, boolean_default=None)

    status = subparsers.add_parser("status", help="Print current parallel state and artifact verification.")
    status.add_argument("--manifest", required=True)

    verify = subparsers.add_parser("verify", help="Print verification and exit non-zero if incomplete.")
    verify.add_argument("--manifest", required=True)

    cancel = subparsers.add_parser("cancel", help="Request run cancellation and stop recorded workers.")
    cancel.add_argument("--manifest", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "start":
        if int(args.workers) < 1:
            raise SystemExit("--workers must be at least 1")
        state = _initialize_state(args, overwrite=bool(args.replace_state))
        return _run_pool(args, state)
    if args.command == "resume":
        if int(args.workers) < 1:
            raise SystemExit("--workers must be at least 1")
        state = _load_or_initialize_state(args)
        return _run_pool(args, state)
    if args.command == "status":
        return _print_status(args, fail_on_incomplete=False)
    if args.command == "verify":
        return _print_status(args, fail_on_incomplete=True)
    if args.command == "cancel":
        return _cancel(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
