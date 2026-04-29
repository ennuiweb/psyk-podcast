from __future__ import annotations

from pathlib import Path

import pytest

from notebooklm_queue.constants import STATE_GENERATING, STATE_QUEUED, STATE_RETRY_SCHEDULED
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.store import QueueStore


def _identity(*, lecture_key: str, content_types: tuple[str, ...] = ("podcast",)) -> JobIdentity:
    return JobIdentity(
        show_slug="demo-show",
        subject_slug="demo-subject",
        lecture_key=lecture_key,
        content_types=content_types,
        config_hash="cfg-123",
    )


def test_upsert_job_is_idempotent_and_builds_indexes(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    first = store.upsert_job(_identity(lecture_key="W01L1"), metadata={"source_count": 4})
    second = store.upsert_job(_identity(lecture_key="W01L1"), metadata={"source_count": 4})

    assert first["job_id"] == second["job_id"]
    assert store.list_jobs(show_slug="demo-show")[0]["lecture_key"] == "W01L1"
    global_jobs = store.list_jobs()
    assert len(global_jobs) == 1
    assert global_jobs[0]["show_slug"] == "demo-show"


def test_transition_job_tracks_history_and_retry_window(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    job = store.upsert_job(_identity(lecture_key="W01L1"))

    updated = store.transition_job(
        show_slug="demo-show",
        job_id=job["job_id"],
        state=STATE_RETRY_SCHEDULED,
        error="rate limited",
        retry_at="2099-01-01T00:00:00+00:00",
        details={"profile": "acct-2"},
    )

    assert updated["state"] == STATE_RETRY_SCHEDULED
    assert updated["last_error"] == "rate limited"
    assert updated["next_retry_at"] == "2099-01-01T00:00:00+00:00"
    assert updated["history"][-1]["details"]["profile"] == "acct-2"


def test_claim_next_job_respects_priority_and_state(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    store.upsert_job(_identity(lecture_key="W01L2"), priority=50)
    store.upsert_job(_identity(lecture_key="W01L1"), priority=10)

    claimed = store.claim_next_job(show_slug="demo-show", target_state=STATE_GENERATING)

    assert claimed is not None
    assert claimed["lecture_key"] == "W01L1"
    assert claimed["state"] == STATE_GENERATING
    assert claimed["attempt_count"] == 1


def test_retry_ready_jobs_requeue_due_entries(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    due = store.upsert_job(_identity(lecture_key="W01L1"))
    later = store.upsert_job(_identity(lecture_key="W01L2"))
    store.transition_job(
        show_slug="demo-show",
        job_id=due["job_id"],
        state=STATE_RETRY_SCHEDULED,
        retry_at="2000-01-01T00:00:00+00:00",
    )
    store.transition_job(
        show_slug="demo-show",
        job_id=later["job_id"],
        state=STATE_RETRY_SCHEDULED,
        retry_at="2999-01-01T00:00:00+00:00",
    )

    updated = store.retry_ready_jobs(show_slug="demo-show")

    assert len(updated) == 1
    assert updated[0]["job_id"] == due["job_id"]
    assert updated[0]["state"] == STATE_QUEUED


def test_reconcile_rebuilds_indexes_from_job_files(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    store.upsert_job(_identity(lecture_key="W01L1"))
    store.upsert_job(_identity(lecture_key="W01L2", content_types=("podcast", "quiz")))

    show_index = store.show_index_path("demo-show")
    global_index = store.global_jobs_index_path
    show_index.unlink()
    global_index.unlink()

    payload = store.reconcile_indexes()

    assert payload["job_count"] == 2
    assert show_index.exists()
    assert global_index.exists()


def test_transition_rejects_unexpected_source_state(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    job = store.upsert_job(_identity(lecture_key="W01L1"))

    with pytest.raises(ValueError):
        store.transition_job(
            show_slug="demo-show",
            job_id=job["job_id"],
            state=STATE_GENERATING,
            expected_states={"completed"},
        )
