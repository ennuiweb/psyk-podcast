#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

CONFIG_TAG_RE = re.compile(r"\s+\{[^{}]+\}(?=\.[^.]+$)")
SHORT_PREFIX_RE = re.compile(r"^\[(?:Short|Brief)\]\s+", re.IGNORECASE)
TTS_PREFIX_RE = re.compile(r"^\[TTS\]\s+", re.IGNORECASE)
WEEK_KEY_RE = re.compile(r"\bW\d+L\d+\b", re.IGNORECASE)
TAG_TOKEN_RE = re.compile(r"([a-z0-9_]+)=([^}\s]+)", re.IGNORECASE)


def strip_cfg_tag_from_filename(name: str) -> str:
    value = CONFIG_TAG_RE.sub("", name)
    return Path(value).name


def strip_leading_variant_prefix(name: str) -> str:
    value = SHORT_PREFIX_RE.sub("", name.strip())
    value = TTS_PREFIX_RE.sub("", value)
    return value.strip()


def parse_config_tags(name: str) -> dict[str, str]:
    match = re.search(r"\{([^{}]+)\}(?=\.[^.]+$)", name)
    if not match:
        return {}
    parsed: dict[str, str] = {}
    for key, value in TAG_TOKEN_RE.findall(match.group(1)):
        parsed[key] = value
    return parsed


def classify_episode(source_name: str) -> str:
    value = source_name.strip()
    if not value:
        return "unknown"
    if TTS_PREFIX_RE.match(value):
        return "tts"
    if SHORT_PREFIX_RE.match(value):
        return "short"
    if "Alle kilder (undtagen slides)" in value:
        return "weekly_readings_only"
    if "Slide lecture:" in value or "Slide exercise:" in value:
        return "single_slide"
    return "single_reading"


def extract_lecture_key(text: str) -> str | None:
    match = WEEK_KEY_RE.search(text)
    return match.group(0).upper() if match else None


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return value.strip("_") or "sample"


def canonical_source_name(source_name: str) -> str:
    return strip_cfg_tag_from_filename(source_name).strip()


def logical_episode_id(source_name: str) -> str:
    prompt_type = classify_episode(source_name)
    lecture_key = (extract_lecture_key(source_name) or "unknown").lower()
    canonical = canonical_source_name(source_name)
    trimmed = strip_leading_variant_prefix(canonical)
    trimmed = trimmed.replace(".mp3", "")
    trimmed = re.sub(r"^w\d+l\d+\s*-\s*", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"^slide\s+(lecture|exercise):\s*", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"^alle kilder \(undtagen slides\)$", "alle_kilder_undtagen_slides", trimmed, flags=re.IGNORECASE)
    return f"{prompt_type}__{lecture_key}__{slugify(trimmed)}"
