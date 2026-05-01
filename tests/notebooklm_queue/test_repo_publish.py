from __future__ import annotations

import json
import subprocess
from pathlib import Path

from notebooklm_queue.constants import STATE_COMMITTING_REPO_ARTIFACTS, STATE_FAILED_RETRYABLE, STATE_REPO_PUSHED
from notebooklm_queue.models import JobIdentity
from notebooklm_queue.repo_publish import RepoPublishOptions, publish_repo_artifacts
from notebooklm_queue.store import QueueStore


def _identity() -> JobIdentity:
    return JobIdentity(
        show_slug="bioneuro",
        subject_slug="bioneuro",
        lecture_key="W1L1",
        content_types=("audio", "quiz"),
        config_hash="cfg-1",
    )


def _run(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def _seed_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote_root = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_root)], check=True, capture_output=True, text=True)

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_root)], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_root, check=True, capture_output=True, text=True)

    for relative, content in (
        (
            "shows/bioneuro/config.github.json",
            json.dumps(
                {
                    "subject_slug": "bioneuro",
                    "storage": {"provider": "r2", "manifest_file": "shows/bioneuro/media_manifest.json"},
                }
            ),
        ),
        ("shows/bioneuro/feeds/rss.xml", "<rss />\n"),
        ("shows/bioneuro/episode_inventory.json", json.dumps({"episodes": []}) + "\n"),
        ("shows/bioneuro/quiz_links.json", json.dumps({"by_name": {}}) + "\n"),
        ("shows/bioneuro/spotify_map.json", json.dumps({"by_episode_key": {}}) + "\n"),
        ("shows/bioneuro/content_manifest.json", json.dumps({"lectures": []}) + "\n"),
        ("shows/bioneuro/media_manifest.json", json.dumps({"items": []}) + "\n"),
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root, remote_root


def _seed_job(tmp_path: Path, repo_root: Path) -> tuple[QueueStore, dict[str, object]]:
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_COMMITTING_REPO_ARTIFACTS)
    manifest = {
        "version": 1,
        "bundle_id": "bundle-1",
        "job_id": str(job["job_id"]),
        "show_slug": "bioneuro",
        "subject_slug": "bioneuro",
        "lecture_key": "W1L1",
    }
    manifest_path = store.save_publish_manifest(
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        payload=manifest,
        bundle_id="bundle-1",
    )
    job["artifacts"] = {
        "publish": {
            "latest_bundle_manifest": manifest_path,
            "latest_bundle_id": "bundle-1",
        }
    }
    store.save_job(job)
    return store, job


def test_publish_repo_artifacts_commits_and_pushes_allowlisted_files(tmp_path: Path) -> None:
    repo_root, remote_root = _seed_repo(tmp_path)
    store, job = _seed_job(tmp_path, repo_root)

    (repo_root / "shows/bioneuro/feeds/rss.xml").write_text("<rss>updated</rss>\n", encoding="utf-8")
    (repo_root / "shows/bioneuro/quiz_links.json").write_text(
        json.dumps({"by_name": {"Episode": [{"url": "https://freudd.dk/q/abc.html"}]}}) + "\n",
        encoding="utf-8",
    )

    result = publish_repo_artifacts(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=RepoPublishOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_REPO_PUSHED
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_REPO_PUSHED
    assert updated["artifacts"]["publish"]["last_repo_push_performed"] is True
    local_head = _run(["git", "rev-parse", "HEAD"], repo_root)
    remote_head = _run(["git", "rev-parse", "main"], remote_root)
    assert local_head == remote_head


def test_publish_repo_artifacts_fails_on_unexpected_tracked_changes(tmp_path: Path) -> None:
    repo_root, _remote_root = _seed_repo(tmp_path)
    store, job = _seed_job(tmp_path, repo_root)

    (repo_root / "README.md").write_text("unexpected\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "shows/bioneuro/feeds/rss.xml").write_text("<rss>updated</rss>\n", encoding="utf-8")

    result = publish_repo_artifacts(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=RepoPublishOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_FAILED_RETRYABLE
    assert "Unexpected tracked repo changes outside the queue allowlist" in str(updated["last_error"])
