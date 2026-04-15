#!/usr/bin/env python3
"""Auto-populate spotify_map.json from episode inventory."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MULTISPACE_RE = re.compile(r"\s+")
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
LECTURE_PREFIX_RE = re.compile(
    r"^(?:W\d{1,2}L\d+|U\d{1,2}F\d+|(?:Uge|Week)\s+\d+\s*,\s*(?:Forelæsning|Lecture)\s+\d+)\s*(?:·\s*)?",
    re.IGNORECASE,
)
CATEGORY_PREFIX_RE = re.compile(
    r"^(?:\[\s*(?:podcast|lydbog|kort\s+podcast)\s*\]|podcast|lydbog|kort\s+podcast)\s*(?:·\s*)?",
    re.IGNORECASE,
)
SPOTIFY_EPISODE_URL_RE = re.compile(
    r"^https://open\.spotify\.com/episode/[A-Za-z0-9]+(?:[/?#].*)?$",
    re.IGNORECASE,
)
SPOTIFY_SHOW_URL_RE = re.compile(
    r"^https://open\.spotify\.com/show/(?P<show_id>[A-Za-z0-9]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


def normalize_title_key(value: str) -> str:
    return MULTISPACE_RE.sub(" ", str(value or "")).strip()


def normalize_match_title(value: str) -> str:
    text = normalize_title_key(value).replace("–", "-").replace("—", "-")
    while text:
        updated = CATEGORY_PREFIX_RE.sub("", text).strip()
        updated = LECTURE_PREFIX_RE.sub("", updated).strip()
        updated = normalize_title_key(updated)
        if updated == text:
            break
        text = updated
    return normalize_title_key(text).casefold()


def is_episode_spotify_url(value: str) -> bool:
    url = str(value or "").strip()
    if not url:
        return False
    return bool(SPOTIFY_EPISODE_URL_RE.match(url))


def _inventory_path_from_rss_path(rss_path: Path) -> Path:
    if rss_path.parent.name == "feeds":
        return rss_path.parent.parent / "episode_inventory.json"
    return rss_path.with_name("episode_inventory.json")


def normalize_episode_key(value: object) -> str:
    return str(value or "").strip()


def load_inventory_episodes(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Unable to read episode inventory: {path} ({exc})")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to parse episode inventory: {path} ({exc})")

    if not isinstance(payload, dict):
        raise SystemExit(f"Episode inventory must be a JSON object: {path}")
    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        raise SystemExit(f"Episode inventory missing episodes list: {path}")

    episodes: list[dict[str, str]] = []
    seen_episode_keys: set[str] = set()
    for raw_episode in raw_episodes:
        if not isinstance(raw_episode, dict):
            continue
        episode_key = normalize_episode_key(raw_episode.get("episode_key") or raw_episode.get("guid"))
        title = normalize_title_key(str(raw_episode.get("title") or ""))
        if not episode_key or not title:
            continue
        if episode_key in seen_episode_keys:
            continue
        seen_episode_keys.add(episode_key)
        episodes.append(
            {
                "episode_key": episode_key,
                "title": title,
            }
        )
    return episodes


def load_existing_map(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print(f"Warning: could not parse existing spotify map; rebuilding from scratch: {path}", file=sys.stderr)
        return {}
    if not isinstance(payload, dict):
        print(f"Warning: spotify map is not a JSON object; rebuilding from scratch: {path}", file=sys.stderr)
        return {}
    return payload


def _normalize_existing_by_title(raw_by_title: Any) -> Dict[str, Tuple[str, str]]:
    normalized: Dict[str, Tuple[str, str]] = {}
    if not isinstance(raw_by_title, dict):
        return normalized
    for raw_title, raw_url in raw_by_title.items():
        if not isinstance(raw_title, str):
            continue
        if not isinstance(raw_url, str):
            continue
        title = normalize_title_key(raw_title)
        if not title:
            continue
        key = title.casefold()
        if key not in normalized:
            normalized[key] = (title, raw_url.strip())
    return normalized


def _normalize_existing_by_episode_key(raw_by_episode_key: Any) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    if not isinstance(raw_by_episode_key, dict):
        return normalized
    for raw_key, raw_url in raw_by_episode_key.items():
        episode_key = normalize_episode_key(raw_key)
        if not episode_key or not isinstance(raw_url, str):
            continue
        spotify_url = raw_url.strip()
        if not spotify_url:
            continue
        normalized[episode_key] = spotify_url
    return normalized


def parse_show_id_from_url(show_url: str) -> str | None:
    match = SPOTIFY_SHOW_URL_RE.match(str(show_url or "").strip())
    if not match:
        return None
    show_id = str(match.group("show_id") or "").strip()
    return show_id or None


def _spotify_client_access_token(client_id: str, client_secret: str) -> str:
    auth_token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    payload = urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    request = Request(
        "https://accounts.spotify.com/api/token",
        data=payload,
        headers={
            "Authorization": f"Basic {auth_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to fetch Spotify access token: {exc}") from exc
    access_token = str(body.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Spotify token response missing access_token.")
    return access_token


def fetch_spotify_show_episode_urls(*, show_id: str, client_id: str, client_secret: str, market: str) -> Dict[str, str]:
    access_token = _spotify_client_access_token(client_id, client_secret)
    headers = {"Authorization": f"Bearer {access_token}"}
    next_url = (
        f"https://api.spotify.com/v1/shows/{quote(show_id, safe='')}/episodes"
        f"?limit=50&offset=0&market={quote(str(market or 'DK').strip() or 'DK', safe='')}"
    )
    by_title: Dict[str, str] = {}

    while next_url:
        request = Request(next_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unable to fetch Spotify show episodes: {exc}") from exc

        items = payload.get("items")
        if not isinstance(items, list):
            break

        for item in items:
            if not isinstance(item, dict):
                continue
            title = normalize_title_key(str(item.get("name") or ""))
            if not title:
                continue
            spotify_url = str(((item.get("external_urls") or {}).get("spotify")) or "").strip()
            if not SPOTIFY_EPISODE_URL_RE.match(spotify_url):
                continue
            key = title.casefold()
            if key not in by_title:
                by_title[key] = spotify_url

        raw_next = payload.get("next")
        next_url = str(raw_next).strip() if isinstance(raw_next, str) and raw_next.strip() else ""

    return by_title


def _build_normalized_title_index(spotify_episode_by_title: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    ambiguous: set[str] = set()
    for raw_title, raw_url in spotify_episode_by_title.items():
        title = normalize_title_key(raw_title)
        if not title or not is_episode_spotify_url(raw_url):
            continue
        key = normalize_match_title(title)
        if not key:
            continue
        existing = normalized.get(key)
        if existing and normalize_title_key(existing) != normalize_title_key(raw_url):
            ambiguous.add(key)
            normalized.pop(key, None)
            continue
        if key not in ambiguous:
            normalized[key] = raw_url
    return normalized


def build_spotify_map(
    *,
    inventory_episodes: Iterable[dict[str, str]],
    existing_payload: Dict[str, Any],
    spotify_episode_by_title: Dict[str, str] | None,
    prune_stale: bool,
) -> tuple[Dict[str, str], Dict[str, str], list[dict[str, str]], Dict[str, int]]:
    existing_by_episode_key = _normalize_existing_by_episode_key(existing_payload.get("by_episode_key"))
    existing_by_title = _normalize_existing_by_title(existing_payload.get("by_rss_title"))
    updated_by_episode_key: Dict[str, str] = {}
    updated_by_rss_title: Dict[str, str] = {}
    unresolved_episodes: list[dict[str, str]] = []
    seen_episode_keys: set[str] = set()
    stats = {
        "preserved_existing": 0,
        "matched_show_episode": 0,
        "refreshed_from_show_episode": 0,
        "repaired_invalid": 0,
        "discarded_non_episode": 0,
        "carried_stale": 0,
        "unresolved": 0,
    }
    spotify_episode_by_title = spotify_episode_by_title or {}
    normalized_spotify_episode_by_title = _build_normalized_title_index(spotify_episode_by_title)

    for episode in inventory_episodes:
        if not isinstance(episode, dict):
            continue
        episode_key = normalize_episode_key(episode.get("episode_key"))
        title = normalize_title_key(episode.get("title") or "")
        if not episode_key or not title:
            continue
        if episode_key in seen_episode_keys:
            continue
        seen_episode_keys.add(episode_key)

        title_key = title.casefold()
        existing_url = existing_by_episode_key.get(episode_key, "")
        existing_from_title = existing_by_title.get(title_key)
        if not existing_url and existing_from_title:
            existing_url = existing_from_title[1]
        existing_is_episode = is_episode_spotify_url(existing_url)

        mapped_episode_url = spotify_episode_by_title.get(title_key)
        if not mapped_episode_url:
            mapped_episode_url = normalized_spotify_episode_by_title.get(normalize_match_title(title))
        if mapped_episode_url and is_episode_spotify_url(mapped_episode_url):
            updated_by_episode_key[episode_key] = mapped_episode_url
            updated_by_rss_title[title] = mapped_episode_url
            if existing_is_episode and normalize_title_key(existing_url) != normalize_title_key(mapped_episode_url):
                stats["refreshed_from_show_episode"] += 1
            elif existing_is_episode:
                stats["preserved_existing"] += 1
            else:
                stats["matched_show_episode"] += 1
            continue

        if existing_is_episode:
            updated_by_episode_key[episode_key] = existing_url
            updated_by_rss_title[title] = existing_url
            stats["preserved_existing"] += 1
            continue

        if existing_url:
            if existing_url.startswith("https://open.spotify.com/"):
                stats["discarded_non_episode"] += 1
            else:
                stats["repaired_invalid"] += 1
        unresolved_episodes.append({"episode_key": episode_key, "title": title})
        stats["unresolved"] += 1

    if not prune_stale:
        for episode_key, url in existing_by_episode_key.items():
            if episode_key in seen_episode_keys:
                continue
            if not is_episode_spotify_url(url):
                continue
            updated_by_episode_key[episode_key] = url
            stats["carried_stale"] += 1

    ordered_by_episode_key = dict(sorted(updated_by_episode_key.items(), key=lambda item: item[0]))
    ordered_by_rss_title = dict(sorted(updated_by_rss_title.items(), key=lambda item: item[0].casefold()))
    return ordered_by_episode_key, ordered_by_rss_title, unresolved_episodes, stats


def write_spotify_map(path: Path, payload: Dict[str, Any], *, dry_run: bool) -> bool:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    changed = rendered != existing
    if dry_run or not changed:
        return changed
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(rendered, encoding="utf-8")
    temp_path.replace(path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        help="Source episode_inventory.json path. If omitted, derive from --rss.",
    )
    parser.add_argument(
        "--rss",
        type=Path,
        help="Legacy source RSS path used only to derive the sibling episode inventory path.",
    )
    parser.add_argument("--spotify-map", required=True, type=Path, help="spotify_map.json path.")
    parser.add_argument(
        "--subject-slug",
        default="personlighedspsykologi",
        help="Subject slug to persist in spotify_map.json.",
    )
    parser.add_argument(
        "--spotify-show-url",
        help="Spotify show URL (https://open.spotify.com/show/<id>) used for direct episode URL matching.",
    )
    parser.add_argument(
        "--spotify-client-id",
        help="Spotify API client id (or use SPOTIFY_CLIENT_ID env var).",
    )
    parser.add_argument(
        "--spotify-client-secret",
        help="Spotify API client secret (or use SPOTIFY_CLIENT_SECRET env var).",
    )
    parser.add_argument(
        "--spotify-market",
        default="DK",
        help="Spotify market for episode lookup (default: DK).",
    )
    parser.add_argument(
        "--prune-stale",
        action="store_true",
        help="Drop existing map entries not present in the current RSS.",
    )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help=(
            "Allow unresolved RSS titles and still write direct episode mappings for resolved titles. "
            "Unresolved titles are reported and stored in unresolved_rss_titles."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files.")
    args = parser.parse_args()

    subject_slug = str(args.subject_slug or "").strip().lower()
    if not SUBJECT_SLUG_RE.match(subject_slug):
        raise SystemExit("--subject-slug must match ^[a-z0-9-]+$")

    inventory_arg = args.inventory.expanduser().resolve() if args.inventory else None
    rss_arg = args.rss.expanduser().resolve() if args.rss else None
    if inventory_arg is None and rss_arg is None:
        raise SystemExit("Either --inventory or --rss must be provided.")
    inventory_path = inventory_arg or _inventory_path_from_rss_path(rss_arg)
    spotify_map_path = args.spotify_map.expanduser().resolve()

    inventory_episodes = load_inventory_episodes(inventory_path)
    existing_payload = load_existing_map(spotify_map_path)
    spotify_episode_by_title: Dict[str, str] = {}
    show_url = str(args.spotify_show_url or "").strip()
    show_id = parse_show_id_from_url(show_url) if show_url else None
    if show_url and not show_id:
        raise SystemExit(f"--spotify-show-url is invalid: {show_url}")
    if show_id:
        spotify_client_id = str(args.spotify_client_id or os.getenv("SPOTIFY_CLIENT_ID") or "").strip()
        spotify_client_secret = str(
            args.spotify_client_secret or os.getenv("SPOTIFY_CLIENT_SECRET") or ""
        ).strip()
        if spotify_client_id and spotify_client_secret:
            try:
                spotify_episode_by_title = fetch_spotify_show_episode_urls(
                    show_id=show_id,
                    client_id=spotify_client_id,
                    client_secret=spotify_client_secret,
                    market=str(args.spotify_market or "DK"),
                )
            except RuntimeError as exc:
                raise SystemExit(f"Spotify show lookup failed: {exc}")
        else:
            raise SystemExit(
                "Spotify show URL provided but API credentials are missing; "
                "set --spotify-client-id/--spotify-client-secret or env vars."
            )
    by_episode_key, by_rss_title, unresolved_episodes, stats = build_spotify_map(
        inventory_episodes=inventory_episodes,
        existing_payload=existing_payload,
        spotify_episode_by_title=spotify_episode_by_title,
        prune_stale=bool(args.prune_stale),
    )

    if unresolved_episodes:
        print(
            "Error: could not map all inventory episodes to direct Spotify episode URLs. "
            "No search fallback is allowed.",
            file=sys.stderr,
        )
        preview_limit = 30
        for episode in unresolved_episodes[:preview_limit]:
            print(f"- {episode['episode_key']}: {episode['title']}", file=sys.stderr)
        remaining = len(unresolved_episodes) - preview_limit
        if remaining > 0:
            print(f"... and {remaining} more", file=sys.stderr)
        if not args.allow_unresolved:
            return 2
        print(
            "Continuing because --allow-unresolved is set; unresolved episodes were omitted from by_episode_key.",
            file=sys.stderr,
        )

    payload = {
        "version": 2,
        "subject_slug": subject_slug,
        "by_episode_key": by_episode_key,
        "by_rss_title": by_rss_title,
        "unresolved_episode_keys": [episode["episode_key"] for episode in unresolved_episodes],
        "unresolved_rss_titles": [episode["title"] for episode in unresolved_episodes],
    }
    changed = write_spotify_map(spotify_map_path, payload, dry_run=bool(args.dry_run))

    print(f"Inventory path: {inventory_path}")
    print(f"Inventory episodes: {len(inventory_episodes)}")
    print(f"Map entries: {len(by_episode_key)}")
    print(f"Preserved existing: {stats['preserved_existing']}")
    print(f"Matched show episodes: {stats['matched_show_episode']}")
    print(f"Refreshed from show episodes: {stats['refreshed_from_show_episode']}")
    print(f"Unresolved episodes: {stats['unresolved']}")
    print(f"Repaired invalid links: {stats['repaired_invalid']}")
    print(f"Discarded non-episode Spotify links: {stats['discarded_non_episode']}")
    print(f"Carried stale entries: {stats['carried_stale']}")
    if args.dry_run:
        print(f"Dry run: {'changes detected' if changed else 'no changes'}")
    else:
        print(f"Updated file: {'yes' if changed else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
