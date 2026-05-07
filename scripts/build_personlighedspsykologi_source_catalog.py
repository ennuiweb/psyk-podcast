#!/usr/bin/env python3
"""Build a deterministic raw-source catalog for Personlighedspsykologi.

This script inventories local course files but does not extract or semantically
analyse reading text. Source understanding is delegated to Gemini with the
actual PDFs attached.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) in sys.path:
    sys.path.remove(str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import prompting
from notebooklm_queue.json_artifact_utils import render_json, write_json_stably
from notebooklm_queue.source_intelligence_policy import (
    evidence_origin_for_source,
    load_source_intelligence_policy,
)

logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)


DEFAULT_SUBJECT_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi"
)
DEFAULT_OUTPUT = "shows/personlighedspsykologi-en/source_catalog.json"
DEFAULT_CONTENT_MANIFEST = "shows/personlighedspsykologi-en/content_manifest.json"
DEFAULT_SLIDES_CATALOG = "shows/personlighedspsykologi-en/slides_catalog.json"
DEFAULT_READING_KEY = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_PROMPT_CONFIG = "notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json"
DEFAULT_POLICY_PATH = "shows/personlighedspsykologi-en/source_intelligence_policy.json"

TOKEN_SPLIT_RE = re.compile(r"\b\w+\b", re.UNICODE)
LANGUAGE_TOKEN_RE = re.compile(r"\b[a-zA-ZæøåÆØÅ]+\b", re.UNICODE)

SOURCE_CATALOG_VERSION = 1
PDF_METADATA_TOKEN_ESTIMATE_PER_PAGE = 650

_DANISH_HINTS = {
    "og",
    "ikke",
    "det",
    "den",
    "der",
    "for",
    "til",
    "med",
    "som",
    "af",
    "på",
    "eller",
    "personlighed",
    "forelæsning",
    "psykologi",
}
_ENGLISH_HINTS = {
    "the",
    "and",
    "that",
    "with",
    "from",
    "this",
    "personality",
    "psychology",
    "lecture",
    "method",
    "self",
}


def _repo_root() -> Path:
    return REPO_ROOT


def _load_reading_sync_module(repo_root: Path):
    script_path = repo_root / "scripts" / "sync_personlighedspsykologi_readings_to_droplet.py"
    spec = importlib.util.spec_from_file_location(
        "sync_personlighedspsykologi_readings_to_droplet",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relativize(path: Path, base: Path) -> str:
    return str(path.resolve().relative_to(base.resolve()))


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_values(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _estimate_tokens(*, char_count: int, word_count: int) -> int:
    if char_count <= 0 and word_count <= 0:
        return 0
    return max(int(math.ceil(char_count / 4.0)), int(math.ceil(word_count * 1.3)))


def _estimate_tokens_from_pages(page_count: int | None) -> int:
    if not page_count or page_count <= 0:
        return 0
    return int(page_count) * PDF_METADATA_TOKEN_ESTIMATE_PER_PAGE


def _guess_language(*, title: str, sample_text: str) -> str:
    sample = f"{title}\n{sample_text}".strip().lower()
    if not sample:
        return "unknown"
    tokens = LANGUAGE_TOKEN_RE.findall(sample)
    if not tokens:
        return "unknown"
    danish_score = sum(1 for token in tokens if token in _DANISH_HINTS)
    english_score = sum(1 for token in tokens if token in _ENGLISH_HINTS)
    if any(char in sample for char in "æøå"):
        danish_score += 2
    if danish_score == 0 and english_score == 0:
        return "unknown"
    return "da" if danish_score >= english_score else "en"


def _length_band(*, page_count: int | None, estimated_tokens: int) -> str:
    if page_count and page_count > 0:
        if page_count <= 10:
            return "short"
        if page_count <= 25:
            return "medium"
        return "long"
    if estimated_tokens <= 1500:
        return "short"
    if estimated_tokens <= 5000:
        return "medium"
    return "long"


def _has_summary(summary: object) -> bool:
    if not isinstance(summary, dict):
        return False
    summary_lines = summary.get("summary_lines")
    key_points = summary.get("key_points")
    return bool(summary_lines or key_points)


def _extract_file_metrics(path: Path) -> tuple[dict[str, Any], str]:
    suffix = path.suffix.lower()
    if suffix != ".pdf":
        return (
            {
                "page_count": None,
                "text_char_count": 0,
                "estimated_word_count": 0,
                "estimated_token_count": 0,
                "text_extraction_status": "unsupported",
            },
            "",
        )

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:  # pragma: no cover - defensive against damaged PDFs
        return (
            {
                "page_count": None,
                "text_char_count": 0,
                "estimated_word_count": 0,
                "estimated_token_count": 0,
                "text_extraction_status": f"read_error:{type(exc).__name__}",
            },
            "",
        )

    page_count = len(reader.pages)
    estimated_token_count = _estimate_tokens_from_pages(page_count)
    return (
        {
            "page_count": page_count,
            "text_char_count": 0,
            "estimated_word_count": 0,
            "estimated_token_count": estimated_token_count,
            "text_extraction_status": "metadata_only_no_local_text_extraction",
        },
        "",
    )


def _aggregate_file_metrics(metrics_by_file: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics_by_file:
        return {
            "page_count": None,
            "text_char_count": 0,
            "estimated_word_count": 0,
            "estimated_token_count": 0,
            "text_extraction_status": "missing_source",
        }
    page_values = [item.get("page_count") for item in metrics_by_file if item.get("page_count") is not None]
    statuses = [str(item.get("text_extraction_status") or "") for item in metrics_by_file if item.get("text_extraction_status")]
    if len(set(statuses)) == 1:
        status = statuses[0]
    else:
        status = "mixed_metadata_statuses"
    if len(metrics_by_file) > 1 and status == "metadata_only_no_local_text_extraction":
        status = "metadata_only_multi_file_no_local_text_extraction"
    return {
        "page_count": sum(int(value or 0) for value in page_values) if page_values else None,
        "text_char_count": sum(int(item.get("text_char_count") or 0) for item in metrics_by_file),
        "estimated_word_count": sum(int(item.get("estimated_word_count") or 0) for item in metrics_by_file),
        "estimated_token_count": sum(int(item.get("estimated_token_count") or 0) for item in metrics_by_file),
        "text_extraction_status": status,
    }


def _existing_sidecar_paths(
    *,
    candidates: list[Path],
    subject_root: Path,
) -> list[str]:
    existing: list[str] = []
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            existing.append(_relativize(candidate, subject_root))
    return existing


def _load_meta_prompting(prompt_config_path: Path) -> dict[str, Any]:
    payload = _load_json(prompt_config_path)
    raw = payload.get("meta_prompting") if isinstance(payload, dict) else {}
    return prompting.normalize_meta_prompting(raw)


def build_source_catalog(
    *,
    repo_root: Path,
    subject_root: Path,
    output_path: Path,
    content_manifest_path: Path,
    slides_catalog_path: Path,
    reading_key_path: Path,
    prompt_config_path: Path,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _load_json(content_manifest_path)
    slides_catalog = _load_json(slides_catalog_path)
    meta_prompting = _load_meta_prompting(prompt_config_path)
    policy = load_source_intelligence_policy(policy_path)

    reading_sync = _load_reading_sync_module(repo_root)
    reading_entries = reading_sync.parse_reading_key(reading_key_path)
    week_dir_index = reading_sync.index_week_dirs(subject_root / "Readings")
    reading_resolutions, unresolved_readings = reading_sync.resolve_entries(reading_entries, week_dir_index)
    resolution_by_key: dict[str, list[Any]] = {}
    for item in reading_resolutions:
        resolution_by_key.setdefault(item.entry.reading_key, []).append(item)
    expected_source_counts_by_key = Counter(item.reading_key for item in reading_entries)

    lectures = manifest.get("lectures")
    if not isinstance(lectures, list):
        raise SystemExit(f"content manifest is missing lectures: {content_manifest_path}")
    slide_items = slides_catalog.get("slides")
    if not isinstance(slide_items, list):
        raise SystemExit(f"slides catalog is missing slides: {slides_catalog_path}")

    lecture_summary_map: dict[str, dict[str, Any]] = {}
    flat_sources: list[dict[str, Any]] = []
    slide_counts_by_lecture: Counter[str] = Counter()
    warnings: list[str] = list(unresolved_readings)

    slide_key_map: dict[str, dict[str, Any]] = {}
    for slide in slide_items:
        if not isinstance(slide, dict):
            continue
        slide_key = str(slide.get("slide_key") or "").strip()
        if not slide_key:
            continue
        slide_key_map[slide_key] = slide
        lecture_keys = slide.get("lecture_keys")
        if isinstance(lecture_keys, list) and lecture_keys:
            for lecture_key in lecture_keys:
                slide_counts_by_lecture[str(lecture_key).strip().upper()] += 1
        else:
            lecture_key = str(slide.get("lecture_key") or "").strip().upper()
            if lecture_key:
                slide_counts_by_lecture[lecture_key] += 1

    lecture_week_sidecars: dict[str, list[str]] = {}
    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        week_dirs = week_dir_index.get(lecture_key, [])
        existing: list[str] = []
        for week_dir in week_dirs:
            existing.extend(
                _existing_sidecar_paths(
                    candidates=prompting._week_prompt_sidecar_candidates(week_dir, lecture_key, meta_prompting),
                    subject_root=subject_root,
                )
            )
        lecture_week_sidecars[lecture_key] = sorted(dict.fromkeys(existing))

    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        lecture_title = str(lecture.get("lecture_title") or "").strip()
        sequence_index = int(lecture.get("sequence_index") or 0)
        lecture_summary_present = _has_summary(lecture.get("summary"))
        week_sidecars = lecture_week_sidecars.get(lecture_key, [])

        readings = lecture.get("readings")
        if not isinstance(readings, list):
            readings = []
        lecture_missing_count = 0

        for reading in readings:
            if not isinstance(reading, dict):
                continue
            reading_key = str(reading.get("reading_key") or "").strip()
            reading_title = str(reading.get("reading_title") or "").strip()
            resolutions = sorted(
                resolution_by_key.get(reading_key, []),
                key=lambda item: str(item.entry.source_filename).casefold(),
            )
            expected_source_count = int(expected_source_counts_by_key.get(reading_key, 0))
            source_paths = [item.source_path for item in resolutions if item.source_path.exists() and item.source_path.is_file()]
            source_exists = expected_source_count > 0 and len(source_paths) == expected_source_count
            source_filenames = [str(item.entry.source_filename) for item in resolutions]
            if source_exists:
                subject_relative_paths = [_relativize(path, subject_root) for path in source_paths]
                file_sizes = [path.stat().st_size for path in source_paths]
                file_hashes = [_sha256_file(path) for path in source_paths]
                sha256 = file_hashes[0] if len(file_hashes) == 1 else _sha256_values(file_hashes)
                file_size = sum(file_sizes)
                metrics_by_file: list[dict[str, Any]] = []
                file_parts: list[dict[str, Any]] = []
                sidecars_by_file: list[str] = []
                for source_path, source_filename, subject_relative_path, file_hash, file_size_bytes in zip(
                    source_paths,
                    source_filenames,
                    subject_relative_paths,
                    file_hashes,
                    file_sizes,
                    strict=True,
                ):
                    file_metrics, _sample_text = _extract_file_metrics(source_path)
                    metrics_by_file.append(file_metrics)
                    file_parts.append(
                        {
                            "source_filename": source_filename,
                            "subject_relative_path": subject_relative_path,
                            "sha256": file_hash,
                            "size_bytes": file_size_bytes,
                            **file_metrics,
                        }
                    )
                    sidecars_by_file.extend(
                        _existing_sidecar_paths(
                            candidates=prompting._source_prompt_sidecar_candidates(source_path, meta_prompting),
                            subject_root=subject_root,
                        )
                    )
                subject_relative_path = subject_relative_paths[0] if subject_relative_paths else None
                metrics = _aggregate_file_metrics(metrics_by_file)
                sample_text = ""
                sidecars = sorted(dict.fromkeys(sidecars_by_file))
            else:
                subject_relative_path = None
                subject_relative_paths = []
                file_parts = []
                file_size = None
                sha256 = None
                metrics = {
                    "page_count": None,
                    "text_char_count": 0,
                    "estimated_word_count": 0,
                    "estimated_token_count": 0,
                    "text_extraction_status": "missing_source",
                }
                sample_text = ""
                sidecars = []
                lecture_missing_count += 1

            if source_exists:
                missing_reason = None
            elif expected_source_count and resolutions:
                missing_reason = "partially_unresolved_source_paths"
            elif reading.get("is_missing"):
                missing_reason = "manifest_marked_missing"
            else:
                missing_reason = "unresolved_source_path"

            source_entry = {
                "source_id": reading_key,
                "source_kind": "reading",
                "source_family": "reading",
                "lecture_key": lecture_key,
                "lecture_keys": [lecture_key],
                "sequence_index": int(reading.get("sequence_index") or 0),
                "title": reading_title,
                "source_filename": reading.get("source_filename"),
                "subject_relative_path": subject_relative_path,
                "source_exists": source_exists,
                "missing_reason": missing_reason,
                "language_guess": _guess_language(title=reading_title, sample_text=sample_text),
                "length_band": _length_band(
                    page_count=metrics["page_count"],
                    estimated_tokens=metrics["estimated_token_count"],
                ),
                "priority_signals": {
                    "is_grundbog": "grundbog" in reading_title.lower(),
                    "has_manual_summary": _has_summary(reading.get("summary")),
                    "has_prompt_analysis_sidecar": bool(sidecars),
                    "lecture_has_week_analysis_sidecar": bool(week_sidecars),
                },
                "evidence_origin": evidence_origin_for_source(
                    source_family="reading",
                    is_grundbog="grundbog" in reading_title.lower(),
                    policy=policy,
                ),
                "file": {
                    "sha256": sha256,
                    "size_bytes": file_size,
                    **metrics,
                },
                "prompt_analysis_sidecars": sidecars,
            }
            if len(source_filenames) > 1:
                source_entry["source_filenames"] = source_filenames
            if len(subject_relative_paths) > 1:
                source_entry["subject_relative_paths"] = subject_relative_paths
            if len(file_parts) > 1:
                source_entry["file"]["parts"] = file_parts
            flat_sources.append(source_entry)

        lecture_summary_map[lecture_key] = {
            "lecture_key": lecture_key,
            "sequence_index": sequence_index,
            "lecture_title": lecture_title,
            "reading_count": len(readings),
            "slide_count": int(slide_counts_by_lecture.get(lecture_key, 0)),
            "missing_source_count": lecture_missing_count,
            "lecture_summary_present": lecture_summary_present,
            "week_prompt_analysis_present": bool(week_sidecars),
            "week_prompt_analysis_sidecars": week_sidecars,
        }

    for slide in slide_items:
        if not isinstance(slide, dict):
            continue
        slide_key = str(slide.get("slide_key") or "").strip()
        if not slide_key:
            continue
        lecture_key = str(slide.get("lecture_key") or "").strip().upper()
        lecture_keys_raw = slide.get("lecture_keys")
        if isinstance(lecture_keys_raw, list) and lecture_keys_raw:
            lecture_keys = [str(item).strip().upper() for item in lecture_keys_raw if str(item).strip()]
        else:
            lecture_keys = [lecture_key] if lecture_key else []

        local_relative = str(slide.get("local_relative_path") or "").strip()
        source_path = (subject_root / local_relative).resolve() if local_relative else None
        source_exists = bool(source_path and source_path.exists() and source_path.is_file())
        if source_exists and source_path is not None:
            subject_relative_path = _relativize(source_path, subject_root)
            file_size = source_path.stat().st_size
            sha256 = _sha256_file(source_path)
            metrics, sample_text = _extract_file_metrics(source_path)
            sidecars = _existing_sidecar_paths(
                candidates=prompting._source_prompt_sidecar_candidates(source_path, meta_prompting),
                subject_root=subject_root,
            )
            missing_reason = None
        else:
            subject_relative_path = None
            file_size = None
            sha256 = None
            metrics = {
                "page_count": None,
                "text_char_count": 0,
                "estimated_word_count": 0,
                "estimated_token_count": 0,
                "text_extraction_status": "missing_source",
            }
            sample_text = ""
            sidecars = []
            missing_reason = "missing_local_relative_path" if not local_relative else "local_source_missing"
            warnings.append(f"{slide_key} | {local_relative or '<blank>'} | {missing_reason}")
            for key in lecture_keys:
                lecture_info = lecture_summary_map.get(key)
                if lecture_info is not None:
                    lecture_info["missing_source_count"] += 1

        title = str(slide.get("title") or "").strip()
        subcategory = str(slide.get("subcategory") or "").strip().lower() or "unknown"
        primary_lecture_key = lecture_keys[0] if lecture_keys else lecture_key
        week_sidecars = lecture_week_sidecars.get(primary_lecture_key, [])

        flat_sources.append(
            {
                "source_id": slide_key,
                "source_kind": "slide",
                "source_family": f"{subcategory}_slide",
                "lecture_key": primary_lecture_key,
                "lecture_keys": lecture_keys,
                "sequence_index": None,
                "title": title,
                "source_filename": slide.get("source_filename"),
                "subject_relative_path": subject_relative_path,
                "source_exists": source_exists,
                "missing_reason": missing_reason,
                "slide_subcategory": subcategory,
                "language_guess": _guess_language(title=title, sample_text=sample_text),
                "length_band": _length_band(
                    page_count=metrics["page_count"],
                    estimated_tokens=metrics["estimated_token_count"],
                ),
                "priority_signals": {
                    "is_grundbog": False,
                    "has_manual_summary": False,
                    "has_prompt_analysis_sidecar": bool(sidecars),
                    "lecture_has_week_analysis_sidecar": bool(week_sidecars),
                },
                "evidence_origin": evidence_origin_for_source(
                    source_family=f"{subcategory}_slide",
                    is_grundbog=False,
                    policy=policy,
                ),
                "file": {
                    "sha256": sha256,
                    "size_bytes": file_size,
                    **metrics,
                },
                "prompt_analysis_sidecars": sidecars,
                "catalog_relative_path": slide.get("relative_path"),
                "catalog_local_relative_path": local_relative or None,
            }
        )

    flat_sources.sort(
        key=lambda item: (
            int(item["lecture_key"][1:3]) if item.get("lecture_key") else 0,
            int(str(item["lecture_key"]).split("L", 1)[1]) if item.get("lecture_key") else 0,
            {"reading": 0, "slide": 1}.get(str(item.get("source_kind")), 9),
            str(item.get("title") or "").casefold(),
        )
    )

    lecture_entries = [
        lecture_summary_map[key]
        for key in sorted(
            lecture_summary_map.keys(),
            key=lambda value: (
                int(value[1:3]),
                int(value.split("L", 1)[1]),
            ),
        )
    ]

    reading_count = sum(1 for item in flat_sources if item["source_kind"] == "reading")
    slide_count = sum(1 for item in flat_sources if item["source_kind"] == "slide")
    missing_count = sum(1 for item in flat_sources if not item["source_exists"])
    manual_summary_count = sum(1 for item in flat_sources if item["priority_signals"]["has_manual_summary"])
    source_sidecar_count = sum(1 for item in flat_sources if item["priority_signals"]["has_prompt_analysis_sidecar"])
    total_pages = sum(int(item["file"]["page_count"] or 0) for item in flat_sources)
    total_estimated_tokens = sum(int(item["file"]["estimated_token_count"] or 0) for item in flat_sources)
    source_family_counts = Counter(str(item.get("source_family") or "") for item in flat_sources)
    extraction_status_counts = Counter(str(item["file"]["text_extraction_status"]) for item in flat_sources)

    return {
        "version": SOURCE_CATALOG_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "build_inputs": {
            "content_manifest": _display_path(content_manifest_path, repo_root),
            "slides_catalog": _display_path(slides_catalog_path, repo_root),
            "reading_key": _display_path(reading_key_path, repo_root),
            "prompt_config": _display_path(prompt_config_path, repo_root),
            "source_intelligence_policy": _display_path(policy_path, repo_root) if policy_path else None,
            "subject_root_name": subject_root.name,
        },
        "policy": policy,
        "stats": {
            "lecture_count": len(lecture_entries),
            "source_count": len(flat_sources),
            "reading_count": reading_count,
            "slide_count": slide_count,
            "missing_source_count": missing_count,
            "manual_source_summary_count": manual_summary_count,
            "lecture_summary_count": sum(1 for entry in lecture_entries if entry["lecture_summary_present"]),
            "source_prompt_analysis_count": source_sidecar_count,
            "lecture_week_prompt_analysis_count": sum(
                1 for entry in lecture_entries if entry["week_prompt_analysis_present"]
            ),
            "total_pages": total_pages,
            "total_estimated_tokens": total_estimated_tokens,
            "source_family_counts": dict(sorted(source_family_counts.items())),
            "text_extraction_status_counts": dict(sorted(extraction_status_counts.items())),
        },
        "lectures": lecture_entries,
        "sources": flat_sources,
        "warnings": warnings,
    }


def _write_catalog(path: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    stored_catalog, _ = write_json_stably(path, catalog)
    if not isinstance(stored_catalog, dict):
        raise RuntimeError(f"stored catalog is not an object: {path}")
    return stored_catalog


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Catalog JSON path.")
    parser.add_argument("--content-manifest", default=DEFAULT_CONTENT_MANIFEST, help="content_manifest.json path.")
    parser.add_argument("--slides-catalog", default=DEFAULT_SLIDES_CATALOG, help="slides_catalog.json path.")
    parser.add_argument("--reading-key", default=DEFAULT_READING_KEY, help="reading-file-key.md path.")
    parser.add_argument("--prompt-config", default=DEFAULT_PROMPT_CONFIG, help="Prompt config path.")
    parser.add_argument("--policy-path", default=DEFAULT_POLICY_PATH, help="source_intelligence_policy.json path.")
    parser.add_argument(
        "--subject-root",
        default=DEFAULT_SUBJECT_ROOT,
        help="Canonical local source root containing Readings/ and slide folders.",
    )
    parser.add_argument("--stdout", action="store_true", help="Print the generated JSON to stdout.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
    content_manifest_path = (
        (repo_root / args.content_manifest).resolve()
        if not Path(args.content_manifest).is_absolute()
        else Path(args.content_manifest).resolve()
    )
    slides_catalog_path = (
        (repo_root / args.slides_catalog).resolve()
        if not Path(args.slides_catalog).is_absolute()
        else Path(args.slides_catalog).resolve()
    )
    reading_key_path = (
        (repo_root / args.reading_key).resolve()
        if not Path(args.reading_key).is_absolute()
        else Path(args.reading_key).resolve()
    )
    prompt_config_path = (
        (repo_root / args.prompt_config).resolve()
        if not Path(args.prompt_config).is_absolute()
        else Path(args.prompt_config).resolve()
    )
    policy_path = (
        (repo_root / args.policy_path).resolve()
        if not Path(args.policy_path).is_absolute()
        else Path(args.policy_path).resolve()
    )
    subject_root = Path(args.subject_root).expanduser().resolve()

    catalog = build_source_catalog(
        repo_root=repo_root,
        subject_root=subject_root,
        output_path=output_path,
        content_manifest_path=content_manifest_path,
        slides_catalog_path=slides_catalog_path,
        reading_key_path=reading_key_path,
        prompt_config_path=prompt_config_path,
        policy_path=policy_path,
    )
    catalog = _write_catalog(output_path, catalog)
    rendered = render_json(catalog)
    if args.stdout:
        print(rendered, end="")
    print(
        f"Wrote {output_path} "
        f"(sources={catalog['stats']['source_count']} missing={catalog['stats']['missing_source_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
