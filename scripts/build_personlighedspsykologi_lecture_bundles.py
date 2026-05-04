#!/usr/bin/env python3
"""Build lecture-bundle artifacts for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = "shows/personlighedspsykologi-en/lecture_bundles"
DEFAULT_SOURCE_CATALOG = "shows/personlighedspsykologi-en/source_catalog.json"
DEFAULT_CONTENT_MANIFEST = "shows/personlighedspsykologi-en/content_manifest.json"
DEFAULT_SUBJECT_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi"
)
LECTURE_BUNDLE_VERSION = 1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _course_stage(sequence_index: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    ratio = sequence_index / total
    if ratio <= 0.2:
        return "opening"
    if ratio <= 0.5:
        return "early-middle"
    if ratio <= 0.8:
        return "late-middle"
    return "closing"


def _normalize_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _has_manual_summary(summary: object) -> bool:
    if not isinstance(summary, dict):
        return False
    return bool(_normalize_text_list(summary.get("summary_lines")) or _normalize_text_list(summary.get("key_points")))


def _read_sidecar_entries(*, relative_paths: list[str], subject_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative_path in relative_paths:
        path = (subject_root / relative_path).resolve()
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        entries.append(
            {
                "relative_path": relative_path,
                "content": content,
                "char_count": len(content),
            }
        )
    return entries


def _priority_base(source: dict[str, Any]) -> int:
    family = str(source.get("source_family") or "")
    if family == "reading":
        return 100
    if family == "lecture_slide":
        return 72
    if family == "seminar_slide":
        return 58
    if family == "exercise_slide":
        return 48
    return 40


def _length_bonus(length_band: str) -> int:
    if length_band == "long":
        return 12
    if length_band == "medium":
        return 6
    return 0


def _priority_score(source: dict[str, Any]) -> tuple[int, list[str]]:
    if not source.get("source_exists"):
        return 0, ["missing source"]
    score = _priority_base(source)
    reasons: list[str] = [str(source.get("source_family") or "source")]
    priority = source.get("priority_signals") if isinstance(source.get("priority_signals"), dict) else {}
    if priority.get("is_grundbog"):
        score += 12
        reasons.append("grundbog")
    if priority.get("has_manual_summary"):
        score += 10
        reasons.append("manual summary")
    if priority.get("has_prompt_analysis_sidecar"):
        score += 8
        reasons.append("analysis sidecar")
    if priority.get("lecture_has_week_analysis_sidecar"):
        score += 4
        reasons.append("week analysis")
    length_band = str(source.get("length_band") or "")
    bonus = _length_bonus(length_band)
    if bonus:
        score += bonus
        reasons.append(f"{length_band} source")
    tokens = int(((source.get("file") or {}) if isinstance(source.get("file"), dict) else {}).get("estimated_token_count") or 0)
    if tokens >= 7000:
        score += 8
        reasons.append("very substantial")
    elif tokens >= 3000:
        score += 4
        reasons.append("substantial")
    return score, reasons


def _priority_band(score: int) -> str:
    if score >= 120:
        return "core"
    if score >= 95:
        return "primary"
    if score >= 70:
        return "supporting"
    if score > 0:
        return "contextual"
    return "missing"


def _dominant_language(sources: list[dict[str, Any]]) -> str:
    weighted = Counter()
    for source in sources:
        language = str(source.get("language_guess") or "unknown")
        token_count = int(((source.get("file") or {}) if isinstance(source.get("file"), dict) else {}).get("estimated_token_count") or 0)
        weighted[language] += max(token_count, 1)
    if not weighted:
        return "unknown"
    return weighted.most_common(1)[0][0]


def _enriched_source(
    *,
    source: dict[str, Any],
    reading_summary: dict[str, Any] | None,
    subject_root: Path,
) -> dict[str, Any]:
    score, reasons = _priority_score(source)
    sidecar_paths = [str(item) for item in source.get("prompt_analysis_sidecars") or [] if str(item).strip()]
    sidecars = _read_sidecar_entries(relative_paths=sidecar_paths, subject_root=subject_root)
    file_meta = source.get("file") if isinstance(source.get("file"), dict) else {}
    return {
        "source_id": source["source_id"],
        "title": source["title"],
        "source_kind": source["source_kind"],
        "source_family": source["source_family"],
        "source_filename": source.get("source_filename"),
        "subject_relative_path": source.get("subject_relative_path"),
        "source_exists": bool(source.get("source_exists")),
        "missing_reason": source.get("missing_reason"),
        "sequence_index": source.get("sequence_index"),
        "language_guess": source.get("language_guess"),
        "length_band": source.get("length_band"),
        "slide_subcategory": source.get("slide_subcategory"),
        "priority_score": score,
        "priority_band": _priority_band(score),
        "priority_reasons": reasons,
        "priority_signals": source.get("priority_signals") or {},
        "file": {
            "page_count": file_meta.get("page_count"),
            "estimated_token_count": file_meta.get("estimated_token_count"),
            "estimated_word_count": file_meta.get("estimated_word_count"),
            "text_char_count": file_meta.get("text_char_count"),
            "text_extraction_status": file_meta.get("text_extraction_status"),
            "sha256": file_meta.get("sha256"),
            "size_bytes": file_meta.get("size_bytes"),
        },
        "summary": {
            "present": _has_manual_summary(reading_summary),
            "summary_lines": _normalize_text_list((reading_summary or {}).get("summary_lines")),
            "key_points": _normalize_text_list((reading_summary or {}).get("key_points")),
        },
        "analysis": {
            "present": bool(sidecars),
            "sidecars": sidecars,
        },
    }


def build_lecture_bundles(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    content_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_catalog = _load_json(source_catalog_path)
    content_manifest = _load_json(content_manifest_path)

    catalog_lectures = source_catalog.get("lectures")
    if not isinstance(catalog_lectures, list):
        raise SystemExit(f"source catalog is missing lectures: {source_catalog_path}")
    catalog_sources = source_catalog.get("sources")
    if not isinstance(catalog_sources, list):
        raise SystemExit(f"source catalog is missing sources: {source_catalog_path}")
    manifest_lectures = content_manifest.get("lectures")
    if not isinstance(manifest_lectures, list):
        raise SystemExit(f"content manifest is missing lectures: {content_manifest_path}")

    catalog_lecture_by_key = {
        str(item.get("lecture_key") or "").strip().upper(): item
        for item in catalog_lectures
        if isinstance(item, dict) and str(item.get("lecture_key") or "").strip()
    }
    manifest_lecture_by_key = {
        str(item.get("lecture_key") or "").strip().upper(): item
        for item in manifest_lectures
        if isinstance(item, dict) and str(item.get("lecture_key") or "").strip()
    }

    sources_by_lecture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in catalog_sources:
        if not isinstance(source, dict):
            continue
        lecture_keys = source.get("lecture_keys")
        if isinstance(lecture_keys, list) and lecture_keys:
            normalized_keys = [str(item).strip().upper() for item in lecture_keys if str(item).strip()]
        else:
            normalized_keys = [str(source.get("lecture_key") or "").strip().upper()]
        for lecture_key in normalized_keys:
            if lecture_key:
                sources_by_lecture[lecture_key].append(source)

    ordered_lecture_keys = [
        str(item.get("lecture_key") or "").strip().upper()
        for item in sorted(
            catalog_lectures,
            key=lambda entry: int(entry.get("sequence_index") or 0),
        )
        if str(item.get("lecture_key") or "").strip()
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    expected_output_names = {f"{lecture_key}.json" for lecture_key in ordered_lecture_keys}
    expected_output_names.add("index.json")
    for existing in output_dir.glob("*.json"):
        if existing.name not in expected_output_names:
            existing.unlink()
    bundle_index_entries: list[dict[str, Any]] = []

    for offset, lecture_key in enumerate(ordered_lecture_keys):
        catalog_lecture = catalog_lecture_by_key[lecture_key]
        manifest_lecture = manifest_lecture_by_key.get(lecture_key, {})
        lecture_sources = list(sources_by_lecture.get(lecture_key, []))
        readings_manifest = manifest_lecture.get("readings") if isinstance(manifest_lecture.get("readings"), list) else []
        reading_summary_by_key = {
            str(item.get("reading_key") or "").strip(): (item.get("summary") if isinstance(item.get("summary"), dict) else {})
            for item in readings_manifest
            if isinstance(item, dict)
        }
        lecture_summary = manifest_lecture.get("summary") if isinstance(manifest_lecture.get("summary"), dict) else {}
        lecture_warnings = [str(item).strip() for item in manifest_lecture.get("warnings") or [] if str(item).strip()]

        enriched_sources = [
            _enriched_source(
                source=source,
                reading_summary=reading_summary_by_key.get(str(source.get("source_id") or "").strip()),
                subject_root=subject_root,
            )
            for source in lecture_sources
        ]
        enriched_sources.sort(
            key=lambda item: (
                -int(item["priority_score"]),
                {"reading": 0, "slide": 1}.get(str(item.get("source_kind")), 9),
                str(item.get("title") or "").casefold(),
            )
        )

        grouped_sources = {
            "readings": [item for item in enriched_sources if item["source_family"] == "reading"],
            "lecture_slides": [item for item in enriched_sources if item["source_family"] == "lecture_slide"],
            "seminar_slides": [item for item in enriched_sources if item["source_family"] == "seminar_slide"],
            "exercise_slides": [item for item in enriched_sources if item["source_family"] == "exercise_slide"],
        }
        week_sidecars = _read_sidecar_entries(
            relative_paths=[str(item) for item in catalog_lecture.get("week_prompt_analysis_sidecars") or [] if str(item).strip()],
            subject_root=subject_root,
        )
        missing_sources = [
            {
                "source_id": item["source_id"],
                "title": item["title"],
                "source_kind": item["source_kind"],
                "missing_reason": item["missing_reason"],
            }
            for item in enriched_sources
            if not item["source_exists"]
        ]
        summary_present_count = sum(1 for item in grouped_sources["readings"] if item["summary"]["present"])
        analysis_present_count = sum(1 for item in enriched_sources if item["analysis"]["present"])
        total_tokens = sum(int((item.get("file") or {}).get("estimated_token_count") or 0) for item in enriched_sources)
        total_pages = sum(int((item.get("file") or {}).get("page_count") or 0) for item in enriched_sources)
        source_family_counts = Counter(item["source_family"] for item in enriched_sources)

        previous_key = ordered_lecture_keys[offset - 1] if offset > 0 else None
        next_key = ordered_lecture_keys[offset + 1] if offset + 1 < len(ordered_lecture_keys) else None
        previous_lecture = catalog_lecture_by_key.get(previous_key or "")
        next_lecture = catalog_lecture_by_key.get(next_key or "")

        likely_core_sources = [item["source_id"] for item in enriched_sources if item["priority_band"] in {"core", "primary"}][:4]
        likely_supporting_sources = [item["source_id"] for item in enriched_sources if item["priority_band"] == "supporting"][:6]

        bundle_status = "ready"
        readiness_issues: list[str] = []
        if missing_sources:
            bundle_status = "partial"
            readiness_issues.append("missing_sources")
        if not _has_manual_summary(lecture_summary):
            bundle_status = "partial"
            readiness_issues.append("missing_lecture_summary")
        if not grouped_sources["readings"]:
            bundle_status = "partial"
            readiness_issues.append("no_readings")
        if summary_present_count < len(grouped_sources["readings"]):
            readiness_issues.append("incomplete_reading_summary_coverage")

        lecture_title = str(catalog_lecture.get("lecture_title") or "").strip()
        bundle_payload = {
            "version": LECTURE_BUNDLE_VERSION,
            "subject_slug": str(source_catalog.get("subject_slug") or "personlighedspsykologi"),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "lecture_key": lecture_key,
            "lecture_title": lecture_title,
            "sequence_index": int(catalog_lecture.get("sequence_index") or 0),
            "course_position": {
                "index": offset + 1,
                "total_lectures": len(ordered_lecture_keys),
                "stage": _course_stage(offset + 1, len(ordered_lecture_keys)),
                "previous_lecture_key": previous_key,
                "previous_lecture_title": str((previous_lecture or {}).get("lecture_title") or "").strip() or None,
                "next_lecture_key": next_key,
                "next_lecture_title": str((next_lecture or {}).get("lecture_title") or "").strip() or None,
            },
            "bundle_status": bundle_status,
            "readiness_issues": readiness_issues,
            "lecture_summary": {
                "present": _has_manual_summary(lecture_summary),
                "summary_lines": _normalize_text_list(lecture_summary.get("summary_lines")),
                "key_points": _normalize_text_list(lecture_summary.get("key_points")),
            },
            "teaching_context": {
                "lecture_slide_titles": [item["title"] for item in grouped_sources["lecture_slides"]],
                "seminar_slide_titles": [item["title"] for item in grouped_sources["seminar_slides"]],
                "exercise_slide_titles": [item["title"] for item in grouped_sources["exercise_slides"]],
            },
            "source_counts": {
                "total_sources": len(enriched_sources),
                "readings": len(grouped_sources["readings"]),
                "lecture_slides": len(grouped_sources["lecture_slides"]),
                "seminar_slides": len(grouped_sources["seminar_slides"]),
                "exercise_slides": len(grouped_sources["exercise_slides"]),
                "missing_sources": len(missing_sources),
                "manual_reading_summaries_present": summary_present_count,
                "source_analyses_present": analysis_present_count,
                "total_pages": total_pages,
                "total_estimated_tokens": total_tokens,
                "source_family_counts": dict(sorted(source_family_counts.items())),
            },
            "source_intelligence": {
                "dominant_language": _dominant_language(enriched_sources),
                "week_analysis": {
                    "present": bool(week_sidecars),
                    "sidecars": week_sidecars,
                },
                "missing_sources": missing_sources,
                "likely_core_sources": likely_core_sources,
                "likely_supporting_sources": likely_supporting_sources,
            },
            "source_priority_order": [
                {
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "source_family": item["source_family"],
                    "priority_score": item["priority_score"],
                    "priority_band": item["priority_band"],
                }
                for item in enriched_sources
            ],
            "sources": grouped_sources,
            "manifest_warnings": lecture_warnings,
        }

        bundle_path = output_dir / f"{lecture_key}.json"
        _write_json(bundle_path, bundle_payload)
        bundle_index_entries.append(
            {
                "lecture_key": lecture_key,
                "lecture_title": lecture_title,
                "relative_path": bundle_path.name,
                "bundle_status": bundle_status,
                "readiness_issues": readiness_issues,
                "source_counts": bundle_payload["source_counts"],
                "likely_core_sources": likely_core_sources,
            }
        )

    index_payload = {
        "version": LECTURE_BUNDLE_VERSION,
        "subject_slug": str(source_catalog.get("subject_slug") or "personlighedspsykologi"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "build_inputs": {
            "source_catalog": _display_path(source_catalog_path, repo_root),
            "content_manifest": _display_path(content_manifest_path, repo_root),
            "subject_root_name": subject_root.name,
        },
        "stats": {
            "lecture_count": len(bundle_index_entries),
            "ready_bundle_count": sum(1 for entry in bundle_index_entries if entry["bundle_status"] == "ready"),
            "partial_bundle_count": sum(1 for entry in bundle_index_entries if entry["bundle_status"] != "ready"),
            "bundle_with_week_analysis_count": sum(
                1 for lecture_key in ordered_lecture_keys if catalog_lecture_by_key[lecture_key].get("week_prompt_analysis_present")
            ),
            "bundle_with_missing_sources_count": sum(
                1 for entry in bundle_index_entries if entry["source_counts"]["missing_sources"] > 0
            ),
        },
        "bundles": bundle_index_entries,
    }
    _write_json(output_dir / "index.json", index_payload)
    return index_payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for lecture bundle JSON files.")
    parser.add_argument("--source-catalog", default=DEFAULT_SOURCE_CATALOG, help="Path to source_catalog.json.")
    parser.add_argument("--content-manifest", default=DEFAULT_CONTENT_MANIFEST, help="Path to content_manifest.json.")
    parser.add_argument(
        "--subject-root",
        default=DEFAULT_SUBJECT_ROOT,
        help="Canonical local source root for reading/slide sidecars.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    output_dir = (repo_root / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir).resolve()
    source_catalog_path = (
        (repo_root / args.source_catalog).resolve()
        if not Path(args.source_catalog).is_absolute()
        else Path(args.source_catalog).resolve()
    )
    content_manifest_path = (
        (repo_root / args.content_manifest).resolve()
        if not Path(args.content_manifest).is_absolute()
        else Path(args.content_manifest).resolve()
    )
    subject_root = Path(args.subject_root).expanduser().resolve()

    index_payload = build_lecture_bundles(
        repo_root=repo_root,
        subject_root=subject_root,
        source_catalog_path=source_catalog_path,
        content_manifest_path=content_manifest_path,
        output_dir=output_dir,
    )
    print(
        f"Wrote {output_dir} "
        f"(lectures={index_payload['stats']['lecture_count']} partial={index_payload['stats']['partial_bundle_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
