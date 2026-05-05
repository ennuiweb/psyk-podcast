from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_INTELLIGENCE_POLICY: dict[str, Any] = {
    "version": 1,
    "subject_slug": "personlighedspsykologi",
    "interpretation": {
        "evidence_origins": {
            "reading": "reading_grounded",
            "grundbog_reading": "textbook_framing",
            "lecture_slide": "lecture_framed",
            "seminar_slide": "seminar_applied",
            "exercise_slide": "exercise_clarified",
        }
    },
    "lecture_bundle": {
        "priority_base": {
            "reading": 100,
            "lecture_slide": 72,
            "seminar_slide": 58,
            "exercise_slide": 48,
            "default": 40,
        },
        "bonus_weights": {
            "grundbog": 12,
            "manual_summary": 10,
            "analysis_sidecar": 8,
            "week_analysis": 4,
            "very_substantial_tokens": 8,
            "substantial_tokens": 4,
        },
        "length_bonus": {
            "long": 12,
            "medium": 6,
        },
    },
    "source_weighting": {
        "family_weights": {
            "reading": 40,
            "lecture_slide": 18,
            "seminar_slide": 14,
            "exercise_slide": 10,
        },
        "priority_band_weights": {
            "core": 18,
            "primary": 14,
            "supporting": 10,
            "contextual": 6,
            "missing": 0,
        },
        "length_band_weights": {
            "long": 6,
            "medium": 3,
        },
        "bonus_weights": {
            "manual_summary": 6,
            "analysis_sidecar": 4,
            "week_analysis_context": 3,
            "likely_core_source": 10,
            "very_substantial_tokens": 6,
            "substantial_tokens": 3,
            "textbook_framing": 4,
            "lecture_framed": 2,
            "seminar_applied": 1,
        },
    },
}


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_source_intelligence_policy(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_SOURCE_INTELLIGENCE_POLICY)
    return _merge_dict(DEFAULT_SOURCE_INTELLIGENCE_POLICY, raw)


def load_source_intelligence_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return copy.deepcopy(DEFAULT_SOURCE_INTELLIGENCE_POLICY)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_SOURCE_INTELLIGENCE_POLICY)
    return normalize_source_intelligence_policy(raw)


def evidence_origin_for_source(
    *,
    source_family: str,
    is_grundbog: bool,
    policy: dict[str, Any],
) -> str:
    interpretation = policy.get("interpretation") if isinstance(policy.get("interpretation"), dict) else {}
    evidence_origins = (
        interpretation.get("evidence_origins")
        if isinstance(interpretation.get("evidence_origins"), dict)
        else {}
    )
    if source_family == "reading" and is_grundbog:
        return str(evidence_origins.get("grundbog_reading") or "textbook_framing")
    return str(evidence_origins.get(source_family) or "reading_grounded")
