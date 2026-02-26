#!/usr/bin/env python3
"""Auto-populate spotify_map.json from RSS titles."""

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
from xml.etree import ElementTree


MULTISPACE_RE = re.compile(r"\s+")
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
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


def is_episode_spotify_url(value: str) -> bool:
    url = str(value or "").strip()
    if not url:
        return False
    return bool(SPOTIFY_EPISODE_URL_RE.match(url))


def load_rss_titles(rss_path: Path) -> list[str]:
    try:
        payload = rss_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Unable to read RSS source: {rss_path} ({exc})")

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"Unable to parse RSS source: {rss_path} ({exc})")

    channel = root.find("channel")
    if channel is None:
        raise SystemExit(f"RSS source missing <channel>: {rss_path}")

    titles: list[str] = []
    seen: set[str] = set()
    for item in channel.findall("item"):
        title = normalize_title_key(str(item.findtext("title") or ""))
        if not title:
            continue
        normalized = normalize_title_key(title).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        titles.append(title)
    return titles


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


def build_spotify_map(
    *,
    rss_titles: Iterable[str],
    existing_payload: Dict[str, Any],
    spotify_episode_by_title: Dict[str, str] | None,
    prune_stale: bool,
) -> tuple[Dict[str, str], list[str], Dict[str, int]]:
    existing_by_title = _normalize_existing_by_title(existing_payload.get("by_rss_title"))
    updated: Dict[str, str] = {}
    unresolved_titles: list[str] = []
    seen_keys: set[str] = set()
    stats = {
        "preserved_existing": 0,
        "matched_show_episode": 0,
        "repaired_invalid": 0,
        "discarded_non_episode": 0,
        "carried_stale": 0,
        "unresolved": 0,
    }
    spotify_episode_by_title = spotify_episode_by_title or {}

    for rss_title in rss_titles:
        title = normalize_title_key(rss_title)
        if not title:
            continue
        key = title.casefold()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        existing = existing_by_title.get(key)
        existing_url = existing[1] if existing else ""
        existing_is_episode = is_episode_spotify_url(existing_url)

        if existing and existing_is_episode:
            updated[title] = existing[1]
            stats["preserved_existing"] += 1
            continue

        mapped_episode_url = spotify_episode_by_title.get(key)
        if mapped_episode_url and is_episode_spotify_url(mapped_episode_url):
            updated[title] = mapped_episode_url
            stats["matched_show_episode"] += 1
            continue

        if existing and existing[1]:
            if existing_is_episode:
                pass
            elif existing_url:
                if existing_url.startswith("https://open.spotify.com/"):
                    stats["discarded_non_episode"] += 1
                else:
                    stats["repaired_invalid"] += 1
        unresolved_titles.append(title)
        stats["unresolved"] += 1

    if not prune_stale:
        for key, (title, url) in existing_by_title.items():
            if key in seen_keys:
                continue
            if not is_episode_spotify_url(url):
                continue
            updated[title] = url
            stats["carried_stale"] += 1

    ordered = dict(sorted(updated.items(), key=lambda item: item[0].casefold()))
    return ordered, unresolved_titles, stats


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
    parser.add_argument("--rss", required=True, type=Path, help="Source RSS file path.")
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

    rss_path = args.rss.expanduser().resolve()
    spotify_map_path = args.spotify_map.expanduser().resolve()

    rss_titles = load_rss_titles(rss_path)
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
    by_rss_title, unresolved_titles, stats = build_spotify_map(
        rss_titles=rss_titles,
        existing_payload=existing_payload,
        spotify_episode_by_title=spotify_episode_by_title,
        prune_stale=bool(args.prune_stale),
    )

    if unresolved_titles:
        print(
            "Error: could not map all RSS titles to direct Spotify episode URLs. "
            "No search fallback is allowed.",
            file=sys.stderr,
        )
        preview_limit = 30
        for title in unresolved_titles[:preview_limit]:
            print(f"- {title}", file=sys.stderr)
        remaining = len(unresolved_titles) - preview_limit
        if remaining > 0:
            print(f"... and {remaining} more", file=sys.stderr)
        if not args.allow_unresolved:
            return 2
        print(
            "Continuing because --allow-unresolved is set; unresolved titles were omitted from by_rss_title.",
            file=sys.stderr,
        )

    payload = {
        "version": 1,
        "subject_slug": subject_slug,
        "by_rss_title": by_rss_title,
        "unresolved_rss_titles": unresolved_titles,
    }
    changed = write_spotify_map(spotify_map_path, payload, dry_run=bool(args.dry_run))

    print(f"RSS titles: {len(rss_titles)}")
    print(f"Map entries: {len(by_rss_title)}")
    print(f"Preserved existing: {stats['preserved_existing']}")
    print(f"Matched show episodes: {stats['matched_show_episode']}")
    print(f"Unresolved RSS titles: {stats['unresolved']}")
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
