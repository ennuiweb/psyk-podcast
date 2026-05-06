from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "sync_personlighedspsykologi_learning_material_registry.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("sync_learning_material_registry", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_registry_merges_printouts_and_podcast_attempts(tmp_path: Path) -> None:
    module = _load_script_module()
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    output_root = repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output"
    registry_path = show_root / "learning_material_regeneration_registry.json"

    _write_json(show_root / "source_intelligence" / "index.json", {"generated_at": "2026-05-06T08:00:00Z"})
    _write_json(
        show_root / "source_intelligence" / "course_synthesis.json",
        {"generated_at": "2026-05-06T08:01:00Z", "build": {"prompt_version": "course-synthesis-v1"}},
    )
    _write_json(
        registry_path,
        {
            "materials": [
                {
                    "material_id": "manual:preserved",
                    "family": "manual",
                    "material_type": "note",
                    "status": "kept",
                }
            ]
        },
    )

    scaffold_path = output_root / "W01L1" / "scaffolding" / "w01l1-lewis-1999" / "reading-scaffolds.json"
    _write_json(
        scaffold_path,
        {
            "schema_version": 3,
            "generated_at": "2026-05-06T09:00:00Z",
            "source": {
                "source_id": "w01l1-lewis-1999",
                "lecture_key": "W01L1",
                "title": "Lewis (1999)",
                "source_family": "reading",
            },
            "generator": {
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "prompt_version": "reading-scaffolds-v3",
                "generation_config": {"version": "v3"},
            },
            "provenance": {"course_synthesis_sha256": "course-hash"},
        },
    )
    (scaffold_path.parent / "00-reading-guide.md").write_text("guide\n", encoding="utf-8")

    success_name = "W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"
    failed_name = "W1L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=aaaa1111}.mp3"
    mp3_path = output_root / "W01L1" / success_name
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    mp3_path.write_bytes(b"audio")
    prompt = "Podcast prompt body"
    _write_json(
        output_root / "W01L1" / f"{success_name}.request.json",
        {
            "artifact_id": "artifact-1",
            "created_at": "2026-05-06T10:00:00Z",
            "instructions": prompt,
            "output_path": str(mp3_path),
            "auth": {
                "profile": "oskarvedel",
                "source": "profiles_file",
                "profiles_file": "/etc/podcasts/notebooklm-queue/profiles.host.json",
            },
        },
    )
    _write_json(
        output_root / "W01L1" / f"{failed_name}.request.error.json",
        {
            "created_at": "2026-05-06T09:30:00Z",
            "error": "temporary quota failure",
            "auth": {"profile": "fallback", "source": "default"},
        },
    )
    _write_json(
        show_root / "media_manifest.r2.json",
        {
            "items": [
                {
                    "source_name": success_name,
                    "published_at": "2026-05-06T10:05:00Z",
                    "public_url": "https://example.test/audio.mp3",
                    "sha256": "audio-hash",
                }
            ]
        },
    )
    _write_json(
        show_root / "episode_inventory.json",
        {
            "episodes": [
                {
                    "source_name": success_name,
                    "title": "W01L1 - Lewis (1999)",
                    "episode_key": "episode-1",
                    "episode_kind": "reading",
                }
            ]
        },
    )

    payload = module.build_registry(
        repo_root=repo_root,
        show_root=show_root,
        output_root=output_root,
        registry_path=registry_path,
        generated_at="2026-05-06T11:00:00Z",
        campaign="prompt-refresh",
        queue_job_id="job-1",
        lecture_key="W1L1",
    )

    materials = {item["material_id"]: item for item in payload["materials"]}
    assert "manual:preserved" in materials
    printouts = [item for item in payload["materials"] if item.get("family") == "printout"]
    podcasts = [item for item in payload["materials"] if item.get("family") == "podcast"]
    assert len(printouts) == 1
    assert len(podcasts) == 1

    printout = printouts[0]
    assert printout["status"] == "generated_local"
    assert printout["generator"]["prompt_version"] == "reading-scaffolds-v3"
    assert printout["artifact_paths"]["rendered"] == [
        "notebooklm-podcast-auto/personlighedspsykologi/output/W01L1/scaffolding/w01l1-lewis-1999/00-reading-guide.md"
    ]

    podcast = podcasts[0]
    assert podcast["status"] == "published_active"
    assert podcast["lecture_key"] == "W01L1"
    assert podcast["canonical_source_name"] == "W01L1 - Lewis (1999) [EN].mp3"
    assert podcast["campaign"] == "prompt-refresh"
    assert podcast["queue_job_id"] == "job-1"
    assert podcast["prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert [attempt["status"] for attempt in podcast["attempts"]] == ["failed", "success"]

    assert payload["summary"]["total"] == 3
    assert payload["summary"]["by_family"]["podcast"] == 1
    assert payload["source_understanding_snapshot"]["course_synthesis_prompt_version"] == "course-synthesis-v1"
