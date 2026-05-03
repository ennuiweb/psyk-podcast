"""Rebuild repo-side metadata after queue-managed object upload."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .constants import (
    STATE_COMMITTING_REPO_ARTIFACTS,
    STATE_FAILED_RETRYABLE,
    STATE_OBJECTS_UPLOADED,
    STATE_REBUILDING_METADATA,
)
from .show_artifacts import ShowArtifactPaths, resolve_show_artifact_paths
from .show_config import ShowConfigSelectionError, load_show_config, resolve_manifest_bound_show_config_path
from .store import QueueStore, utc_now_iso

SHOWS_WITH_SPOTIFY_SYNC = {"bioneuro", "personlighedspsykologi-en"}
SHOWS_WITH_CONTENT_MANIFEST = {"bioneuro", "personlighedspsykologi-en"}
SPOTIFY_SHOW_URLS = {
    "bioneuro": "https://open.spotify.com/show/5QIHRkc1N6xuCqtnfmsPfN",
    "personlighedspsykologi-en": "https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv",
}


@dataclass(frozen=True, slots=True)
class MetadataOptions:
    repo_root: Path
    actor: str = "system"
    show_config_path: Path | None = None


@dataclass(frozen=True, slots=True)
class QuizSyncSettings:
    output_root: str
    links_file: str
    subject_slug: str
    remote_root: str
    include_subject_in_flat_id: bool = False
    language_tag: str = "[EN]"


QUIZ_SYNC_SETTINGS = {
    "bioneuro": QuizSyncSettings(
        output_root="notebooklm-podcast-auto/bioneuro/output",
        links_file="shows/bioneuro/quiz_links.json",
        subject_slug="bioneuro",
        remote_root="/var/www/quizzes/bioneuro",
        include_subject_in_flat_id=True,
    ),
    "personlighedspsykologi-en": QuizSyncSettings(
        output_root="notebooklm-podcast-auto/personlighedspsykologi/output",
        links_file="shows/personlighedspsykologi-en/quiz_links.json",
        subject_slug="personlighedspsykologi",
        remote_root="/var/www/quizzes/personlighedspsykologi",
    ),
}


def rebuild_repo_metadata(
    *,
    store: QueueStore,
    show_slug: str,
    options: MetadataOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        manifest_path = _latest_publish_manifest_path(store=store, job=job)
        manifest = _load_publish_manifest(manifest_path)
        bundle_id = str(manifest.get("bundle_id") or job.get("artifacts", {}).get("publish", {}).get("latest_bundle_id") or "")
        if not bundle_id:
            raise RuntimeError(f"Missing bundle_id for metadata rebuild job {job['job_id']}")

        run_id = utc_now_iso().replace(":", "").replace("-", "")
        metadata_payload: dict[str, Any] = {
            "run_id": run_id,
            "status": "running",
            "started_at": utc_now_iso(),
            "phases": [],
        }
        manifest["metadata"] = metadata_payload

        try:
            resolved_show_config_path = resolve_manifest_bound_show_config_path(
                repo_root=options.repo_root,
                default_path=adapter.show_config_path,
                manifest=manifest,
                override_path=options.show_config_path,
            )
            config = load_show_config(
                repo_root=options.repo_root,
                default_path=adapter.show_config_path,
                override_path=resolved_show_config_path,
            )
            artifact_paths = resolve_show_artifact_paths(
                repo_root=options.repo_root,
                show_slug=show_slug,
                config=config,
            )
        except ShowConfigSelectionError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
                note="Metadata rebuild config selection failed.",
            )

        for phase in _phase_definitions(
            repo_root=options.repo_root,
            show_slug=show_slug,
            subject_slug=adapter.subject_slug,
            show_config_path=resolved_show_config_path,
            artifact_paths=artifact_paths,
        ):
            result = _run_phase(name=phase["name"], command=phase["command"], repo_root=options.repo_root)
            metadata_payload["phases"].append(result)
            if result["returncode"] != 0:
                return _finalize_failure(
                    store=store,
                    job=job,
                    manifest=manifest,
                    bundle_id=bundle_id,
                    actor=options.actor,
                    error_message=result.get("stderr") or result.get("stdout") or f"{phase['name']} failed",
                    note=f"Metadata phase failed: {phase['name']}",
                )

        try:
            validation = _validate_repo_metadata(
                repo_root=options.repo_root,
                show_slug=show_slug,
                artifact_paths=artifact_paths,
            )
        except MetadataValidationError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
                note="Metadata validation failed.",
            )

        metadata_payload["status"] = "completed"
        metadata_payload["completed_at"] = utc_now_iso()
        metadata_payload["validation"] = validation
        manifest["status"] = "repo_artifacts_ready"
        manifest["completed_at"] = utc_now_iso()
        manifest_path_rel = store.save_publish_manifest(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            payload=manifest,
            bundle_id=bundle_id,
        )
        updated = store.transition_job(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            state=STATE_COMMITTING_REPO_ARTIFACTS,
            actor=options.actor,
            note="Repo metadata rebuilt from uploaded objects.",
            details={
                "bundle_id": bundle_id,
                "manifest_path": manifest_path_rel,
                "run_id": run_id,
                "phase_count": len(metadata_payload["phases"]),
            },
        )
        updated = _persist_metadata_artifacts(
            store=store,
            job=updated,
            manifest_path=manifest_path_rel,
            run_id=run_id,
            phase_count=len(metadata_payload["phases"]),
        )
        return {
            "job_id": str(updated["job_id"]),
            "show_slug": show_slug,
            "bundle_id": bundle_id,
            "run_id": run_id,
            "final_state": str(updated.get("state") or ""),
            "manifest_path": manifest_path_rel,
            "phase_count": len(metadata_payload["phases"]),
        }


class MetadataValidationError(RuntimeError):
    """Raised when rebuilt repo metadata is missing required downstream artifacts."""


def _claim_or_resume_job(
    *,
    store: QueueStore,
    show_slug: str,
    job_id: str | None,
    actor: str,
) -> dict[str, Any]:
    if job_id:
        job = store.load_job(show_slug=show_slug, job_id=job_id)
        if not job:
            raise FileNotFoundError(f"Unknown job: {show_slug}/{job_id}")
        state = str(job.get("state") or "")
        if state == STATE_OBJECTS_UPLOADED:
            return store.transition_job(
                show_slug=show_slug,
                job_id=job_id,
                state=STATE_REBUILDING_METADATA,
                actor=actor,
                note="Rebuilding repo metadata for explicitly selected job.",
                expected_states={STATE_OBJECTS_UPLOADED},
            )
        if state != STATE_REBUILDING_METADATA:
            raise ValueError(
                f"Job {job_id} is in state {state}, expected {STATE_OBJECTS_UPLOADED} "
                f"or {STATE_REBUILDING_METADATA}."
            )
        return job

    candidates = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_OBJECTS_UPLOADED
    ]
    if not candidates:
        raise FileNotFoundError(f"No objects_uploaded job found for show: {show_slug}")
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("job_id") or ""),
        )
    )
    winner = candidates[0]
    return store.transition_job(
        show_slug=show_slug,
        job_id=str(winner["job_id"]),
        state=STATE_REBUILDING_METADATA,
        actor=actor,
        note="Claimed next objects_uploaded job for repo metadata rebuild.",
        expected_states={STATE_OBJECTS_UPLOADED},
    )


def _phase_definitions(
    *,
    repo_root: Path,
    show_slug: str,
    subject_slug: str,
    show_config_path: Path,
    artifact_paths: ShowArtifactPaths,
) -> list[dict[str, object]]:
    python = str(repo_root / ".venv" / "bin" / "python")
    phases: list[dict[str, object]] = []
    quiz_sync = QUIZ_SYNC_SETTINGS.get(show_slug)
    if quiz_sync is not None:
        command = [
            python,
            str(repo_root / "scripts" / "sync_quiz_links.py"),
            "--output-root",
            quiz_sync.output_root,
            "--links-file",
            str(artifact_paths.quiz_links_path.relative_to(repo_root)),
            "--subject-slug",
            quiz_sync.subject_slug,
            "--language-tag",
            quiz_sync.language_tag,
            "--quiz-path-mode",
            "flat-id",
            "--flat-id-len",
            "8",
            "--quiz-difficulty",
            "any",
            "--fallback-derive-mp3-names",
            "--remote-root",
            quiz_sync.remote_root,
            "--ssh-key",
            _resolve_droplet_ssh_key(),
        ]
        if artifact_paths.inventory_path.exists():
            command.extend(
                [
                    "--preferred-audio-inventory",
                    str(artifact_paths.inventory_path.relative_to(repo_root)),
                ]
            )
        if quiz_sync.include_subject_in_flat_id:
            command.append("--flat-id-include-subject")
        phases.append(
            {
                "name": "sync_quiz_links",
                "command": command,
            }
        )
    phases.append(
        {
            "name": "generate_feed",
            "command": [
                python,
                str(repo_root / "podcast-tools" / "gdrive_podcast_feed.py"),
                "--config",
                str(show_config_path),
            ],
        }
    )
    if show_slug == "personlighedspsykologi-en":
        phases.append(
            {
                "name": "validate_regeneration_inventory",
                "command": [
                    python,
                    str(repo_root / "scripts" / "validate_regeneration_inventory.py"),
                    "--show-slug",
                    "personlighedspsykologi-en",
                ],
            }
        )
        phases.append(
            {
                "name": "audit_slide_briefs",
                "command": [
                    python,
                    str(repo_root / "scripts" / "audit_personlighedspsykologi_slide_briefs.py"),
                    "--warn-only",
                ],
            }
        )
    if show_slug in SHOWS_WITH_SPOTIFY_SYNC:
        spotify_credentials_available = bool(
            str(os.environ.get("SPOTIFY_CLIENT_ID") or "").strip()
            and str(os.environ.get("SPOTIFY_CLIENT_SECRET") or "").strip()
        )
        command = [
            python,
            str(repo_root / "scripts" / "sync_spotify_map.py"),
            "--inventory",
            str(artifact_paths.inventory_path),
            "--spotify-map",
            str(artifact_paths.spotify_map_path),
            "--subject-slug",
            subject_slug,
            "--spotify-market",
            "DK",
            "--prune-stale",
            "--allow-unresolved",
        ]
        if spotify_credentials_available:
            command.extend(
                [
                    "--spotify-show-url",
                    SPOTIFY_SHOW_URLS[show_slug],
                ]
            )
        phases.append(
            {
                "name": "sync_spotify_map",
                "command": command,
            }
        )
    if show_slug in SHOWS_WITH_CONTENT_MANIFEST:
        phases.append(
            {
                "name": "rebuild_content_manifest",
                "command": [
                    python,
                    str(repo_root / "freudd_portal" / "manage.py"),
                    "rebuild_content_manifest",
                    "--subject",
                    subject_slug,
                    "--quiz-links-path",
                    str(artifact_paths.quiz_links_path),
                    "--feed-rss-path",
                    str(artifact_paths.feed_path),
                    "--episode-inventory-path",
                    str(artifact_paths.inventory_path),
                    "--spotify-map-path",
                    str(artifact_paths.spotify_map_path),
                    "--output-path",
                    str(artifact_paths.content_manifest_path),
                ],
            }
        )
    return phases


def _resolve_droplet_ssh_key() -> str:
    configured = str(os.environ.get("NOTEBOOKLM_QUEUE_DROPLET_SSH_KEY") or "").strip()
    if configured:
        return configured
    return "~/.ssh/digitalocean_ed25519"


def _run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, Any]:
    started_at = utc_now_iso()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    completed_at = utc_now_iso()
    return {
        "name": name,
        "command": command,
        "command_shell": shlex.join(command),
        "started_at": started_at,
        "completed_at": completed_at,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _validate_repo_metadata(
    *,
    repo_root: Path,
    show_slug: str,
    artifact_paths: ShowArtifactPaths,
) -> dict[str, Any]:
    feed_path = artifact_paths.feed_path
    inventory_path = artifact_paths.inventory_path
    if not feed_path.exists():
        raise MetadataValidationError(f"Missing rebuilt RSS feed: {feed_path}")
    if not inventory_path.exists():
        raise MetadataValidationError(f"Missing rebuilt episode inventory: {inventory_path}")

    summary: dict[str, Any] = {
        "feed_path": str(feed_path.relative_to(repo_root)),
        "inventory_path": str(inventory_path.relative_to(repo_root)),
    }

    if show_slug in SHOWS_WITH_SPOTIFY_SYNC:
        spotify_map_path = artifact_paths.spotify_map_path
        if not spotify_map_path.exists():
            raise MetadataValidationError(f"Missing spotify_map.json for {show_slug}: {spotify_map_path}")
        summary["spotify_map_path"] = str(spotify_map_path.relative_to(repo_root))

    if show_slug in SHOWS_WITH_CONTENT_MANIFEST:
        quiz_path = artifact_paths.quiz_links_path
        manifest_path = artifact_paths.content_manifest_path
        if not quiz_path.exists():
            raise MetadataValidationError(f"Missing quiz_links.json for {show_slug}: {quiz_path}")
        if not manifest_path.exists():
            raise MetadataValidationError(f"Missing content_manifest.json for {show_slug}: {manifest_path}")
        quiz_payload = json.loads(quiz_path.read_text(encoding="utf-8"))
        by_name = quiz_payload.get("by_name") if isinstance(quiz_payload, dict) else None
        if not isinstance(by_name, dict) or not by_name:
            raise MetadataValidationError(f"quiz_links.by_name is empty for {show_slug}")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        lectures = manifest_payload.get("lectures") if isinstance(manifest_payload, dict) else []
        quiz_assets = 0
        if isinstance(lectures, list):
            for lecture in lectures:
                if not isinstance(lecture, dict):
                    continue
                lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
                quiz_assets += len(lecture_assets.get("quizzes") or [])
                readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
                for reading in readings:
                    if not isinstance(reading, dict):
                        continue
                    assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
                    quiz_assets += len(assets.get("quizzes") or [])
        if quiz_assets <= 0:
            raise MetadataValidationError(f"content_manifest has zero quiz assets for {show_slug}")
        summary["quiz_links_path"] = str(quiz_path.relative_to(repo_root))
        summary["content_manifest_path"] = str(manifest_path.relative_to(repo_root))
        summary["quiz_assets"] = quiz_assets
        summary["quiz_links_by_name"] = len(by_name)

    return summary


def _latest_publish_manifest_path(*, store: QueueStore, job: dict[str, Any]) -> Path:
    publish = dict((job.get("artifacts") or {}).get("publish") or {})
    relative = str(publish.get("latest_bundle_manifest") or "").strip()
    if not relative:
        raise RuntimeError(f"No publish manifest recorded for job {job['job_id']}")
    path = store.root / relative
    if not path.exists():
        raise RuntimeError(f"Publish manifest missing for job {job['job_id']}: {path}")
    return path


def _load_publish_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load publish manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Publish manifest must be a JSON object: {path}")
    return payload


def _persist_metadata_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest_path: str,
    run_id: str,
    phase_count: int,
) -> dict[str, Any]:
    artifacts = dict(job.get("artifacts") or {})
    publish = dict(artifacts.get("publish") or {})
    publish.update(
        {
            "latest_bundle_manifest": manifest_path,
            "last_metadata_rebuild_at": utc_now_iso(),
            "last_metadata_run_id": run_id,
            "last_metadata_phase_count": int(phase_count),
        }
    )
    artifacts["publish"] = publish
    job["artifacts"] = artifacts
    store.save_job(job)
    return job


def _finalize_failure(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest: dict[str, Any],
    bundle_id: str,
    actor: str,
    error_message: str,
    note: str,
) -> dict[str, Any]:
    metadata = dict(manifest.get("metadata") or {})
    metadata["status"] = "failed"
    metadata["completed_at"] = utc_now_iso()
    metadata["last_error"] = error_message
    manifest["metadata"] = metadata
    manifest["status"] = "metadata_failed"
    manifest["completed_at"] = utc_now_iso()
    manifest["last_error"] = error_message
    manifest_path = store.save_publish_manifest(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        payload=manifest,
        bundle_id=bundle_id,
    )
    updated = store.transition_job(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        actor=actor,
        note=note,
        error=error_message,
        details={"bundle_id": bundle_id, "manifest_path": manifest_path},
    )
    _persist_metadata_artifacts(
        store=store,
        job=updated,
        manifest_path=manifest_path,
        run_id=str(metadata.get("run_id") or ""),
        phase_count=len(metadata.get("phases") or []),
    )
    return {
        "bundle_id": bundle_id,
        "job_id": str(updated["job_id"]),
        "show_slug": str(updated["show_slug"]),
        "final_state": str(updated.get("state") or ""),
        "manifest_path": manifest_path,
        "error": error_message,
    }
