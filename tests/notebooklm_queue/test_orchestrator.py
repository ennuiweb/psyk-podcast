from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from notebooklm_queue.constants import (
    STATE_BLOCKED_AUTH_STALE,
    STATE_COMPLETED,
    STATE_FAILED_RETRYABLE,
    STATE_RETRY_SCHEDULED,
    STATE_WAITING_FOR_ARTIFACT,
)
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.orchestrator import DrainShowOptions, ServeShowOptions, drain_show_queue, serve_show_queue
from notebooklm_queue.store import QueueLockError, QueueStore


def _write_profile_capacity_fixture(tmp_path: Path, *, cooled: bool) -> tuple[Path, Path]:
    storage_file = tmp_path / "default-storage.json"
    storage_file.write_text("{}", encoding="utf-8")
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps({"profiles": {"default": str(storage_file)}}),
        encoding="utf-8",
    )
    state_file = tmp_path / "profile_state.json"
    cooldown_until = (datetime.now(tz=UTC) + timedelta(hours=1)).timestamp() if cooled else 0
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "last_error": "rate_limit" if cooled else None,
                        "cooldown_until": cooldown_until,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return profiles_file, state_file


def _patch_non_execution_stages_idle(monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.sync_downstream_publication",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("sync")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.publish_repo_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("push")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.rebuild_repo_metadata",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("metadata")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.upload_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("upload")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.prepare_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("prepare")),
    )


def test_drain_show_queue_runs_stages_until_idle(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    events: list[str] = []

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [{"lecture_key": "W1L1"}], "enqueued": [{"job_id": "job-1"}]},
    )
    monkeypatch.setattr(
        store,
        "retry_ready_jobs",
        lambda show_slug: [{"job_id": "retry-1"}],
    )

    stage_counts = {
        "sync_downstream": 0,
        "push_repo": 1,
        "rebuild_metadata": 1,
        "upload_r2": 1,
        "prepare_publish": 1,
        "run_once": 1,
    }

    def _stage(name: str):
        def _runner(**kwargs):
            remaining = stage_counts[name]
            if remaining <= 0:
                raise FileNotFoundError(name)
            stage_counts[name] = remaining - 1
            events.append(name)
            return {"final_state": f"{name}_done"}

        return _runner

    monkeypatch.setattr("notebooklm_queue.orchestrator.sync_downstream_publication", _stage("sync_downstream"))
    monkeypatch.setattr("notebooklm_queue.orchestrator.publish_repo_artifacts", _stage("push_repo"))
    monkeypatch.setattr("notebooklm_queue.orchestrator.rebuild_repo_metadata", _stage("rebuild_metadata"))
    monkeypatch.setattr("notebooklm_queue.orchestrator.upload_publish_bundle", _stage("upload_r2"))
    monkeypatch.setattr("notebooklm_queue.orchestrator.prepare_publish_bundle", _stage("prepare_publish"))
    monkeypatch.setattr("notebooklm_queue.orchestrator.execute_job", _stage("run_once"))
    monkeypatch.setattr("notebooklm_queue.orchestrator._has_ready_execution_work", lambda **kwargs: True)

    result = drain_show_queue(
        store=store,
        show_slug="bioneuro",
        options=DrainShowOptions(repo_root=repo_root),
    )

    assert result["retry_ready_count"] == 1
    assert result["discovery"]["discovered_count"] == 1
    assert result["discovery"]["enqueued_count"] == 1
    assert result["stage_run_count"] == 5
    assert [item["stage"] for item in result["stage_results"]] == [
        "push_repo",
        "rebuild_metadata",
        "upload_r2",
        "prepare_publish",
        "run_once",
    ]
    assert events == ["push_repo", "rebuild_metadata", "upload_r2", "prepare_publish", "run_once"]
    assert result["stopped_due_to_max_stage_runs"] is False


def test_drain_show_queue_passes_show_config_to_discovery_and_publish_stages(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    show_config = repo_root / "shows" / "bioneuro" / "config.r2-pilot.json"
    show_config.parent.mkdir(parents=True, exist_ok=True)
    show_config.write_text("{}", encoding="utf-8")
    store = QueueStore(tmp_path / "queue-root")
    captured_paths: list[Path] = []

    def _capture_discovery(**kwargs):
        captured_paths.append(kwargs["show_config_path"])
        return {"discovered": [], "enqueued": []}

    def _capture_prepare(**kwargs):
        captured_paths.append(kwargs["options"].show_config_path)
        raise FileNotFoundError("prepare")

    monkeypatch.setattr("notebooklm_queue.orchestrator.enqueue_discovered_jobs", _capture_discovery)
    monkeypatch.setattr(store, "retry_ready_jobs", lambda show_slug: [])
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.sync_downstream_publication",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("sync")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.publish_repo_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("push")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.rebuild_repo_metadata",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("metadata")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.upload_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("upload")),
    )
    monkeypatch.setattr("notebooklm_queue.orchestrator.prepare_publish_bundle", _capture_prepare)
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("run")),
    )

    result = drain_show_queue(
        store=store,
        show_slug="bioneuro",
        options=DrainShowOptions(
            repo_root=repo_root,
            show_config_path=show_config,
        ),
    )

    assert captured_paths == [show_config.resolve(), show_config.resolve()]
    assert result["show_config_path"] == "shows/bioneuro/config.r2-pilot.json"
    assert result["stage_run_count"] == 0


def test_drain_show_queue_stops_when_max_stage_runs_is_hit(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(store, "retry_ready_jobs", lambda show_slug: [])
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.sync_downstream_publication",
        lambda **kwargs: {"final_state": "completed"},
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.publish_repo_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("push")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.rebuild_repo_metadata",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("metadata")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.upload_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("upload")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.prepare_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("prepare")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("run")),
    )

    result = drain_show_queue(
        store=store,
        show_slug="bioneuro",
        options=DrainShowOptions(repo_root=repo_root, max_stage_runs=2),
    )

    assert result["stage_run_count"] == 2
    assert result["stopped_due_to_max_stage_runs"] is True


def test_drain_show_queue_waits_for_profile_capacity_without_claiming_job(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="personlighedspsykologi-en",
            subject_slug="personlighedspsykologi",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    profiles_file, state_file = _write_profile_capacity_fixture(
        tmp_path,
        cooled=True,
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(state_file))
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(store, "retry_ready_jobs", lambda show_slug: [])
    _patch_non_execution_stages_idle(monkeypatch)
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("execute_job should not be called")),
    )

    result = drain_show_queue(
        store=store,
        show_slug="personlighedspsykologi-en",
        options=DrainShowOptions(repo_root=repo_root),
    )

    updated = store.load_job(show_slug="personlighedspsykologi-en", job_id=str(job["job_id"]))
    assert updated["state"] == "queued"
    assert result["stopped_due_to_profile_capacity"] is True
    assert result["stopped_due_to_max_stage_runs"] is False
    assert result["stage_results"][0]["stage"] == "run_once"
    assert result["stage_results"][0]["result"]["final_state"] == "profile_capacity_wait"
    assert result["stage_results"][0]["result"]["reason"] == "no_usable_profiles"


def test_drain_show_queue_waits_when_global_notebooklm_lock_is_held(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    store.upsert_job(
        JobIdentity(
            show_slug="personlighedspsykologi-en",
            subject_slug="personlighedspsykologi",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    profiles_file, state_file = _write_profile_capacity_fixture(
        tmp_path,
        cooled=False,
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(state_file))
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(store, "retry_ready_jobs", lambda show_slug: [])
    _patch_non_execution_stages_idle(monkeypatch)
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("execute_job should not be called")),
    )

    def fake_global_lock(scope: str = "global", *, blocking: bool = False):
        raise QueueLockError(f"Lock is already held for {scope}")

    monkeypatch.setattr(store, "acquire_global_lock", fake_global_lock)

    result = drain_show_queue(
        store=store,
        show_slug="personlighedspsykologi-en",
        options=DrainShowOptions(repo_root=repo_root),
    )

    stage_result = result["stage_results"][0]["result"]
    assert result["stopped_due_to_profile_capacity"] is True
    assert stage_result["final_state"] == "profile_capacity_wait"
    assert stage_result["reason"] == "notebooklm_execution_lock_held"


def test_drain_show_queue_executes_when_profile_capacity_is_available(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="personlighedspsykologi-en",
            subject_slug="personlighedspsykologi",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    profiles_file, state_file = _write_profile_capacity_fixture(
        tmp_path,
        cooled=False,
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(state_file))
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(store, "retry_ready_jobs", lambda show_slug: [])
    _patch_non_execution_stages_idle(monkeypatch)
    calls: list[str] = []

    def fake_execute_job(**kwargs):
        calls.append(kwargs["show_slug"])
        store.transition_job(
            show_slug=kwargs["show_slug"],
            job_id=str(job["job_id"]),
            state=STATE_COMPLETED,
            expected_states={"queued"},
        )
        return {"final_state": STATE_COMPLETED}

    monkeypatch.setattr("notebooklm_queue.orchestrator.execute_job", fake_execute_job)

    result = drain_show_queue(
        store=store,
        show_slug="personlighedspsykologi-en",
        options=DrainShowOptions(repo_root=repo_root),
    )

    assert calls == ["personlighedspsykologi-en"]
    assert result["stopped_due_to_profile_capacity"] is False
    assert result["stage_run_count"] == 1
    assert result["stage_results"][0]["result"]["final_state"] == STATE_COMPLETED


def test_serve_show_queue_treats_profile_capacity_wait_as_clean_stop(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    wait_result = {
        "final_state": "profile_capacity_wait",
        "reason": "no_usable_profiles",
        "sleep_seconds": 300,
        "capacity": {"has_capacity": False},
    }
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": kwargs["show_slug"],
            "stopped_due_to_max_stage_runs": False,
            "stopped_due_to_profile_capacity": True,
            "profile_capacity_wait": wait_result,
            "stage_run_count": 1,
            "queue_summary": store.summarize_jobs(show_slug=kwargs["show_slug"]),
        },
    )

    result = serve_show_queue(
        store=store,
        show_slug="personlighedspsykologi-en",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert result["stop_reason"] == "profile_capacity_wait"
    assert result["wait_plan"] == wait_result


def test_drain_show_queue_repairs_retryable_failures_before_planning_progress(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        error="Generation failed: Sources not ready after waiting. Missing: none. Not ready: 1",
        expected_states={"queued"},
    )

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.sync_downstream_publication",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("sync")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.publish_repo_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("push")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.rebuild_repo_metadata",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("metadata")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.upload_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("upload")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.prepare_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("prepare")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("run")),
    )

    result = drain_show_queue(
        store=store,
        show_slug="bioneuro",
        options=DrainShowOptions(repo_root=repo_root),
    )

    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert result["repaired_retryable_count"] == 1
    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["next_retry_at"]


def test_drain_show_queue_repairs_auth_failures_into_blocked_auth_state(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        error="Authentication expired or invalid. Run 'notebooklm login' to re-authenticate.",
        expected_states={"queued"},
    )

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.enqueue_discovered_jobs",
        lambda **kwargs: {"discovered": [], "enqueued": []},
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.sync_downstream_publication",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("sync")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.publish_repo_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("push")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.rebuild_repo_metadata",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("metadata")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.upload_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("upload")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.prepare_publish_bundle",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("prepare")),
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.execute_job",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("run")),
    )

    result = drain_show_queue(
        store=store,
        show_slug="bioneuro",
        options=DrainShowOptions(repo_root=repo_root),
    )

    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert result["repaired_retryable_count"] == 1
    assert updated["state"] == STATE_BLOCKED_AUTH_STALE
    assert updated["next_retry_at"] is None


def test_serve_show_queue_waits_for_retry_scheduled_backlog(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    retry_at = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_RETRY_SCHEDULED,
        retry_at=retry_at.isoformat(),
        expected_states={"queued"},
    )

    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    drained = {"count": 0}
    slept: list[int] = []

    def fake_now():
        return current_time

    def fake_sleep(seconds: int) -> None:
        nonlocal current_time
        slept.append(seconds)
        current_time = current_time + timedelta(seconds=seconds)

    def fake_drain_show_queue(*, store: QueueStore, show_slug: str, options: DrainShowOptions):
        drained["count"] += 1
        if drained["count"] == 2:
            store.retry_ready_jobs(show_slug=show_slug)
            store.transition_job(
                show_slug=show_slug,
                job_id=str(job["job_id"]),
                state=STATE_COMPLETED,
                expected_states={"queued"},
            )
        return {
            "show_slug": show_slug,
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug=show_slug),
        }

    monkeypatch.setattr("notebooklm_queue.orchestrator._utc_now", fake_now)
    monkeypatch.setattr("notebooklm_queue.orchestrator.time.sleep", fake_sleep)
    monkeypatch.setattr("notebooklm_queue.orchestrator.drain_show_queue", fake_drain_show_queue)

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert drained["count"] == 2
    assert result["cycle_count"] == 2
    assert slept == [300]
    assert result["stop_reason"] == "idle"
    assert result["total_sleep_seconds"] == 300
    assert len(result["recent_cycles"]) == 2


def test_serve_show_queue_waits_for_waiting_artifact_backlog(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    poll_at = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_WAITING_FOR_ARTIFACT,
        retry_at=poll_at.isoformat(),
        expected_states={"queued"},
    )

    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    drained = {"count": 0}
    slept: list[int] = []

    def fake_now():
        return current_time

    def fake_sleep(seconds: int) -> None:
        nonlocal current_time
        slept.append(seconds)
        current_time = current_time + timedelta(seconds=seconds)

    def fake_drain_show_queue(*, store: QueueStore, show_slug: str, options: DrainShowOptions):
        drained["count"] += 1
        if drained["count"] == 2:
            store.transition_job(
                show_slug=show_slug,
                job_id=str(job["job_id"]),
                state=STATE_COMPLETED,
                expected_states={STATE_WAITING_FOR_ARTIFACT},
            )
        return {
            "show_slug": show_slug,
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug=show_slug),
        }

    monkeypatch.setattr("notebooklm_queue.orchestrator._utc_now", fake_now)
    monkeypatch.setattr("notebooklm_queue.orchestrator.time.sleep", fake_sleep)
    monkeypatch.setattr("notebooklm_queue.orchestrator.drain_show_queue", fake_drain_show_queue)

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert drained["count"] == 2
    assert result["cycle_count"] == 2
    assert slept == [60]
    assert result["stop_reason"] == "idle"
    assert result["wait_plan"]["action"] == "idle"
    assert result["total_sleep_seconds"] == 60


def test_serve_show_queue_uses_real_clock_for_retry_wait_plan(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    retry_at = datetime.now(tz=UTC) + timedelta(seconds=3600)
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_RETRY_SCHEDULED,
        retry_at=retry_at.replace(microsecond=0).isoformat(),
        expected_states={"queued"},
    )

    def fake_sleep(seconds: int) -> None:
        raise RuntimeError(f"stop after planning {seconds}")

    monkeypatch.setattr("notebooklm_queue.orchestrator.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": kwargs["show_slug"],
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug=kwargs["show_slug"]),
        },
    )

    try:
        serve_show_queue(
            store=store,
            show_slug="bioneuro",
            options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
        )
    except RuntimeError as exc:
        assert "stop after planning" in str(exc)
    else:  # pragma: no cover - defensive assertion for regression clarity
        raise AssertionError("expected fake sleep to stop the wait loop")


def test_serve_show_queue_respects_service_timeout_before_long_retry_wait(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    retry_at = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_RETRY_SCHEDULED,
        retry_at=retry_at.isoformat(),
        expected_states={"queued"},
    )

    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    monotonic_now = {"value": 100.0}
    slept: list[int] = []

    monkeypatch.setattr("notebooklm_queue.orchestrator._utc_now", lambda: current_time)
    monkeypatch.setattr("notebooklm_queue.orchestrator.time.monotonic", lambda: monotonic_now["value"])
    monkeypatch.setattr("notebooklm_queue.orchestrator.time.sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": kwargs["show_slug"],
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug=kwargs["show_slug"]),
        },
    )

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(
            drain=DrainShowOptions(repo_root=repo_root),
            timeout_seconds=300,
        ),
    )

    assert slept == []
    assert result["stop_reason"] == "service_timeout_reached"
    assert result["wait_plan"]["reason"] == "next_wait_exceeds_time_budget"
    assert result["wait_plan"]["remaining_budget_seconds"] == 300
    assert result["wait_plan"]["sleep_seconds"] == 1800


def test_serve_show_queue_continues_waiting_when_blocked_and_retry_jobs_coexist(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    retry_job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    blocked_job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L2",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(retry_job["job_id"]),
        state=STATE_RETRY_SCHEDULED,
        retry_at="2026-01-01T12:05:00+00:00",
        expected_states={"queued"},
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(blocked_job["job_id"]),
        state=STATE_BLOCKED_AUTH_STALE,
        expected_states={"queued"},
    )

    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    drained = {"count": 0}
    slept: list[int] = []

    def fake_sleep(seconds: int) -> None:
        nonlocal current_time
        slept.append(seconds)
        current_time = current_time + timedelta(seconds=seconds)
        if len(slept) == 1:
            store.transition_job(
                show_slug="bioneuro",
                job_id=str(retry_job["job_id"]),
                state=STATE_COMPLETED,
                expected_states={STATE_RETRY_SCHEDULED},
            )

    def fake_now() -> datetime:
        return current_time

    def fake_drain_show_queue(**kwargs):
        drained["count"] += 1
        return {
            "show_slug": "bioneuro",
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug="bioneuro"),
        }

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        fake_drain_show_queue,
    )
    monkeypatch.setattr("notebooklm_queue.orchestrator._utc_now", fake_now)
    monkeypatch.setattr("notebooklm_queue.orchestrator.time.sleep", fake_sleep)

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert drained["count"] == 2
    assert slept == [300]
    assert result["stop_reason"] == "blocked_backlog_remaining"
    assert result["wait_plan"]["state_counts"] == {STATE_BLOCKED_AUTH_STALE: 1}
    assert result["total_sleep_seconds"] == 300


def test_serve_show_queue_stops_for_invalid_retry_schedule(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    broken = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    broken["state"] = STATE_RETRY_SCHEDULED
    broken["next_retry_at"] = "not-a-timestamp"
    store.save_job(broken)

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug="bioneuro"),
        },
    )

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert result["stop_reason"] == "manual_intervention_required"
    assert result["wait_plan"]["reason"] == "invalid_retry_schedule"
    assert result["wait_plan"]["job_ids"] == [str(job["job_id"])]


def test_serve_show_queue_stops_for_manual_intervention_when_failed_retryable_and_retry_jobs_coexist(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    retry_job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    failed_job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L2",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(retry_job["job_id"]),
        state=STATE_RETRY_SCHEDULED,
        retry_at="2026-01-01T12:05:00+00:00",
        expected_states={"queued"},
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(failed_job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        expected_states={"queued"},
    )

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug="bioneuro"),
        },
    )
    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.time.sleep",
        lambda seconds: (_ for _ in ()).throw(AssertionError("should not sleep when failed_retryable backlog exists")),
    )

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert result["stop_reason"] == "manual_intervention_required"
    assert result["wait_plan"]["reason"] == "mixed_timed_wait_and_failed_retryable_backlog"
    assert result["wait_plan"]["state_counts"] == {
        STATE_FAILED_RETRYABLE: 1,
        STATE_RETRY_SCHEDULED: 1,
    }
    assert result["wait_plan"]["job_ids"] == [str(failed_job["job_id"])]


def test_serve_show_queue_reports_manual_intervention_for_legacy_failed_retryable_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(
        JobIdentity(
            show_slug="bioneuro",
            subject_slug="bioneuro",
            lecture_key="W1L1",
            content_types=("audio",),
            config_hash="cfg-1",
        )
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        expected_states={"queued"},
    )

    monkeypatch.setattr(
        "notebooklm_queue.orchestrator.drain_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stopped_due_to_max_stage_runs": False,
            "stage_run_count": 0,
            "queue_summary": store.summarize_jobs(show_slug="bioneuro"),
        },
    )

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert result["stop_reason"] == "manual_intervention_required"
    assert result["wait_plan"]["reason"] == "failed_retryable_backlog_remaining"
    assert result["wait_plan"]["state_counts"] == {STATE_FAILED_RETRYABLE: 1}
    assert result["wait_plan"]["job_ids"] == [str(job["job_id"])]
