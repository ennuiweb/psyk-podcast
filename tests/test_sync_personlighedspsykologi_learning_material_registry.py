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


def _write_prompt_config(repo_root: Path) -> None:
    _write_json(
        repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "prompt_config.json",
        {
            "language": "en",
            "languages": [{"code": "en", "suffix": "[EN]"}],
            "audio_prompt_strategy": {"enabled": True},
            "audio_prompt_framework": {"enabled": True, "shared_rules": ["Keep it grounded."]},
            "exam_focus": {"enabled": True},
            "meta_prompting": {"enabled": False, "automatic": {"enabled": False}},
            "course_context": {"enabled": True, "podcast_substrate": {"enabled": True}},
            "weekly_overview": {"format": "deep-dive", "length": "long", "prompt": ""},
            "per_reading": {"format": "deep-dive", "length": "long", "prompt": ""},
            "per_slide": {"format": "deep-dive", "length": "default", "prompt": ""},
            "short": {"format": "deep-dive", "length": "short", "prompt": ""},
        },
    )


def test_build_registry_merges_printouts_and_podcast_attempts(tmp_path: Path) -> None:
    module = _load_script_module()
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    output_root = repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output"
    registry_path = show_root / "learning_material_regeneration_registry.json"

    _write_prompt_config(repo_root)
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
                },
                {
                    "material_id": "quiz:48042f6f",
                    "family": "quiz",
                    "material_type": "quiz",
                    "status": "published_linked",
                    "source_config_hash": "oldhash",
                    "public_relative_path": "/q/48042f6f.html",
                },
                {
                    "material_id": "printout:reading_scaffolds:w01l1-lewis-1999",
                    "family": "printout",
                    "material_type": "reading_scaffolds",
                    "status": "generated_local",
                    "source_id": "w01l1-lewis-1999",
                    "artifact_paths": {
                        "json": (
                            "notebooklm-podcast-auto/personlighedspsykologi/output/W01L1/scaffolding/"
                            "w01l1-lewis-1999/reading-scaffolds.json"
                        )
                    },
                },
            ]
        },
    )

    printout_path = output_root / "printout-json" / "w01l1-lewis-1999" / "reading-printouts.json"
    _write_json(
        printout_path,
        {
            "schema_version": 3,
            "artifact_type": "reading_printouts",
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
                "prompt_version": "reading-printouts-v3",
                "generation_config": {"version": "v3"},
            },
            "provenance": {"course_synthesis_sha256": "course-hash"},
        },
    )
    (output_root / "W01L1--w01l1-lewis-1999--01-reading-guide.pdf").write_bytes(b"guide")
    legacy_duplicate_path = output_root / "W01L1" / "scaffolding" / "w01l1-lewis-1999" / "reading-scaffolds.json"
    _write_json(
        legacy_duplicate_path,
        {
            "schema_version": 2,
            "artifact_type": "reading_printouts",
            "generated_at": "2026-05-05T09:00:00Z",
            "source": {
                "source_id": "w01l1-lewis-1999",
                "lecture_key": "W01L1",
                "title": "Lewis legacy",
                "source_family": "reading",
            },
            "generator": {
                "provider": "gemini",
                "model": "legacy-model",
                "prompt_version": "legacy-printouts",
                "generation_config": {"version": "legacy"},
            },
        },
    )
    (legacy_duplicate_path.parent / "01-abridged-guide.pdf").write_bytes(b"legacy")
    other_printout_path = output_root / "printout-json" / "w02l1-zettler-2020" / "reading-printouts.json"
    _write_json(
        other_printout_path,
        {
            "schema_version": 3,
            "artifact_type": "reading_printouts",
            "generated_at": "2026-05-06T09:10:00Z",
            "source": {
                "source_id": "w02l1-zettler-2020",
                "lecture_key": "W02L1",
                "title": "Zettler et al. (2020)",
                "source_family": "reading",
            },
            "generator": {
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "prompt_version": "reading-printouts-v3",
                "generation_config": {"version": "v3"},
            },
            "provenance": {"course_synthesis_sha256": "course-hash"},
        },
    )
    (output_root / "W02L1--w02l1-zettler-2020--01-reading-guide.pdf").write_bytes(b"other guide")

    success_name = "W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"
    inventory_only_name = (
        "W01L1 - Inventory Only [EN] {type=audio lang=en format=deep-dive length=long hash=cccc3333}.mp3"
    )
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
                },
                {
                    "source_name": inventory_only_name,
                    "published_at": "2026-05-06T10:15:00Z",
                    "public_url": "https://example.test/inventory-only.mp3",
                    "sha256": "inventory-only-audio-hash",
                    "stable_guid": "inventory-only-guid",
                    "size": 12345,
                },
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
                },
                {
                    "source_name": inventory_only_name,
                    "title": "W01L1 - Inventory Only",
                    "episode_key": "episode-2",
                    "episode_kind": "reading",
                    "published_at": "2026-05-06T10:16:00Z",
                    "audio_url": "https://example.test/inventory-only.mp3",
                },
            ]
        },
    )
    quiz_name = "W01L1 - Lewis (1999) [EN] {type=quiz lang=en quantity=standard difficulty=medium download=json hash=quiz1234}.json"
    quiz_path = output_root / "W01L1" / quiz_name
    _write_json(quiz_path, {"title": "Lewis quiz", "questions": []})
    _write_json(
        Path(f"{quiz_path}.request.json"),
        {
            "artifact_id": "quiz-artifact-1",
            "artifact_type": "quiz",
            "created_at": "2026-05-06T10:30:00Z",
            "instructions": "Quiz prompt body",
            "output_path": str(quiz_path),
            "quiz_difficulty": "medium",
            "quiz_format": "json",
            "auth": {"profile": "psykku", "source": "profiles_file"},
        },
    )
    _write_json(
        show_root / "quiz_links.json",
        {
            "by_name": {
                success_name: {
                    "relative_path": "48042f6f.html",
                    "format": "html",
                    "difficulty": "medium",
                    "subject_slug": "personlighedspsykologi",
                    "links": [
                        {
                            "relative_path": "https://learn.example/q/48042f6f.html",
                            "format": "html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        }
                    ],
                }
            }
        },
    )
    _write_json(
        show_root / "slides_catalog.json",
        {
            "version": 1,
            "subject_slug": "personlighedspsykologi",
            "generated_at": "2026-05-06T07:00:00Z",
            "slides": [
                {
                    "slide_key": "w01l1-lecture-intro",
                    "lecture_key": "W01L1",
                    "subcategory": "lecture",
                    "title": "Intro slides",
                    "source_filename": "intro.pdf",
                    "relative_path": "W01L1/lecture/intro.pdf",
                    "matched_by": "manual",
                    "local_relative_path": "Forelæsningsrækken/intro.pdf",
                }
            ],
        },
    )
    _write_json(
        show_root / "content_manifest.json",
        {
            "lectures": [
                {
                    "lecture_key": "W01L1",
                    "lecture_title": "Intro",
                    "readings": [
                        {
                            "reading_key": "w01l1-lewis-1999",
                            "reading_title": "Lewis (1999)",
                            "assets": {
                                "quizzes": [
                                    {
                                        "quiz_id": "48042f6f",
                                        "difficulty": "medium",
                                        "quiz_url": "/q/48042f6f.html",
                                        "episode_title": success_name,
                                    }
                                ]
                            },
                        }
                    ],
                    "slides": [
                        {
                            "slide_key": "w01l1-lecture-intro",
                            "subcategory": "lecture",
                            "title": "Intro slides",
                            "relative_path": "W01L1/lecture/intro.pdf",
                            "assets": {"quizzes": [], "podcasts": []},
                        }
                    ],
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
        podcast_setup_version="podcast-v4",
        printout_setup_version="printout-v2",
    )

    materials = {item["material_id"]: item for item in payload["materials"]}
    assert "manual:preserved" in materials
    assert "printout:reading_scaffolds:w01l1-lewis-1999" not in materials
    printouts = [item for item in payload["materials"] if item.get("family") == "printout"]
    podcasts = [item for item in payload["materials"] if item.get("family") == "podcast"]
    quizzes = [item for item in payload["materials"] if item.get("family") == "quiz"]
    slides = [item for item in payload["materials"] if item.get("family") == "slide"]
    assert len(printouts) == 2
    assert len(podcasts) == 2
    assert len(quizzes) == 1
    assert len(slides) == 1

    printout = next(item for item in printouts if item["source_id"] == "w01l1-lewis-1999")
    assert printout["status"] == "generated_local"
    assert printout["setup_version"] == "printout-v2"
    assert printout["generator"]["prompt_version"] == "reading-printouts-v3"
    assert printout["artifact_paths"]["json"] == (
        "notebooklm-podcast-auto/personlighedspsykologi/output/printout-json/"
        "w01l1-lewis-1999/reading-printouts.json"
    )
    expected_printout_fingerprint = module.sha256_json(
        module.printout_setup_fingerprint_payload(
            payload={"schema_version": 3, "artifact_type": "reading_printouts"},
            generator={
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "prompt_version": "reading-printouts-v3",
            },
            generation_config={"version": "v3"},
        )
    )
    assert printout["config_fingerprint"] == expected_printout_fingerprint
    assert printout["config_hash"] == expected_printout_fingerprint[:16]
    assert printout["course_understanding_fingerprint"] == module.sha256_json({"course_synthesis_sha256": "course-hash"})
    assert printout["artifact_paths"]["rendered"] == [
        "notebooklm-podcast-auto/personlighedspsykologi/output/W01L1--w01l1-lewis-1999--01-reading-guide.pdf"
    ]
    other_printout = next(item for item in printouts if item["source_id"] == "w02l1-zettler-2020")
    assert "setup_version" not in other_printout

    podcast = next(item for item in podcasts if item["source_name"] == success_name)
    assert podcast["status"] == "published_active"
    assert podcast["lecture_key"] == "W01L1"
    assert podcast["canonical_source_name"] == "W01L1 - Lewis (1999) [EN].mp3"
    assert podcast["config_hash"] == "bbbb2222"
    assert podcast["setup_version"] == "podcast-v4"
    expected_prompt_system = module.podcast_prompt_system_snapshot(repo_root=repo_root, show_root=show_root)
    assert podcast["prompt_system_label"] == expected_prompt_system["label"]
    assert podcast["prompt_system_fingerprint"] == expected_prompt_system["fingerprint"]
    assert podcast["prompt_system"]["course_synthesis_prompt_version"] == "course-synthesis-v1"
    assert podcast["campaign"] == "prompt-refresh"
    assert podcast["queue_job_id"] == "job-1"
    assert podcast["prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert [attempt["status"] for attempt in podcast["attempts"]] == ["failed", "success"]
    assert podcast["artifact_paths"]["episode_inventory"] == "shows/personlighedspsykologi-en/episode_inventory.json"
    assert podcast["artifact_paths"]["media_manifest"] == "shows/personlighedspsykologi-en/media_manifest.r2.json"

    inventory_only = next(item for item in podcasts if item["source_name"] == inventory_only_name)
    assert inventory_only["status"] == "published_active"
    assert inventory_only["config_hash"] == "cccc3333"
    assert inventory_only["setup_version"] == "podcast-v4"
    assert inventory_only["prompt_system_label"] == expected_prompt_system["label"]
    assert inventory_only["media_sha256"] == "inventory-only-audio-hash"
    assert inventory_only["stable_guid"] == "inventory-only-guid"
    assert inventory_only["feed_published_at"] == "2026-05-06T10:16:00Z"
    assert inventory_only["media_published_at"] == "2026-05-06T10:15:00Z"
    assert inventory_only["published_at"] == "2026-05-06T10:16:00Z"

    quiz = quizzes[0]
    assert quiz["status"] == "published_active"
    assert quiz["quiz_id"] == "48042f6f"
    assert quiz["config_hash"] == "quiz1234"
    assert quiz["source_config_hash"] == "bbbb2222"
    assert quiz["generated_at"] == "2026-05-06T10:30:00Z"
    assert quiz["public_relative_path"] == "/q/48042f6f.html"
    assert quiz["revision_history"][0]["source_config_hash"] == "oldhash"

    slide = slides[0]
    assert slide["status"] == "published_active"
    assert slide["slide_key"] == "w01l1-lecture-intro"
    assert slide["public_relative_path"] == "/slides/personlighedspsykologi/W01L1/lecture/intro.pdf"

    assert payload["schema_version"] == 3
    assert payload["summary"]["total"] == 7
    assert payload["summary"]["by_family"]["podcast"] == 2
    assert payload["summary"]["by_family"]["printout"] == 2
    assert payload["summary"]["by_family"]["quiz"] == 1
    assert payload["summary"]["by_family"]["slide"] == 1
    assert payload["current_run"]["lecture_key"] == "W01L1"
    assert payload["current_run"]["podcast_setup_version"] == "podcast-v4"
    assert payload["current_run"]["printout_setup_version"] == "printout-v2"
    assert payload["current_run"]["podcast_prompt_system_label"] == expected_prompt_system["label"]
    assert payload["source_understanding_snapshot"]["course_synthesis_prompt_version"] == "course-synthesis-v1"


def test_merge_entries_preserves_setup_version_when_no_new_label_is_supplied() -> None:
    module = _load_script_module()
    previous = {
        "material_id": "podcast:example",
        "family": "podcast",
        "material_type": "audio",
        "status": "published_active",
        "setup_version": "podcast-v4",
        "config_hash": "hash-1",
    }
    discovered = {
        "material_id": "podcast:example",
        "family": "podcast",
        "material_type": "audio",
        "status": "published_active",
        "config_hash": "hash-1",
    }

    merged = module.merge_entries({"podcast:example": previous}, {"podcast:example": discovered})

    assert merged[0]["setup_version"] == "podcast-v4"
    assert "revision_history" not in merged[0]


def test_build_registry_auto_labels_current_lecture_podcasts_when_no_manual_setup_version_is_supplied(
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    output_root = repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output"
    registry_path = show_root / "learning_material_regeneration_registry.json"

    _write_prompt_config(repo_root)
    _write_json(show_root / "source_intelligence" / "index.json", {"generated_at": "2026-05-06T08:00:00Z"})
    _write_json(
        show_root / "source_intelligence" / "course_synthesis.json",
        {"generated_at": "2026-05-06T08:01:00Z", "build": {"prompt_version": "course-synthesis-v1"}},
    )
    _write_json(
        show_root / "episode_inventory.json",
        {
            "episodes": [
                {
                    "source_name": "W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3",
                    "title": "W01L1 - Lewis (1999)",
                    "episode_key": "episode-1",
                    "episode_kind": "reading",
                    "published_at": "2026-05-06T10:16:00Z",
                    "audio_url": "https://example.test/audio.mp3",
                },
                {
                    "source_name": "W02L1 - Other (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=cccc3333}.mp3",
                    "title": "W02L1 - Other (2020)",
                    "episode_key": "episode-2",
                    "episode_kind": "reading",
                    "published_at": "2026-05-06T10:20:00Z",
                    "audio_url": "https://example.test/other.mp3",
                },
            ]
        },
    )
    _write_json(
        show_root / "media_manifest.r2.json",
        {
            "items": [
                {
                    "source_name": "W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3",
                    "published_at": "2026-05-06T10:15:00Z",
                    "public_url": "https://example.test/audio.mp3",
                    "sha256": "audio-hash",
                },
                {
                    "source_name": "W02L1 - Other (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=cccc3333}.mp3",
                    "published_at": "2026-05-06T10:18:00Z",
                    "public_url": "https://example.test/other.mp3",
                    "sha256": "other-audio-hash",
                },
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
        lecture_key="W01L1",
        podcast_setup_version=None,
        printout_setup_version=None,
    )

    expected_prompt_system = module.podcast_prompt_system_snapshot(repo_root=repo_root, show_root=show_root)
    podcasts = {item["source_name"]: item for item in payload["materials"] if item.get("family") == "podcast"}
    assert podcasts["W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"][
        "setup_version"
    ] == expected_prompt_system["label"]
    assert podcasts["W01L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"][
        "prompt_system_label"
    ] == expected_prompt_system["label"]
    assert "setup_version" not in podcasts[
        "W02L1 - Other (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=cccc3333}.mp3"
    ]
    assert "prompt_system_label" not in podcasts[
        "W02L1 - Other (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=cccc3333}.mp3"
    ]
    assert payload["current_run"]["podcast_setup_version"] == expected_prompt_system["label"]
