from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from notebooklm_queue.constants import STATE_COMPLETED, STATE_FAILED_RETRYABLE, STATE_RETRY_SCHEDULED
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.orchestrator import DrainShowOptions, ServeShowOptions, drain_show_queue, serve_show_queue
from notebooklm_queue.store import QueueStore


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


def test_serve_show_queue_does_not_wait_when_blocked_and_retry_jobs_coexist(tmp_path: Path, monkeypatch) -> None:
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
        retry_at="2099-01-01T00:00:00+00:00",
        expected_states={"queued"},
    )
    store.transition_job(
        show_slug="bioneuro",
        job_id=str(blocked_job["job_id"]),
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
        lambda seconds: (_ for _ in ()).throw(AssertionError("should not sleep when blocked backlog exists")),
    )

    result = serve_show_queue(
        store=store,
        show_slug="bioneuro",
        options=ServeShowOptions(drain=DrainShowOptions(repo_root=repo_root)),
    )

    assert result["stop_reason"] == "manual_intervention_required"
    assert result["wait_plan"]["reason"] == "mixed_retry_and_blocked_backlog"


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


def test_serve_show_queue_stops_for_manual_intervention(tmp_path: Path, monkeypatch) -> None:
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
    assert result["wait_plan"]["state_counts"] == {STATE_FAILED_RETRYABLE: 1}
