from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.constants import (
    STATE_APPROVED_FOR_PUBLISH,
    STATE_AWAITING_PUBLISH,
    STATE_FAILED_RETRYABLE,
)
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.publish import PublishOptions, prepare_publish_bundle
from notebooklm_queue.store import QueueStore


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
    for relative, content in (
        (
            "shows/bioneuro/config.github.json",
            json.dumps({"subject_slug": "bioneuro", "output_inventory": "shows/bioneuro/episode_inventory.json"}),
        ),
        ("shows/bioneuro/auto_spec.json", "{}"),
        ("shows/bioneuro/episode_metadata.json", "{}"),
        ("notebooklm-podcast-auto/bioneuro/prompt_config.json", "{}"),
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return repo_root


def test_prepare_publish_bundle_approves_valid_job_and_saves_manifest(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    week_dir = repo_root / "notebooklm-podcast-auto/bioneuro/output/W1L1"
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "W1L1 - Reading [EN] {type=audio hash=abc}.mp3").write_bytes(b"audio-data")
    (week_dir / "W1L1 - Reading [EN] {type=quiz difficulty=medium hash=def}.json").write_text(
        json.dumps({"questions": [{"id": 1}]}),
        encoding="utf-8",
    )

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_AWAITING_PUBLISH)

    result = prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_APPROVED_FOR_PUBLISH
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_APPROVED_FOR_PUBLISH
    manifest_path = store.root / str(updated["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["bundle"]["artifact_count"] == 2
    assert manifest["bundle"]["artifact_counts"]["audio"] == 1
    assert manifest["bundle"]["artifact_counts"]["quiz"] == 1


def test_prepare_publish_bundle_fails_when_required_artifacts_are_missing(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    week_dir = repo_root / "notebooklm-podcast-auto/bioneuro/output/W1L1"
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "W1L1 - Reading [EN] {type=audio hash=abc}.mp3").write_bytes(b"audio-data")

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_AWAITING_PUBLISH)

    result = prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_FAILED_RETRYABLE
    manifest_path = store.root / str(updated["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "Missing required artifact types" in manifest["last_error"]


def test_prepare_publish_bundle_fails_when_request_logs_remain(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    week_dir = repo_root / "notebooklm-podcast-auto/bioneuro/output/W1L1"
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "W1L1 - Reading [EN] {type=audio hash=abc}.mp3").write_bytes(b"audio-data")
    (week_dir / "W1L1 - Reading [EN] {type=quiz difficulty=medium hash=def}.json").write_text(
        json.dumps({"questions": [{"id": 1}]}),
        encoding="utf-8",
    )
    (week_dir / "W1L1 - Reading [EN].request.json").write_text("{}", encoding="utf-8")

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_AWAITING_PUBLISH)

    result = prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_FAILED_RETRYABLE
    assert "Pending request logs remain" in str(updated["last_error"])
