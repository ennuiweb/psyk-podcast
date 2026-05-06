from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.constants import (
    STATE_BLOCKED_CONFIG_ERROR,
    STATE_APPROVED_FOR_PUBLISH,
    STATE_AWAITING_PUBLISH,
    STATE_FAILED_RETRYABLE,
    STATE_OBJECTS_UPLOADED,
)
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.publish import PublishOptions, UploadOptions, prepare_publish_bundle, upload_publish_bundle
from notebooklm_queue.store import QueueStore


def _identity() -> JobIdentity:
    return JobIdentity(
        show_slug="bioneuro",
        subject_slug="bioneuro",
        lecture_key="W1L1",
        content_types=("audio", "quiz"),
        config_hash="cfg-1",
    )


def _make_repo_root(tmp_path: Path, *, config_payload: dict[str, object] | None = None) -> Path:
    repo_root = tmp_path / "repo"
    for relative, content in (
        (
            "shows/bioneuro/config.github.json",
            json.dumps(
                config_payload
                or {"subject_slug": "bioneuro", "output_inventory": "shows/bioneuro/episode_inventory.json"}
            ),
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
    assert manifest["show_config"]["path"] == "shows/bioneuro/config.github.json"
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


def test_prepare_publish_bundle_allows_partial_bundle_when_request_logs_remain(tmp_path: Path) -> None:
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

    assert result["final_state"] == STATE_APPROVED_FOR_PUBLISH
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_APPROVED_FOR_PUBLISH
    manifest_path = store.root / str(updated["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["bundle"]["pending_request_count"] == 1
    assert manifest["bundle"]["pending_request_logs"] == [
        "notebooklm-podcast-auto/bioneuro/output/W1L1/W1L1 - Reading [EN].request.json"
    ]


class _FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, object]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body, ContentType: str, Metadata: dict[str, str]) -> None:
        payload = Body.read()
        self.objects[Key] = {
            "bucket": Bucket,
            "body": payload,
            "content_type": ContentType,
            "metadata": dict(Metadata),
        }

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        entry = self.objects[Key]
        assert entry["bucket"] == Bucket
        return {
            "ContentLength": len(entry["body"]),
            "ContentType": entry["content_type"],
            "Metadata": entry["metadata"],
        }


def test_upload_publish_bundle_uploads_media_and_writes_r2_manifest(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(
        tmp_path,
        config_payload={
            "subject_slug": "bioneuro",
            "output_inventory": "shows/bioneuro/episode_inventory.json",
            "storage": {
                "provider": "r2",
                "bucket": "freudd-audio",
                "endpoint": "https://example.r2.cloudflarestorage.com",
                "prefix": "shows/bioneuro",
                "public_base_url": "https://audio.example.com",
                "manifest_file": "shows/bioneuro/media_manifest.json",
                "access_key_id_env": "TEST_R2_ACCESS_KEY_ID",
                "secret_access_key_env": "TEST_R2_SECRET_ACCESS_KEY",
            },
        },
    )
    week_dir = repo_root / "notebooklm-podcast-auto/bioneuro/output/W1L1"
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "W1L1 - Reading [EN] {type=audio hash=abc}.mp3").write_bytes(b"audio-data")
    (week_dir / "W1L1 - Reading [EN] {type=quiz difficulty=medium hash=def}.json").write_text(
        json.dumps({"questions": [{"id": 1}]}),
        encoding="utf-8",
    )

    monkeypatch.setenv("TEST_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("TEST_R2_SECRET_ACCESS_KEY", "secret")
    client = _FakeR2Client()
    monkeypatch.setattr("notebooklm_queue.publish._build_r2_client", lambda target: client)

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_AWAITING_PUBLISH)
    prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root),
    )

    result = upload_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=UploadOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_OBJECTS_UPLOADED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_OBJECTS_UPLOADED
    assert updated["artifacts"]["publish"]["uploaded_object_count"] == 1
    manifest_path = repo_root / "shows/bioneuro/media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider"] == "r2"
    assert manifest["bucket"] == "freudd-audio"
    assert len(manifest["items"]) == 1
    item = manifest["items"][0]
    assert item["object_key"] == "shows/bioneuro/W1L1/W1L1 - Reading [EN] {type=audio hash=abc}.mp3"
    assert item["source_name"] == "W1L1 - Reading [EN] {type=audio hash=abc}.mp3"
    assert item["source_path"] == "W1L1/W1L1 - Reading [EN] {type=audio hash=abc}.mp3"
    assert item["public_url"] == (
        "https://audio.example.com/shows/bioneuro/W1L1/"
        "W1L1%20-%20Reading%20%5BEN%5D%20%7Btype%3Daudio%20hash%3Dabc%7D.mp3"
    )


def test_upload_publish_bundle_blocks_drive_backed_show(tmp_path: Path) -> None:
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
    prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root),
    )

    result = upload_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=UploadOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_BLOCKED_CONFIG_ERROR
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_BLOCKED_CONFIG_ERROR
    assert "storage object" in str(updated["last_error"])


def test_upload_publish_bundle_uses_manifest_bound_override_config(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    pilot_config = repo_root / "shows/bioneuro/config.r2-pilot.json"
    pilot_config.write_text(
        json.dumps(
            {
                "subject_slug": "bioneuro",
                "output_inventory": "shows/bioneuro/episode_inventory.json",
                "storage": {
                    "provider": "r2",
                    "bucket": "freudd-audio",
                    "endpoint": "https://example.r2.cloudflarestorage.com",
                    "prefix": "shows/bioneuro",
                    "public_base_url": "https://audio.example.com",
                    "manifest_file": "shows/bioneuro/media_manifest.json",
                    "access_key_id_env": "TEST_R2_ACCESS_KEY_ID",
                    "secret_access_key_env": "TEST_R2_SECRET_ACCESS_KEY",
                },
            }
        ),
        encoding="utf-8",
    )
    week_dir = repo_root / "notebooklm-podcast-auto/bioneuro/output/W1L1"
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "W1L1 - Reading [EN] {type=audio hash=abc}.mp3").write_bytes(b"audio-data")
    (week_dir / "W1L1 - Reading [EN] {type=quiz difficulty=medium hash=def}.json").write_text(
        json.dumps({"questions": [{"id": 1}]}),
        encoding="utf-8",
    )

    monkeypatch.setenv("TEST_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("TEST_R2_SECRET_ACCESS_KEY", "secret")
    client = _FakeR2Client()
    monkeypatch.setattr("notebooklm_queue.publish._build_r2_client", lambda target: client)

    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_AWAITING_PUBLISH)
    prepare_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=PublishOptions(repo_root=repo_root, show_config_path=pilot_config),
    )

    result = upload_publish_bundle(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=UploadOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_OBJECTS_UPLOADED
    manifest = json.loads((repo_root / "shows/bioneuro/media_manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "r2"
