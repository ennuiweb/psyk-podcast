"""Shared subprocess helpers for queue-owned external commands."""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import utc_now_iso

TIMEOUT_RETURN_CODE = 124


@dataclass(frozen=True, slots=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _coerce_output(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


def run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int | None = None,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    effective_timeout = None
    if timeout_seconds is not None:
        effective_timeout = max(int(timeout_seconds), 1)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_note = (
            f"Command timed out after {effective_timeout} seconds: {shlex.join(command)}"
            if effective_timeout is not None
            else f"Command timed out: {shlex.join(command)}"
        )
        stderr = _coerce_output(exc.stderr).rstrip()
        if stderr:
            stderr = f"{stderr}\n{timeout_note}\n"
        else:
            stderr = f"{timeout_note}\n"
        return ProcessResult(
            command=tuple(command),
            returncode=TIMEOUT_RETURN_CODE,
            stdout=_coerce_output(exc.stdout),
            stderr=stderr,
            timed_out=True,
        )
    return ProcessResult(
        command=tuple(command),
        returncode=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


def run_phase_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    timeout_seconds: int | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    started = time.monotonic()
    result = run_process(
        command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    completed_at = utc_now_iso()
    return {
        "name": name,
        "command": command,
        "command_shell": shlex.join(command),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": round(max(time.monotonic() - started, 0.0), 3),
        "returncode": int(result.returncode),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": bool(result.timed_out),
        "timeout_seconds": max(int(timeout_seconds), 1) if timeout_seconds is not None else None,
    }
