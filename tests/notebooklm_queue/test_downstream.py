from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.constants import STATE_COMPLETED, STATE_FAILED_RETRYABLE, STATE_REPO_PUSHED, STATE_WAITING_FOR_ARTIFACT
from notebooklm_queue.downstream import DownstreamOptions, DownstreamSyncError, sync_downstream_publication
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.store import QueueStore


def _identity(show_slug: str = "bioneuro") -> JobIdentity:
    return JobIdentity(
        show_slug=show_slug,
        subject_slug="bioneuro" if show_slug == "bioneuro" else show_slug,
        lecture_key="W1L1",
        content_types=("audio", "quiz"),
        config_hash="cfg-1",
    )


def _seed_job(
    tmp_path: Path,
    *,
    show_slug: str = "bioneuro",
    changed_paths: list[str] | None = None,
    pending_request_count: int = 0,
) -> tuple[QueueStore, dict[str, object]]:
    config_path = tmp_path / "shows" / show_slug / "config.github.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_payload: dict[str, object] = {"subject_slug": "bioneuro" if show_slug == "bioneuro" else show_slug}
    if show_slug == "personlighedspsykologi-da":
        config_payload["queue"] = {
            "freudd_deploy": False,
            "spotify_sync": False,
            "content_manifest_mode": "never",
            "portal_sidecars_mode": "never",
            "quiz_sync": {"enabled": False},
        }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(show_slug), initial_state=STATE_REPO_PUSHED)
    manifest = {
        "version": 1,
        "bundle_id": "bundle-1",
        "job_id": str(job["job_id"]),
        "show_slug": show_slug,
        "lecture_key": "W1L1",
        "bundle": {
            "bundle_hash": "bundle-hash-1",
            "pending_request_count": pending_request_count,
        },
        "repo_publish": {
            "head_sha": "abc123",
            "changed_allowlist_paths": changed_paths or [],
        },
    }
    manifest_path = store.save_publish_manifest(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        payload=manifest,
        bundle_id="bundle-1",
    )
    job["artifacts"] = {
        "publish": {
            "latest_bundle_manifest": manifest_path,
            "latest_bundle_id": "bundle-1",
            "last_repo_commit_sha": "abc123",
        }
    }
    store.save_job(job)
    return store, job


def test_sync_downstream_marks_completed_when_no_targets_expected(tmp_path: Path) -> None:
    store, job = _seed_job(tmp_path, changed_paths=["shows/bioneuro/feeds/rss.xml"])

    result = sync_downstream_publication(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=DownstreamOptions(repo_root=tmp_path, timeout_seconds=1, poll_interval_seconds=1),
    )

    assert result["final_state"] == STATE_COMPLETED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_COMPLETED
    manifest_path = store.root / updated["artifacts"]["publish"]["latest_bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["downstream"]["targets"] == []
    assert updated["artifacts"]["publish"]["last_completed_bundle_hash"] == "bundle-hash-1"


def test_sync_downstream_waits_for_freudd_deploy_success(tmp_path: Path, monkeypatch) -> None:
    store, job = _seed_job(
        tmp_path,
        changed_paths=[
            "shows/bioneuro/content_manifest.json",
            "shows/bioneuro/quiz_links.json",
        ],
    )

    def fake_wait_for_workflow_target(**kwargs):
        return {
            "name": kwargs["target"].name,
            "workflow_file": kwargs["target"].workflow_file,
            "status": "completed",
            "conclusion": "success",
            "run_id": 12345,
            "url": "https://github.com/example/run/12345",
            "changed_paths": list(kwargs["target"].changed_paths),
        }

    monkeypatch.setattr("notebooklm_queue.downstream._wait_for_workflow_target", fake_wait_for_workflow_target)

    result = sync_downstream_publication(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=DownstreamOptions(repo_root=tmp_path, timeout_seconds=1, poll_interval_seconds=1),
    )

    assert result["final_state"] == STATE_COMPLETED
    assert result["targets"][0]["conclusion"] == "success"
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_COMPLETED
    assert updated["artifacts"]["publish"]["last_downstream_targets"][0]["run_id"] == 12345
    assert updated["artifacts"]["publish"]["last_completed_bundle_hash"] == "bundle-hash-1"


def test_sync_downstream_returns_to_waiting_for_artifact_when_bundle_is_partial(tmp_path: Path) -> None:
    store, job = _seed_job(tmp_path, pending_request_count=2)

    result = sync_downstream_publication(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=DownstreamOptions(repo_root=tmp_path, timeout_seconds=1, poll_interval_seconds=1),
    )

    assert result["final_state"] == STATE_WAITING_FOR_ARTIFACT
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_WAITING_FOR_ARTIFACT
    assert updated["next_retry_at"]
    assert updated["artifacts"]["publish"]["last_completed_bundle_hash"] == "bundle-hash-1"
    manifest_path = store.root / updated["artifacts"]["publish"]["latest_bundle_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "waiting_for_artifact"


def test_sync_downstream_marks_retryable_failure_on_failed_workflow(tmp_path: Path, monkeypatch) -> None:
    store, job = _seed_job(
        tmp_path,
        changed_paths=["shows/bioneuro/content_manifest.json"],
    )

    def fake_wait_for_workflow_target(**kwargs):
        raise DownstreamSyncError("workflow failed")

    monkeypatch.setattr("notebooklm_queue.downstream._wait_for_workflow_target", fake_wait_for_workflow_target)

    result = sync_downstream_publication(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=DownstreamOptions(repo_root=tmp_path, timeout_seconds=1, poll_interval_seconds=1),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_FAILED_RETRYABLE
    assert updated["last_error"] == "workflow failed"


def test_sync_downstream_skips_freudd_targets_for_danish_mirror(tmp_path: Path) -> None:
    store, job = _seed_job(
        tmp_path,
        show_slug="personlighedspsykologi-da",
        changed_paths=["shows/personlighedspsykologi-da/content_manifest.json"],
    )

    result = sync_downstream_publication(
        store=store,
        show_slug="personlighedspsykologi-da",
        job_id=str(job["job_id"]),
        options=DownstreamOptions(repo_root=tmp_path, timeout_seconds=1, poll_interval_seconds=1),
    )

    assert result["final_state"] == STATE_COMPLETED
    assert result["targets"] == []
