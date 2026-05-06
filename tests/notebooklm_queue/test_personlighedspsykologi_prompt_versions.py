from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.personlighedspsykologi_prompt_versions import (
    configured_prompt_versions,
    resolve_setup_versions,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_configured_prompt_versions_use_show_config_over_defaults(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    _write_json(
        show_root / "prompt_versions.json",
        {
            "prompt_versions": {
                "course_synthesis": "personlighedspsykologi-course-synthesis-v9",
                "reading_printouts": "personlighedspsykologi-reading-printouts-v7",
            }
        },
    )

    resolved = configured_prompt_versions(repo_root=repo_root)

    assert resolved["course_synthesis"] == "personlighedspsykologi-course-synthesis-v9"
    assert resolved["reading_printouts"] == "personlighedspsykologi-reading-printouts-v7"
    assert resolved["podcast_substrate"] == "personlighedspsykologi-podcast-substrate-v2"


def test_resolve_setup_versions_use_show_config_by_default(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    _write_json(
        show_root / "prompt_versions.json",
        {
            "setup_versions": {
                "podcast": "personlighedspsykologi-podcast-v1",
                "printout": "personlighedspsykologi-reading-printouts-v3",
            }
        },
    )
    monkeypatch.delenv("PERSONLIGHEDSPSYKOLOGI_SETUP_VERSION", raising=False)
    monkeypatch.delenv("PERSONLIGHEDSPSYKOLOGI_PODCAST_SETUP_VERSION", raising=False)
    monkeypatch.delenv("PERSONLIGHEDSPSYKOLOGI_PRINTOUT_SETUP_VERSION", raising=False)

    resolved = resolve_setup_versions(repo_root=repo_root)

    assert resolved["podcast"] == "personlighedspsykologi-podcast-v1"
    assert resolved["printout"] == "personlighedspsykologi-reading-printouts-v3"


def test_resolve_setup_versions_shared_override_beats_configured_family_labels(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    show_root = repo_root / "shows" / "personlighedspsykologi-en"
    _write_json(
        show_root / "prompt_versions.json",
        {
            "setup_versions": {
                "podcast": "personlighedspsykologi-podcast-v1",
                "printout": "personlighedspsykologi-reading-printouts-v3",
            }
        },
    )
    monkeypatch.setenv("PERSONLIGHEDSPSYKOLOGI_SETUP_VERSION", "rollout-override")
    monkeypatch.delenv("PERSONLIGHEDSPSYKOLOGI_PODCAST_SETUP_VERSION", raising=False)
    monkeypatch.delenv("PERSONLIGHEDSPSYKOLOGI_PRINTOUT_SETUP_VERSION", raising=False)

    resolved = resolve_setup_versions(repo_root=repo_root)

    assert resolved["podcast"] == "rollout-override"
    assert resolved["printout"] == "rollout-override"
