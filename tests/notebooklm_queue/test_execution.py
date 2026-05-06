from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from notebooklm_queue.constants import (
    STATE_APPROVED_FOR_PUBLISH,
    STATE_AWAITING_PUBLISH,
    STATE_FAILED_RETRYABLE,
    STATE_GENERATED,
    STATE_GENERATING,
    STATE_RETRY_SCHEDULED,
)
from notebooklm_queue.execution import ExecutionOptions, execute_job
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.store import QueueStore


def _write_python_shim(path: Path) -> None:
    path.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_phase_script(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _identity() -> JobIdentity:
    return JobIdentity(
        show_slug="bioneuro",
        subject_slug="bioneuro",
        lecture_key="W1L1",
        content_types=("audio", "quiz"),
        config_hash="cfg-1",
    )


def _make_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    _write_python_shim(repo_root / ".venv" / "bin" / "python")
    for relative in (
        "shows/bioneuro/config.github.json",
        "shows/bioneuro/auto_spec.json",
        "shows/bioneuro/episode_metadata.json",
        "notebooklm-podcast-auto/bioneuro/prompt_config.json",
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    return repo_root


def test_execute_job_runs_generate_and_download_and_persists_manifest(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import json, pathlib, sys\n"
        "path = pathlib.Path(sys.argv[0]).resolve().parents[3] / '.phase-generate.json'\n"
        "path.write_text(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False), encoding='utf-8')\n"
        "print('generated ok')\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "import pathlib, sys\n"
        "path = pathlib.Path(sys.argv[0]).resolve().parents[3] / '.phase-download.txt'\n"
        "path.write_text('downloaded', encoding='utf-8')\n"
        "print('downloaded ok')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_AWAITING_PUBLISH
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_AWAITING_PUBLISH
    manifest_path = store.root / str(updated["artifacts"]["execution"]["latest_run_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert [phase["name"] for phase in manifest["phases"]] == ["generate", "download"]
    assert (repo_root / ".phase-generate.json").exists()
    assert (repo_root / ".phase-download.txt").exists()


def test_execute_job_marks_failure_and_saves_run_manifest(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\nprint('boom', file=sys.stderr)\nraise SystemExit(7)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root, retry_at="2099-01-01T00:00:00+00:00"),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["next_retry_at"] == "2099-01-01T00:00:00+00:00"
    manifest_path = store.root / str(updated["artifacts"]["execution"]["latest_run_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["phases"][0]["returncode"] == 7


def test_execute_job_auto_schedules_retry_for_rate_limit_failures(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\nprint('API rate limit or quota exceeded. Please wait before retrying.', file=sys.stderr)\nraise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["next_retry_at"]


def test_execute_job_detects_rate_limit_stdout_when_stderr_has_rpc_noise(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\n"
        "print('Generation failed: API rate limit or quota exceeded. Please wait before retrying.')\n"
        "print('RPC CREATE_ARTIFACT failed after 0.362s', file=sys.stderr)\n"
        "raise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["next_retry_at"]
    assert "RPC CREATE_ARTIFACT failed" in updated["last_error"]


def test_execute_job_auto_schedules_retry_for_transient_notebooklm_generation_failure(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\n"
        "print('Failures: Generator timed out before writing a usable request log for output.mp3')\n"
        "print('RPC CREATE_NOTEBOOK failed after 0.304s', file=sys.stderr)\n"
        "raise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["next_retry_at"]
    assert "RPC CREATE_NOTEBOOK failed" in updated["last_error"]


def test_execute_job_emits_auth_alert_via_command(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\nprint('authentication expired', file=sys.stderr)\nraise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    alert_capture = tmp_path / "alert-command.json"
    monkeypatch.setenv(
        "NOTEBOOKLM_QUEUE_ALERT_COMMAND",
        f"{shlex_quote(sys.executable)} -c "
        f"{shlex_quote('import pathlib, sys; pathlib.Path(sys.argv[1]).write_text(sys.stdin.read(), encoding=\"utf-8\")')} "
        f"{shlex_quote(str(alert_capture))}",
    )
    monkeypatch.setenv("NOTEBOOKLM_QUEUE_ALERT_DEDUP_SECONDS", "0")

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    execution = updated["artifacts"]["execution"]
    assert execution["latest_alert_kind"] == "auth_stale"
    alert_path = Path(execution["latest_alert_path"])
    alert_payload = json.loads(alert_path.read_text(encoding="utf-8"))
    assert alert_payload["kind"] == "auth_stale"
    assert alert_capture.exists()
    delivered = json.loads(alert_capture.read_text(encoding="utf-8"))
    assert delivered["kind"] == "auth_stale"


def test_execute_job_does_not_misclassify_decimal_timing_as_auth_error(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\nprint('RPC CREATE_ARTIFACT failed after 0.403s', file=sys.stderr)\nraise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    monkeypatch.setenv("NOTEBOOKLM_QUEUE_ALERT_DEDUP_SECONDS", "0")

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert "latest_alert_kind" not in updated["artifacts"]["execution"]


def test_execute_job_does_not_alert_rate_limit_before_threshold(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "import sys\nprint('API rate limit or quota exceeded. Please wait before retrying.', file=sys.stderr)\nraise SystemExit(2)\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('should not run')\n",
    )
    monkeypatch.setenv("NOTEBOOKLM_QUEUE_RATE_LIMIT_ALERT_ATTEMPTS", "3")
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_RETRY_SCHEDULED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert "latest_alert_kind" not in updated["artifacts"]["execution"]


def test_execute_job_resumes_from_generated_state_and_skips_generate(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "raise SystemExit('generate should not run')\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('download only ok')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_GENERATED,
        note="Prepared for resume test",
    )

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_AWAITING_PUBLISH
    manifest_path = store.root / str(
        store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))["artifacts"]["execution"]["latest_run_manifest"]
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [phase["name"] for phase in manifest["phases"]] == ["download"]


def test_execute_job_claims_next_queued_job_when_job_id_is_omitted(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "print('generate ok')\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('download ok')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    later = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W2L1",
            content_types=("audio",),
            config_hash="cfg-1",
        ),
        priority=50,
    )
    first = store.upsert_job(_identity(), priority=10)

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["job_id"] == str(first["job_id"])
    untouched = store.load_job(show_slug="bioneuro", job_id=str(later["job_id"]))
    assert untouched["state"] != STATE_GENERATING


def test_execute_job_resumes_in_progress_job_when_job_id_is_omitted(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "raise SystemExit('generate should not run')\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('download resumed ok')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    resumed = store.upsert_job(_identity(), priority=50)
    queued = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W3L1",
            content_types=("audio",),
            config_hash="cfg-1",
        ),
        priority=10,
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(resumed["job_id"]),
        state=STATE_GENERATED,
        note="Prepared generated resume test",
    )

    result = execute_job(
        store=store,
        show_slug="bioneuro",
        options=ExecutionOptions(repo_root=repo_root),
    )

    assert result["job_id"] == str(resumed["job_id"])
    untouched = store.load_job(show_slug="bioneuro", job_id=str(queued["job_id"]))
    assert untouched["state"] != STATE_GENERATING


def test_execute_job_ignores_non_execution_ready_states_when_job_id_is_omitted(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        "print('generate ok')\n",
    )
    _write_phase_script(
        repo_root / "notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        "print('download ok')\n",
    )
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity())
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_APPROVED_FOR_PUBLISH,
        note="Prepared non-execution-ready state",
    )

    with pytest.raises(FileNotFoundError):
        execute_job(
            store=store,
            show_slug="bioneuro",
            options=ExecutionOptions(repo_root=repo_root),
        )


def shlex_quote(text: str) -> str:
    import shlex

    return shlex.quote(text)
