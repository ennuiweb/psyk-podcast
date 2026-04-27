"""Path helpers for Spotify transcript tooling."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_home_dir(create: bool = False) -> Path:
    """Resolve the local Spotify transcript home directory."""

    raw_home = os.environ.get("SPOTIFY_TRANSCRIPTS_HOME")
    path = Path(raw_home).expanduser().resolve() if raw_home else (Path.home() / ".spotify-transcripts")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
    return path


def get_storage_state_path() -> Path:
    return get_home_dir() / "storage_state.json"


def get_browser_profile_dir() -> Path:
    return get_home_dir() / "browser_profile"


def get_path_info() -> dict[str, str]:
    home_from_env = os.environ.get("SPOTIFY_TRANSCRIPTS_HOME")
    return {
        "home_dir": str(get_home_dir()),
        "home_source": "SPOTIFY_TRANSCRIPTS_HOME" if home_from_env else "default (~/.spotify-transcripts)",
        "storage_state_path": str(get_storage_state_path()),
        "browser_profile_dir": str(get_browser_profile_dir()),
    }


def read_storage_state() -> dict[str, Any]:
    path = get_storage_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
