from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "notebooklm-podcast-auto"
    / "personlighedspsykologi"
    / "scripts"
    / "download_week.py"
)
SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_download_week", MODULE_PATH)
download_week = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(download_week)


def test_collect_storage_candidates_prefers_explicit_current_profiles_over_request_log(
    tmp_path: Path, monkeypatch
) -> None:
    current_storage = tmp_path / "current.json"
    fallback_storage = tmp_path / "fallback.json"
    old_storage = tmp_path / "old.json"
    for path in (current_storage, fallback_storage, old_storage):
        path.write_text("{}", encoding="utf-8")
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "fallback": str(fallback_storage),
                    "current": str(current_storage),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))

    candidates = download_week.collect_storage_candidates(
        tmp_path,
        storage=None,
        profile=None,
        profiles_file=None,
        profile_priority="current",
        log_auth={
            "profile": "old",
            "profiles_file": str(profiles_file),
            "storage_path": str(old_storage),
        },
    )

    assert candidates[:3] == [
        (str(current_storage.resolve()), "profiles:current"),
        (str(fallback_storage.resolve()), "profiles:fallback"),
        (str(old_storage), "log:storage"),
    ]
