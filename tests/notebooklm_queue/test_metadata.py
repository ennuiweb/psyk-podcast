from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.constants import (
    STATE_COMMITTING_REPO_ARTIFACTS,
    STATE_FAILED_RETRYABLE,
    STATE_OBJECTS_UPLOADED,
)
from notebooklm_queue.metadata import MetadataOptions, rebuild_repo_metadata
from notebooklm_queue.models import JobIdentity
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
            json.dumps(
                {
                    "subject_slug": "bioneuro",
                    "output_inventory": "shows/bioneuro/episode_inventory.json",
                    "storage": {
                        "provider": "r2",
                        "bucket": "freudd-audio",
                        "endpoint": "https://example.r2.cloudflarestorage.com",
                        "prefix": "shows/bioneuro",
                        "manifest_file": "shows/bioneuro/media_manifest.json",
                    },
                }
            ),
        ),
        ("shows/bioneuro/auto_spec.json", "{}"),
        ("shows/bioneuro/episode_metadata.json", "{}"),
        ("notebooklm-podcast-auto/bioneuro/prompt_config.json", "{}"),
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (repo_root / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (repo_root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    return repo_root


def _seed_objects_uploaded_job(tmp_path: Path, repo_root: Path) -> tuple[QueueStore, dict[str, object]]:
    store = QueueStore(tmp_path / "queue-root")
    job = store.upsert_job(_identity(), initial_state=STATE_OBJECTS_UPLOADED)
    manifest = {
        "version": 1,
        "bundle_id": "bundle-1",
        "job_id": str(job["job_id"]),
        "show_slug": "bioneuro",
        "subject_slug": "bioneuro",
        "lecture_key": "W1L1",
        "bundle": {
            "artifact_count": 1,
            "bundle_hash": "abc123",
            "artifacts": [],
        },
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


def test_rebuild_repo_metadata_runs_expected_bioneuro_phases(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)
    (repo_root / "shows/bioneuro/episode_inventory.json").write_text(json.dumps({"episodes": []}), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        commands.append(command)
        show_root = repo_root / "shows" / "bioneuro"
        if name == "sync_quiz_links":
            (show_root / "quiz_links.json").write_text(
                json.dumps({"by_name": {"Title 1": [{"url": "https://freudd.dk/q/abc.html"}]}}),
                encoding="utf-8",
            )
        elif name == "generate_feed":
            (show_root / "feeds").mkdir(parents=True, exist_ok=True)
            (show_root / "feeds" / "rss.xml").write_text("<rss />\n", encoding="utf-8")
            (show_root / "episode_inventory.json").write_text(
                json.dumps({"episodes": [{"episode_key": "ep-1", "title": "Title 1"}]}),
                encoding="utf-8",
            )
        elif name == "sync_spotify_map":
            (show_root / "spotify_map.json").write_text(
                json.dumps({"by_episode_key": {"ep-1": "https://open.spotify.com/episode/abc"}}),
                encoding="utf-8",
            )
        elif name == "rebuild_content_manifest":
            (show_root / "content_manifest.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_assets": {"quizzes": [{"url": "https://freudd.dk/q/abc.html"}]},
                                "readings": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", fake_run_phase)

    result = rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_COMMITTING_REPO_ARTIFACTS
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_COMMITTING_REPO_ARTIFACTS
    assert updated["artifacts"]["publish"]["last_metadata_phase_count"] == 4
    assert len(commands) == 4
    assert commands[0][1].endswith("scripts/sync_quiz_links.py")
    assert commands[0][commands[0].index("--remote-root") + 1] == "/var/www/quizzes/bioneuro"
    assert "--flat-id-include-subject" in commands[0]
    assert commands[0][commands[0].index("--preferred-audio-inventory") + 1] == "shows/bioneuro/episode_inventory.json"
    assert commands[1][1].endswith("podcast-tools/gdrive_podcast_feed.py")
    assert commands[2][1].endswith("scripts/sync_spotify_map.py")
    assert "--spotify-show-url" not in commands[2]
    assert commands[3][1].endswith("freudd_portal/manage.py")


def test_rebuild_repo_metadata_marks_retryable_failure_on_phase_error(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)

    def failing_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 1,
            "stdout": "",
            "stderr": "boom",
        }

    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", failing_run_phase)

    result = rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert result["final_state"] == STATE_FAILED_RETRYABLE
    updated = store.load_job(show_slug="bioneuro", job_id=str(job["job_id"]))
    assert updated["state"] == STATE_FAILED_RETRYABLE
    assert updated["last_error"] == "boom"


def test_rebuild_repo_metadata_uses_manifest_bound_override_config(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)
    manifest_path = store.root / str(job["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["show_config"] = {"path": "shows/bioneuro/config.r2-pilot.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (repo_root / "shows/bioneuro/config.r2-pilot.json").write_text(
        json.dumps({"storage": {"provider": "r2", "manifest_file": "shows/bioneuro/media_manifest.json"}}),
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def fake_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        commands.append(command)
        show_root = repo_root / "shows" / "bioneuro"
        if name == "sync_quiz_links":
            (show_root / "quiz_links.json").write_text(json.dumps({"by_name": {}}), encoding="utf-8")
        elif name == "generate_feed":
            (show_root / "feeds").mkdir(parents=True, exist_ok=True)
            (show_root / "feeds" / "rss.xml").write_text("<rss />\n", encoding="utf-8")
            (show_root / "episode_inventory.json").write_text(json.dumps({"episodes": []}), encoding="utf-8")
        elif name == "sync_spotify_map":
            (show_root / "spotify_map.json").write_text(json.dumps({"by_episode_key": {}}), encoding="utf-8")
        elif name == "rebuild_content_manifest":
            (show_root / "content_manifest.json").write_text(json.dumps({"lectures": []}), encoding="utf-8")
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", fake_run_phase)

    rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert commands[1][commands[1].index("--config") + 1].endswith("shows/bioneuro/config.r2-pilot.json")


def test_rebuild_repo_metadata_uses_pilot_artifact_paths_from_config(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)
    manifest_path = store.root / str(job["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["show_config"] = {"path": "shows/bioneuro/config.r2-pilot.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (repo_root / "shows/bioneuro/config.r2-pilot.json").write_text(
        json.dumps(
            {
                "subject_slug": "bioneuro",
                "output_feed": "shows/bioneuro/pilot/feeds/rss.xml",
                "output_inventory": "shows/bioneuro/pilot/episode_inventory.json",
                "quiz": {"links_file": "shows/bioneuro/pilot/quiz_links.json"},
                "spotify_map_file": "shows/bioneuro/pilot/spotify_map.json",
                "content_manifest_file": "shows/bioneuro/pilot/content_manifest.json",
                "storage": {"provider": "r2", "manifest_file": "shows/bioneuro/pilot/media_manifest.json"},
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "shows/bioneuro/pilot").mkdir(parents=True, exist_ok=True)
    (repo_root / "shows/bioneuro/pilot/episode_inventory.json").write_text(
        json.dumps({"episodes": []}),
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def fake_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        commands.append(command)
        pilot_root = repo_root / "shows" / "bioneuro" / "pilot"
        if name == "sync_quiz_links":
            (pilot_root / "quiz_links.json").parent.mkdir(parents=True, exist_ok=True)
            (pilot_root / "quiz_links.json").write_text(json.dumps({"by_name": {"Title 1": [{}]}}), encoding="utf-8")
        elif name == "generate_feed":
            (pilot_root / "feeds").mkdir(parents=True, exist_ok=True)
            (pilot_root / "feeds" / "rss.xml").write_text("<rss />\n", encoding="utf-8")
            (pilot_root / "episode_inventory.json").write_text(
                json.dumps({"episodes": [{"episode_key": "ep-1", "title": "Title 1"}]}),
                encoding="utf-8",
            )
        elif name == "sync_spotify_map":
            (pilot_root / "spotify_map.json").write_text(
                json.dumps({"by_episode_key": {"ep-1": "https://open.spotify.com/episode/abc"}}),
                encoding="utf-8",
            )
        elif name == "rebuild_content_manifest":
            (pilot_root / "content_manifest.json").write_text(
                json.dumps({"lectures": [{"lecture_assets": {"quizzes": [{}]}, "readings": []}]}),
                encoding="utf-8",
            )
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", fake_run_phase)

    rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert commands[0][commands[0].index("--links-file") + 1] == "shows/bioneuro/pilot/quiz_links.json"
    assert commands[0][commands[0].index("--preferred-audio-inventory") + 1] == "shows/bioneuro/pilot/episode_inventory.json"
    assert commands[2][commands[2].index("--inventory") + 1].endswith("shows/bioneuro/pilot/episode_inventory.json")
    assert commands[2][commands[2].index("--spotify-map") + 1].endswith("shows/bioneuro/pilot/spotify_map.json")
    assert "--spotify-show-url" not in commands[2]
    assert commands[3][commands[3].index("--output-path") + 1].endswith("shows/bioneuro/pilot/content_manifest.json")


def test_rebuild_repo_metadata_omits_preferred_inventory_when_target_inventory_missing(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)
    manifest_path = store.root / str(job["artifacts"]["publish"]["latest_bundle_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["show_config"] = {"path": "shows/bioneuro/config.r2-pilot.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (repo_root / "shows/bioneuro/config.r2-pilot.json").write_text(
        json.dumps(
            {
                "subject_slug": "bioneuro",
                "output_feed": "shows/bioneuro/pilot/feeds/rss.xml",
                "output_inventory": "shows/bioneuro/pilot/episode_inventory.json",
                "quiz": {"links_file": "shows/bioneuro/pilot/quiz_links.json"},
                "spotify_map_file": "shows/bioneuro/pilot/spotify_map.json",
                "content_manifest_file": "shows/bioneuro/pilot/content_manifest.json",
                "storage": {"provider": "r2", "manifest_file": "shows/bioneuro/pilot/media_manifest.json"},
            }
        ),
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def fake_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        commands.append(command)
        pilot_root = repo_root / "shows" / "bioneuro" / "pilot"
        if name == "sync_quiz_links":
            (pilot_root / "quiz_links.json").parent.mkdir(parents=True, exist_ok=True)
            (pilot_root / "quiz_links.json").write_text(json.dumps({"by_name": {"Title 1": [{}]}}), encoding="utf-8")
        elif name == "generate_feed":
            (pilot_root / "feeds").mkdir(parents=True, exist_ok=True)
            (pilot_root / "feeds" / "rss.xml").write_text("<rss />\n", encoding="utf-8")
            (pilot_root / "episode_inventory.json").write_text(
                json.dumps({"episodes": [{"episode_key": "ep-1", "title": "Title 1"}]}),
                encoding="utf-8",
            )
        elif name == "sync_spotify_map":
            (pilot_root / "spotify_map.json").write_text(
                json.dumps({"by_episode_key": {"ep-1": "https://open.spotify.com/episode/abc"}}),
                encoding="utf-8",
            )
        elif name == "rebuild_content_manifest":
            (pilot_root / "content_manifest.json").write_text(
                json.dumps({"lectures": [{"lecture_assets": {"quizzes": [{}]}, "readings": []}]}),
                encoding="utf-8",
            )
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", fake_run_phase)

    rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert "--preferred-audio-inventory" not in commands[0]


def test_rebuild_repo_metadata_includes_spotify_show_lookup_when_credentials_exist(tmp_path: Path, monkeypatch) -> None:
    repo_root = _make_repo_root(tmp_path)
    store, job = _seed_objects_uploaded_job(tmp_path, repo_root)
    (repo_root / "shows/bioneuro/episode_inventory.json").write_text(json.dumps({"episodes": []}), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, object]:
        commands.append(command)
        show_root = repo_root / "shows" / "bioneuro"
        if name == "sync_quiz_links":
            (show_root / "quiz_links.json").write_text(json.dumps({"by_name": {}}), encoding="utf-8")
        elif name == "generate_feed":
            (show_root / "feeds").mkdir(parents=True, exist_ok=True)
            (show_root / "feeds" / "rss.xml").write_text("<rss />\n", encoding="utf-8")
            (show_root / "episode_inventory.json").write_text(json.dumps({"episodes": []}), encoding="utf-8")
        elif name == "sync_spotify_map":
            (show_root / "spotify_map.json").write_text(json.dumps({"by_episode_key": {}}), encoding="utf-8")
        elif name == "rebuild_content_manifest":
            (show_root / "content_manifest.json").write_text(json.dumps({"lectures": []}), encoding="utf-8")
        return {
            "name": name,
            "command": command,
            "command_shell": " ".join(command),
            "started_at": "2026-05-01T00:00:00+00:00",
            "completed_at": "2026-05-01T00:00:01+00:00",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("notebooklm_queue.metadata._run_phase", fake_run_phase)

    rebuild_repo_metadata(
        store=store,
        show_slug="bioneuro",
        job_id=str(job["job_id"]),
        options=MetadataOptions(repo_root=repo_root),
    )

    assert commands[2][commands[2].index("--spotify-show-url") + 1] == "https://open.spotify.com/show/5QIHRkc1N6xuCqtnfmsPfN"
