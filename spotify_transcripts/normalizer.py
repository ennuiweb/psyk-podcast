"""Normalize raw Spotify transcript payloads into repo-owned artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import NORMALIZED_TRANSCRIPT_VERSION


class TranscriptSchemaError(RuntimeError):
    """Raised when a Spotify transcript payload no longer matches expected shapes."""


@dataclass(frozen=True)
class NormalizedTranscript:
    payload: dict[str, Any]
    vtt: str


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_text(node: Any) -> str:
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, dict):
        for key in ("text", "displayText", "sentence"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = _extract_text(value)
                if nested:
                    return nested
    return ""


def _extract_translation(node: Any) -> list[dict[str, str]]:
    translations: list[dict[str, str]] = []
    if isinstance(node, list):
        for item in node:
            translations.extend(_extract_translation(item))
        return translations
    if not isinstance(node, dict):
        return translations

    text = _extract_text(node)
    locale = _coerce_text(node.get("locale") or node.get("language") or node.get("lang"))
    if text and locale:
        translations.append({"locale": locale, "text": text})
    for key in ("translation", "translations", "translatedText"):
        nested = node.get(key)
        if nested is not None:
            translations.extend(_extract_translation(nested))
    return translations


def _sections_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("section", "sections"):
        sections = payload.get(key)
        if isinstance(sections, list):
            return [item for item in sections if isinstance(item, dict)]
    return []


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _format_vtt_timestamp(total_ms: int) -> str:
    hours, remainder = divmod(max(total_ms, 0), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def _build_vtt(segments: list[dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for index, segment in enumerate(segments, start=1):
        start_ms = int(segment["start_ms"])
        end_ms = int(segment["end_ms"])
        lines.append(str(index))
        lines.append(f"{_format_vtt_timestamp(start_ms)} --> {_format_vtt_timestamp(end_ms)}")
        lines.append(str(segment["text"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def normalize_transcript_payload(
    *,
    episode_key: str,
    title: str,
    spotify_url: str,
    raw_payload: dict[str, Any],
) -> NormalizedTranscript:
    sections = _sections_from_payload(raw_payload)
    if not sections:
        raise TranscriptSchemaError("Spotify transcript payload is missing a section list.")

    normalized_segments: list[dict[str, Any]] = []
    translation_locales: set[str] = set()
    for index, section in enumerate(sections):
        start_ms = _coerce_int(_first_present(section, "startMs", "start_ms"))
        end_ms = _coerce_int(_first_present(section, "endMs", "end_ms"))
        title_text = _extract_text(section.get("title"))
        sentence_text = _extract_text(section.get("text"))
        text = sentence_text or title_text
        if start_ms is None or not text:
            continue
        translations = _extract_translation(section.get("text"))
        for translation in translations:
            locale = _coerce_text(translation.get("locale"))
            if locale:
                translation_locales.add(locale)
        normalized_segments.append(
            {
                "index": index,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
                "section_title": title_text or None,
                "translations": translations or [],
            }
        )

    if not normalized_segments:
        raise TranscriptSchemaError("Spotify transcript payload had sections, but none contained usable timing + text.")

    for index, segment in enumerate(normalized_segments):
        if segment["end_ms"] is None:
            next_start = (
                normalized_segments[index + 1]["start_ms"]
                if index + 1 < len(normalized_segments)
                else segment["start_ms"] + 1_000
            )
            segment["end_ms"] = max(next_start, segment["start_ms"] + 1_000)
        elif int(segment["end_ms"]) <= int(segment["start_ms"]):
            segment["end_ms"] = int(segment["start_ms"]) + 1_000

    payload = {
        "version": NORMALIZED_TRANSCRIPT_VERSION,
        "source": "spotify",
        "source_schema": "spotify-transcript-read-along",
        "episode_key": episode_key,
        "title": title,
        "spotify_url": spotify_url,
        "episode_name": _coerce_text(raw_payload.get("episodeName") or raw_payload.get("episode_name")) or title,
        "language": _coerce_text(raw_payload.get("language") or raw_payload.get("locale")) or None,
        "available_translations": sorted(translation_locales),
        "segment_count": len(normalized_segments),
        "segments": normalized_segments,
    }
    return NormalizedTranscript(payload=payload, vtt=_build_vtt(normalized_segments))
