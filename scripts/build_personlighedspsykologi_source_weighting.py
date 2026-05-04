#!/usr/bin/env python3
"""Build source-weighting artifacts for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LECTURE_BUNDLE_DIR = "shows/personlighedspsykologi-en/lecture_bundles"
DEFAULT_GLOSSARY_PATH = "shows/personlighedspsykologi-en/course_glossary.json"
DEFAULT_THEORY_MAP_PATH = "shows/personlighedspsykologi-en/course_theory_map.json"
DEFAULT_OUTPUT_PATH = "shows/personlighedspsykologi-en/source_weighting.json"
DEFAULT_STALENESS_PATH = "shows/personlighedspsykologi-en/source_intelligence_staleness.json"
SOURCE_WEIGHTING_VERSION = 1

FAMILY_WEIGHTS = {
    "reading": 40,
    "lecture_slide": 18,
    "seminar_slide": 14,
    "exercise_slide": 10,
}
PRIORITY_WEIGHTS = {
    "core": 18,
    "primary": 14,
    "supporting": 10,
    "contextual": 6,
    "missing": 0,
}
LENGTH_WEIGHTS = {
    "long": 6,
    "medium": 3,
}
BONUS_WEIGHTS = {
    "manual_summary": 6,
    "analysis_sidecar": 4,
    "week_analysis_context": 3,
    "likely_core_source": 10,
    "very_substantial_tokens": 6,
    "substantial_tokens": 3,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _lecture_bundle_paths(lecture_bundle_dir: Path, lecture_bundle_index: dict[str, Any]) -> list[Path]:
    bundle_paths: list[Path] = []
    for entry in lecture_bundle_index.get("bundles", []):
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("relative_path") or "").strip()
        if relative_path:
            bundle_paths.append(lecture_bundle_dir / relative_path)
    return bundle_paths


def _signature_for_paths(paths: list[Path]) -> str:
    return _sha256_bytes("\n".join(_sha256_file(path) for path in paths).encode("utf-8"))


def _weight_band(score: int) -> str:
    if score >= 90:
        return "anchor"
    if score >= 70:
        return "major"
    if score >= 50:
        return "supporting"
    if score > 0:
        return "contextual"
    return "missing"


def _bundle_source_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    sources = bundle.get("sources")
    if not isinstance(sources, dict):
        return entries
    for source_group in sources.values():
        if not isinstance(source_group, list):
            continue
        for source in source_group:
            if isinstance(source, dict):
                entries.append(source)
    return entries


def build_source_weighting(
    *,
    repo_root: Path,
    lecture_bundle_dir: Path,
    glossary_path: Path,
    theory_map_path: Path,
    output_path: Path,
    staleness_path: Path,
) -> dict[str, Any]:
    lecture_bundle_index = _load_json(lecture_bundle_dir / "index.json")
    glossary_payload = _load_json(glossary_path)
    theory_map_payload = _load_json(theory_map_path)
    lecture_bundle_paths = _lecture_bundle_paths(lecture_bundle_dir, lecture_bundle_index)

    bundle_by_key: dict[str, dict[str, Any]] = {}
    for entry, bundle_path in zip(lecture_bundle_index.get("bundles", []), lecture_bundle_paths):
        if not isinstance(entry, dict):
            continue
        lecture_key = str(entry.get("lecture_key") or "").strip().upper()
        if lecture_key:
            bundle_by_key[lecture_key] = _load_json(bundle_path)

    source_to_terms: dict[str, list[str]] = {}
    term_to_theories: dict[str, list[str]] = {}
    for term in glossary_payload.get("terms", []):
        if not isinstance(term, dict):
            continue
        term_id = str(term.get("term_id") or "").strip()
        if not term_id:
            continue
        term_to_theories[term_id] = _normalize_list(term.get("linked_theories"))
        for source_id in _normalize_list(term.get("source_ids")):
            source_to_terms.setdefault(source_id, []).append(term_id)

    source_to_theories: dict[str, list[str]] = {}
    for source_id, term_ids in source_to_terms.items():
        theory_ids: list[str] = []
        for term_id in term_ids:
            theory_ids.extend(term_to_theories.get(term_id, []))
        source_to_theories[source_id] = sorted(set(theory_ids))

    lectures_payload: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []

    for lecture_key in [
        str(entry.get("lecture_key") or "").strip().upper()
        for entry in lecture_bundle_index.get("bundles", [])
        if isinstance(entry, dict)
    ]:
        bundle = bundle_by_key.get(lecture_key)
        if not bundle:
            continue
        likely_core_sources = set(_normalize_list((bundle.get("source_intelligence") or {}).get("likely_core_sources")))
        week_analysis_present = bool(((bundle.get("source_intelligence") or {}).get("week_analysis") or {}).get("present"))
        lecture_sources: list[dict[str, Any]] = []
        for source in _bundle_source_entries(bundle):
            source_id = str(source.get("source_id") or "").strip()
            if not source_id:
                continue
            if not source.get("source_exists"):
                score = 0
                breakdown = {
                    "family_base": 0,
                    "priority_band": 0,
                    "length_band": 0,
                    "manual_summary": 0,
                    "analysis_sidecar": 0,
                    "week_analysis_context": 0,
                    "likely_core_source": 0,
                    "token_volume": 0,
                    "term_coverage": 0,
                    "theory_coverage": 0,
                }
            else:
                family = str(source.get("source_family") or "")
                priority_band = str(source.get("priority_band") or "")
                length_band = str(source.get("length_band") or "")
                token_count = int((source.get("file") or {}).get("estimated_token_count") or 0)
                term_ids = sorted(set(source_to_terms.get(source_id, [])))
                theory_ids = sorted(set(source_to_theories.get(source_id, [])))
                breakdown = {
                    "family_base": FAMILY_WEIGHTS.get(family, 8),
                    "priority_band": PRIORITY_WEIGHTS.get(priority_band, 0),
                    "length_band": LENGTH_WEIGHTS.get(length_band, 0),
                    "manual_summary": BONUS_WEIGHTS["manual_summary"] if ((source.get("summary") or {}).get("present")) else 0,
                    "analysis_sidecar": BONUS_WEIGHTS["analysis_sidecar"] if ((source.get("analysis") or {}).get("present")) else 0,
                    "week_analysis_context": BONUS_WEIGHTS["week_analysis_context"] if week_analysis_present and family == "reading" else 0,
                    "likely_core_source": BONUS_WEIGHTS["likely_core_source"] if source_id in likely_core_sources else 0,
                    "token_volume": BONUS_WEIGHTS["very_substantial_tokens"] if token_count >= 10000 else BONUS_WEIGHTS["substantial_tokens"] if token_count >= 5000 else 0,
                    "term_coverage": min(12, len(term_ids) * 3),
                    "theory_coverage": min(12, len(theory_ids) * 4),
                }
                score = sum(breakdown.values())

            term_ids = sorted(set(source_to_terms.get(source_id, [])))
            theory_ids = sorted(set(source_to_theories.get(source_id, [])))
            weighted_entry = {
                "source_id": source_id,
                "lecture_key": lecture_key,
                "lecture_title": str(bundle.get("lecture_title") or "").strip(),
                "title": str(source.get("title") or "").strip(),
                "source_family": str(source.get("source_family") or ""),
                "priority_band": str(source.get("priority_band") or ""),
                "length_band": str(source.get("length_band") or ""),
                "weight_score": score,
                "weight_band": _weight_band(score),
                "term_ids": term_ids,
                "theory_ids": theory_ids,
                "breakdown": breakdown,
            }
            lecture_sources.append(weighted_entry)
            all_sources.append(weighted_entry)

        lecture_sources.sort(key=lambda item: (-int(item["weight_score"]), str(item["title"]).casefold()))
        lectures_payload.append(
            {
                "lecture_key": lecture_key,
                "lecture_title": str(bundle.get("lecture_title") or "").strip(),
                "ranked_sources": lecture_sources,
                "anchor_source_ids": [item["source_id"] for item in lecture_sources if item["weight_band"] == "anchor"],
                "major_source_ids": [item["source_id"] for item in lecture_sources if item["weight_band"] == "major"],
            }
        )

    all_sources.sort(key=lambda item: (-int(item["weight_score"]), str(item["source_id"]).casefold()))
    payload = {
        "version": SOURCE_WEIGHTING_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": _now(),
        "build_inputs": {
            "lecture_bundle_index": _display_path(lecture_bundle_dir / "index.json", repo_root),
            "course_glossary": _display_path(glossary_path, repo_root),
            "course_theory_map": _display_path(theory_map_path, repo_root),
        },
        "weighting_policy": {
            "family_weights": FAMILY_WEIGHTS,
            "priority_band_weights": PRIORITY_WEIGHTS,
            "length_band_weights": LENGTH_WEIGHTS,
            "bonus_weights": BONUS_WEIGHTS,
        },
        "stats": {
            "lecture_count": len(lectures_payload),
            "source_count": len(all_sources),
            "anchor_source_count": sum(1 for item in all_sources if item["weight_band"] == "anchor"),
            "major_source_count": sum(1 for item in all_sources if item["weight_band"] == "major"),
            "supporting_source_count": sum(1 for item in all_sources if item["weight_band"] == "supporting"),
            "contextual_source_count": sum(1 for item in all_sources if item["weight_band"] == "contextual"),
            "missing_source_count": sum(1 for item in all_sources if item["weight_band"] == "missing"),
        },
        "lectures": lectures_payload,
        "sources": all_sources,
    }
    _write_json(output_path, payload)
    builder_path = Path(__file__).resolve()
    dependency_paths = [
        lecture_bundle_dir / "index.json",
        *lecture_bundle_paths,
        glossary_path,
        theory_map_path,
        builder_path,
    ]
    input_signature = _signature_for_paths(dependency_paths)

    staleness_payload = _load_json(staleness_path) if staleness_path.exists() else {
        "version": SOURCE_WEIGHTING_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": _now(),
        "artifacts": {},
        "derivations": [],
    }
    staleness_payload["generated_at"] = _now()
    artifacts = staleness_payload.setdefault("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        staleness_payload["artifacts"] = artifacts
    artifacts["source_weighting"] = {
        "path": _display_path(output_path, repo_root),
        "sha256": _sha256_file(output_path),
        "input_signature_sha256": input_signature,
        "builder_script": _display_path(builder_path, repo_root),
    }
    derivations = staleness_payload.setdefault("derivations", [])
    if not isinstance(derivations, list):
        derivations = []
        staleness_payload["derivations"] = derivations
    weighting_derivation = {
        "artifact_path": _display_path(output_path, repo_root),
        "depends_on": [_display_path(path, repo_root) for path in dependency_paths],
    }
    derivations = [
        entry
        for entry in derivations
        if not (isinstance(entry, dict) and str(entry.get("artifact_path") or "").strip() == weighting_derivation["artifact_path"])
    ]
    derivations.append(weighting_derivation)
    staleness_payload["derivations"] = derivations
    _write_json(staleness_path, staleness_payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lecture-bundle-dir", default=DEFAULT_LECTURE_BUNDLE_DIR, help="Path to lecture_bundles directory.")
    parser.add_argument("--glossary-path", default=DEFAULT_GLOSSARY_PATH, help="Path to course_glossary.json.")
    parser.add_argument("--theory-map-path", default=DEFAULT_THEORY_MAP_PATH, help="Path to course_theory_map.json.")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH, help="Path to source_weighting.json.")
    parser.add_argument("--staleness-path", default=DEFAULT_STALENESS_PATH, help="Path to source_intelligence_staleness.json.")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    payload = build_source_weighting(
        repo_root=repo_root,
        lecture_bundle_dir=_resolve_path(repo_root, args.lecture_bundle_dir),
        glossary_path=_resolve_path(repo_root, args.glossary_path),
        theory_map_path=_resolve_path(repo_root, args.theory_map_path),
        output_path=_resolve_path(repo_root, args.output_path),
        staleness_path=_resolve_path(repo_root, args.staleness_path),
    )
    print(
        "Built source weighting "
        f"(lectures={payload['stats']['lecture_count']} sources={payload['stats']['source_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
