#!/usr/bin/env python3
"""Validate lecture-slide podcast coverage in the Personlighedspsykologi episode inventory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slides-catalog",
        default="shows/personlighedspsykologi-en/slides_catalog.json",
        help="Path to slides_catalog.json.",
    )
    parser.add_argument(
        "--inventory",
        default="shows/personlighedspsykologi-en/episode_inventory.json",
        help="Path to the generated episode inventory.",
    )
    parser.add_argument(
        "--rss",
        default="shows/personlighedspsykologi-en/feeds/rss.xml",
        help="Legacy fallback path to the generated RSS feed.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print problems but exit successfully instead of failing.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_feed_module(root: Path):
    module_path = root / "podcast-tools" / "gdrive_podcast_feed.py"
    spec = importlib.util.spec_from_file_location("gdrive_podcast_feed", module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load feed module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonicalize_lecture_key(value: str) -> str:
    match = re.fullmatch(r"\s*W?0*(\d{1,2})L0*(\d+)\s*", value, re.IGNORECASE)
    if not match:
        return value.strip().upper()
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def slide_catalog_lecture_keys(raw_slide: dict[str, object]) -> list[str]:
    lecture_keys: list[str] = []
    primary = canonicalize_lecture_key(str(raw_slide.get("lecture_key") or ""))
    if re.fullmatch(r"W\d{2}L\d+", primary):
        lecture_keys.append(primary)
    raw_lecture_keys = raw_slide.get("lecture_keys")
    if isinstance(raw_lecture_keys, list):
        for value in raw_lecture_keys:
            lecture_key = canonicalize_lecture_key(str(value or ""))
            if re.fullmatch(r"W\d{2}L\d+", lecture_key) and lecture_key not in lecture_keys:
                lecture_keys.append(lecture_key)
    return lecture_keys


def iter_slide_expectations(
    payload: dict,
    *,
    feed_module,
) -> Iterable[tuple[str, str, str]]:
    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        raise SystemExit("slides_catalog.json is missing a 'slides' list.")
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        subcategory = str(raw_slide.get("subcategory") or "").strip().lower()
        title = str(raw_slide.get("title") or "").strip()
        if subcategory not in {"lecture", "exercise", "seminar"} or not title:
            continue
        subject = feed_module._normalize_slide_subject(title)
        if not subject:
            continue
        for lecture_key in slide_catalog_lecture_keys(raw_slide):
            yield lecture_key, subcategory, subject


def inventory_titles(path: Path) -> set[str]:
    payload = load_json(path)
    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        raise SystemExit(f"Invalid episode inventory: missing episodes list in {path}")
    titles: set[str] = set()
    for item in raw_episodes:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title:
            titles.add(title)
    return titles


def rss_titles(path: Path) -> set[str]:
    tree = ET.parse(path)
    channel = tree.getroot().find("channel")
    if channel is None:
        raise SystemExit(f"Invalid RSS feed: missing channel in {path}")
    titles: set[str] = set()
    for item in channel.findall("item"):
        title_node = item.find("title")
        if title_node is None or not title_node.text:
            continue
        titles.add(title_node.text.strip())
    return titles


def build_expected_title(lecture_key: str, audio_label: str, subject: str) -> str:
    match = re.fullmatch(r"W(\d{2})L(\d+)", lecture_key)
    if not match:
        raise SystemExit(f"Invalid lecture key in slides catalog: {lecture_key}")
    week_number = int(match.group(1))
    lecture_number = int(match.group(2))
    return (
        f"Uge {week_number}, Forelæsning {lecture_number} · "
        f"{audio_label} · Forelæsningsslides - {subject}"
    )


def main() -> int:
    args = parse_args()
    root = repo_root()
    slides_catalog_path = (root / args.slides_catalog).resolve()
    inventory_path = (root / args.inventory).resolve()
    rss_path = (root / args.rss).resolve()
    feed_module = load_feed_module(root)
    slide_payload = load_json(slides_catalog_path)
    if inventory_path.exists():
        titles = inventory_titles(inventory_path)
    else:
        titles = rss_titles(rss_path)

    missing_full: list[str] = []
    missing_short: list[str] = []
    unexpected_nonlecture_short: list[str] = []
    unexpected_seminar_full: list[str] = []

    for lecture_key, subcategory, subject in iter_slide_expectations(
        slide_payload,
        feed_module=feed_module,
    ):
        full_title = build_expected_title(lecture_key, "Podcast", subject)
        short_title = build_expected_title(lecture_key, "Kort podcast", subject)
        if subcategory == "lecture":
            if full_title not in titles:
                missing_full.append(full_title)
            if short_title not in titles:
                missing_short.append(short_title)
            continue
        if subcategory == "seminar":
            if full_title in titles:
                unexpected_seminar_full.append(full_title)
            if short_title in titles:
                unexpected_nonlecture_short.append(short_title)
            continue
        if short_title in titles:
            unexpected_nonlecture_short.append(short_title)

    problems: list[str] = []
    if missing_full:
        problems.append("Missing lecture slide full podcasts:\n- " + "\n- ".join(missing_full))
    if missing_short:
        problems.append("Missing lecture slide short podcasts:\n- " + "\n- ".join(missing_short))
    if unexpected_nonlecture_short:
        problems.append(
            "Unexpected non-lecture slide short podcasts:\n- "
            + "\n- ".join(unexpected_nonlecture_short)
        )
    if unexpected_seminar_full:
        problems.append(
            "Unexpected seminar slide full podcasts:\n- "
            + "\n- ".join(unexpected_seminar_full)
        )

    if problems:
        message = "\n\n".join(problems)
        if args.warn_only:
            print(message)
            return 0
        raise SystemExit(message)

    print("Validated Personlighedspsykologi slide short coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
