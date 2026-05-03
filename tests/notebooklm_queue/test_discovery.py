from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue.discovery import discover_show_jobs, enqueue_discovered_jobs
from notebooklm_queue.runner import build_dry_run_plan
from notebooklm_queue.store import QueueStore


def test_discover_personlighedspsykologi_jobs_from_auto_spec(tmp_path: Path) -> None:
    (tmp_path / "shows" / "personlighedspsykologi-en").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notebooklm-podcast-auto" / "personlighedspsykologi").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shows" / "personlighedspsykologi-en" / "config.github.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notebooklm-podcast-auto" / "personlighedspsykologi" / "prompt_config.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "shows" / "personlighedspsykologi-en" / "auto_spec.json").write_text(
        json.dumps(
            {
                "rules": [
                    {"aliases": ["W01L1", "w1l1"], "topic": "Intro"},
                    {"aliases": ["week 2"], "topic": "Ignored"},
                    {"aliases": ["W01L2"], "topic": "Assessment"},
                ]
            }
        ),
        encoding="utf-8",
    )

    jobs = discover_show_jobs(repo_root=tmp_path, show_slug="personlighedspsykologi-en")

    lecture_keys = [item["identity"].lecture_key for item in jobs]
    assert lecture_keys == ["W01L1", "W01L2"]
    assert jobs[0]["metadata"]["topic"] == "Intro"


def test_discover_bioneuro_jobs_from_episode_metadata(tmp_path: Path) -> None:
    (tmp_path / "shows" / "bioneuro").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notebooklm-podcast-auto" / "bioneuro").mkdir(parents=True, exist_ok=True)
    for relative in (
        "shows/bioneuro/config.github.json",
        "shows/bioneuro/auto_spec.json",
        "notebooklm-podcast-auto/bioneuro/prompt_config.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (tmp_path / "shows" / "bioneuro" / "episode_metadata.json").write_text(
        json.dumps(
            {
                "by_id": {
                    "a": {"meta": {"source_folder": "W1L1 Intro (2026-02-06)"}},
                    "b": {"meta": {"source_folder": "W2L1 Function (2026-02-13)"}},
                },
                "by_name": {
                    "Grundbog Kapitel 1.mp3": {"meta": {"source_folder": "W1L1 Intro (2026-02-06)"}}
                },
            }
        ),
        encoding="utf-8",
    )

    jobs = discover_show_jobs(repo_root=tmp_path, show_slug="bioneuro")

    assert [item["identity"].lecture_key for item in jobs] == ["W1L1", "W2L1"]


def test_enqueue_discovered_jobs_and_build_dry_run_plan(tmp_path: Path) -> None:
    (tmp_path / "shows" / "bioneuro").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notebooklm-podcast-auto" / "bioneuro" / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notebooklm-podcast-auto" / "bioneuro" / "scripts" / "generate_week.py").write_text(
        "#!/usr/bin/env python3\n",
        encoding="utf-8",
    )
    (tmp_path / "notebooklm-podcast-auto" / "bioneuro" / "scripts" / "download_week.py").write_text(
        "#!/usr/bin/env python3\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    for relative in (
        "shows/bioneuro/config.github.json",
        "shows/bioneuro/auto_spec.json",
        "notebooklm-podcast-auto/bioneuro/prompt_config.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (tmp_path / "shows" / "bioneuro" / "episode_metadata.json").write_text(
        json.dumps(
            {
                "by_id": {
                    "a": {"meta": {"source_folder": "W1L1 Intro (2026-02-06)"}},
                }
            }
        ),
        encoding="utf-8",
    )
    store = QueueStore(tmp_path / "queue-root")

    enqueue_discovered_jobs(repo_root=tmp_path, store=store, show_slug="bioneuro")
    plan = build_dry_run_plan(repo_root=tmp_path, store=store, show_slug="bioneuro")

    assert plan["lecture_key"] == "W1L1"
    assert "--dry-run" in plan["generate_command"]
    assert "--week" in plan["download_command"]


def test_discover_jobs_hashes_override_show_config_and_persists_metadata(tmp_path: Path) -> None:
    (tmp_path / "shows" / "bioneuro").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notebooklm-podcast-auto" / "bioneuro").mkdir(parents=True, exist_ok=True)
    for relative, content in (
        ("shows/bioneuro/config.github.json", '{"publication":{"owner":"legacy_workflow"}}'),
        ("shows/bioneuro/config.r2-pilot.json", '{"storage":{"provider":"r2"}}'),
        ("shows/bioneuro/auto_spec.json", "{}"),
        ("notebooklm-podcast-auto/bioneuro/prompt_config.json", "{}"),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (tmp_path / "shows" / "bioneuro" / "episode_metadata.json").write_text(
        json.dumps({"by_id": {"a": {"meta": {"source_folder": "W1L1 Intro (2026-02-06)"}}}}),
        encoding="utf-8",
    )

    default_jobs = discover_show_jobs(repo_root=tmp_path, show_slug="bioneuro")
    override_jobs = discover_show_jobs(
        repo_root=tmp_path,
        show_slug="bioneuro",
        show_config_path=tmp_path / "shows" / "bioneuro" / "config.r2-pilot.json",
    )

    assert default_jobs[0]["identity"].config_hash != override_jobs[0]["identity"].config_hash
    assert override_jobs[0]["metadata"]["show_config_path"] == "shows/bioneuro/config.r2-pilot.json"
