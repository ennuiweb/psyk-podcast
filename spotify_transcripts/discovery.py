"""Show and episode discovery for Spotify transcript downloads."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import EpisodeSource, ShowSources

SPOTIFY_EPISODE_ID_RE = re.compile(
    r"^https://open\.spotify\.com/episode/(?P<episode_id>[A-Za-z0-9]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Unable to read {label}: {path} ({exc})") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to parse {label}: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return payload


def _spotify_episode_id(url: str | None) -> str | None:
    if not url:
        return None
    match = SPOTIFY_EPISODE_ID_RE.match(str(url).strip())
    if not match:
        return None
    episode_id = str(match.group("episode_id") or "").strip()
    return episode_id or None


def load_show_sources(*, repo_root: Path, show_slug: str) -> ShowSources:
    show_root = (repo_root / "shows" / show_slug).resolve()
    if not show_root.exists():
        raise SystemExit(f"Unknown show slug: {show_slug} ({show_root} does not exist)")

    inventory_path = show_root / "episode_inventory.json"
    spotify_map_path = show_root / "spotify_map.json"
    inventory_payload = _load_json(inventory_path, "episode inventory")
    spotify_map_payload = _load_json(spotify_map_path, "spotify map")

    subject_slug = str(inventory_payload.get("subject_slug") or "").strip().lower() or None
    raw_episodes = inventory_payload.get("episodes")
    if not isinstance(raw_episodes, list):
        raise SystemExit(f"Episode inventory missing episodes list: {inventory_path}")

    raw_by_episode_key = spotify_map_payload.get("by_episode_key")
    by_episode_key = raw_by_episode_key if isinstance(raw_by_episode_key, dict) else {}

    episodes: list[EpisodeSource] = []
    seen_episode_keys: set[str] = set()
    for raw_episode in raw_episodes:
        if not isinstance(raw_episode, dict):
            continue
        episode_key = str(raw_episode.get("episode_key") or raw_episode.get("guid") or "").strip()
        title = str(raw_episode.get("title") or "").strip()
        if not episode_key or not title or episode_key in seen_episode_keys:
            continue
        seen_episode_keys.add(episode_key)

        spotify_url = by_episode_key.get(episode_key)
        if not isinstance(spotify_url, str):
            spotify_url = None
        elif not spotify_url.strip():
            spotify_url = None
        else:
            spotify_url = spotify_url.strip()

        episodes.append(
            EpisodeSource(
                show_slug=show_slug,
                subject_slug=subject_slug,
                show_root=show_root,
                episode_key=episode_key,
                title=title,
                spotify_url=spotify_url,
                spotify_episode_id=_spotify_episode_id(spotify_url),
                inventory_entry=raw_episode,
            )
        )

    return ShowSources(
        show_slug=show_slug,
        subject_slug=subject_slug,
        show_root=show_root,
        inventory_path=inventory_path,
        spotify_map_path=spotify_map_path,
        episodes=tuple(episodes),
    )
