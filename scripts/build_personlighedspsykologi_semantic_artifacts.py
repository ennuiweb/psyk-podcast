#!/usr/bin/env python3
"""Build course-level semantic artifacts for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_CATALOG = "shows/personlighedspsykologi-en/source_catalog.json"
DEFAULT_LECTURE_BUNDLE_DIR = "shows/personlighedspsykologi-en/lecture_bundles"
DEFAULT_SEED_PATH = "shows/personlighedspsykologi-en/source_intelligence_seed.json"
DEFAULT_GLOSSARY_PATH = "shows/personlighedspsykologi-en/course_glossary.json"
DEFAULT_THEORY_MAP_PATH = "shows/personlighedspsykologi-en/course_theory_map.json"
DEFAULT_STALENESS_PATH = "shows/personlighedspsykologi-en/source_intelligence_staleness.json"
SEMANTIC_ARTIFACT_VERSION = 1


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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _normalize_id_list(value: object) -> list[str]:
    items = _normalize_list(value)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _casefold(text: str) -> str:
    return text.casefold()


def _contains_alias(text: str, alias: str) -> bool:
    return _casefold(alias) in _casefold(text)


def _trim_excerpt(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _load_lecture_bundles(lecture_bundle_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index_payload = _load_json(lecture_bundle_dir / "index.json")
    bundle_by_key: dict[str, dict[str, Any]] = {}
    for entry in index_payload.get("bundles", []):
        if not isinstance(entry, dict):
            continue
        lecture_key = str(entry.get("lecture_key") or "").strip().upper()
        relative_path = str(entry.get("relative_path") or "").strip()
        if not lecture_key or not relative_path:
            continue
        bundle_by_key[lecture_key] = _load_json(lecture_bundle_dir / relative_path)
    return index_payload, bundle_by_key


def _bundle_source_lookup(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    sources = bundle.get("sources")
    if not isinstance(sources, dict):
        return lookup
    for source_group in sources.values():
        if not isinstance(source_group, list):
            continue
        for source in source_group:
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("source_id") or "").strip()
            if source_id:
                lookup[source_id] = source
    return lookup


def _bundle_fragments(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    lecture_key = str(bundle.get("lecture_key") or "").strip().upper()
    lecture_title = str(bundle.get("lecture_title") or "").strip()
    if lecture_title:
        fragments.append(
            {
                "lecture_key": lecture_key,
                "location": "lecture_title",
                "text": lecture_title,
                "source_id": None,
            }
        )
    lecture_summary = bundle.get("lecture_summary")
    if isinstance(lecture_summary, dict):
        for text in _normalize_list(lecture_summary.get("summary_lines")):
            fragments.append(
                {
                    "lecture_key": lecture_key,
                    "location": "lecture_summary",
                    "text": text,
                    "source_id": None,
                }
            )
        for text in _normalize_list(lecture_summary.get("key_points")):
            fragments.append(
                {
                    "lecture_key": lecture_key,
                    "location": "lecture_key_point",
                    "text": text,
                    "source_id": None,
                }
            )

    for source_id, source in _bundle_source_lookup(bundle).items():
        title = str(source.get("title") or "").strip()
        if title:
            fragments.append(
                {
                    "lecture_key": lecture_key,
                    "location": "source_title",
                    "text": title,
                    "source_id": source_id,
                }
            )
        summary = source.get("summary")
        if isinstance(summary, dict):
            for text in _normalize_list(summary.get("summary_lines")):
                fragments.append(
                    {
                        "lecture_key": lecture_key,
                        "location": "source_summary",
                        "text": text,
                        "source_id": source_id,
                    }
                )
            for text in _normalize_list(summary.get("key_points")):
                fragments.append(
                    {
                        "lecture_key": lecture_key,
                        "location": "source_key_point",
                        "text": text,
                        "source_id": source_id,
                    }
                )
    return fragments


def _collect_matches(bundle: dict[str, Any], aliases: list[str]) -> dict[str, Any]:
    aliases = [alias for alias in _normalize_list(aliases) if alias]
    matched_aliases: list[str] = []
    match_locations: list[str] = []
    excerpts: list[str] = []
    source_ids: list[str] = []
    core_source_ids: list[str] = []
    supporting_source_ids: list[str] = []
    source_lookup = _bundle_source_lookup(bundle)

    for fragment in _bundle_fragments(bundle):
        fragment_text = str(fragment["text"])
        fragment_matches = [alias for alias in aliases if _contains_alias(fragment_text, alias)]
        if not fragment_matches:
            continue
        matched_aliases.extend(fragment_matches)
        match_locations.append(str(fragment["location"]))
        excerpts.append(_trim_excerpt(fragment_text))
        source_id = fragment.get("source_id")
        if source_id:
            source_ids.append(str(source_id))
            priority_band = str((source_lookup.get(str(source_id)) or {}).get("priority_band") or "")
            if priority_band in {"core", "primary"}:
                core_source_ids.append(str(source_id))
            elif priority_band:
                supporting_source_ids.append(str(source_id))

    return {
        "matched_aliases": _unique_preserve_order(matched_aliases),
        "match_locations": _unique_preserve_order(match_locations),
        "representative_excerpts": _unique_preserve_order(excerpts)[:3],
        "source_ids": _unique_preserve_order(source_ids),
        "core_source_ids": _unique_preserve_order(core_source_ids),
        "supporting_source_ids": _unique_preserve_order(supporting_source_ids),
        "evidence_fragment_count": len(excerpts),
    }


def _lecture_titles(bundle_keys: list[str], bundle_by_key: dict[str, dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for lecture_key in bundle_keys:
        bundle = bundle_by_key.get(lecture_key)
        if not bundle:
            continue
        title = str(bundle.get("lecture_title") or "").strip()
        if title:
            titles.append(title)
    return titles


def _grounding_status(*, scoped_count: int, matched_count: int) -> str:
    if matched_count <= 0:
        return "seed_only"
    if scoped_count and matched_count < scoped_count:
        return "partially_grounded"
    return "grounded"


def _term_salience(*, importance: int, lecture_count: int, core_source_count: int, evidence_count: int) -> int:
    return (importance * 12) + (lecture_count * 8) + (core_source_count * 5) + min(evidence_count, 12)


def _theory_salience(*, importance: int, lecture_count: int, core_term_count: int, source_count: int) -> int:
    return (importance * 14) + (lecture_count * 8) + (core_term_count * 6) + min(source_count, 10)


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
    payload = "\n".join(_sha256_file(path) for path in paths).encode("utf-8")
    return _sha256_bytes(payload)


def build_semantic_artifacts(
    *,
    repo_root: Path,
    source_catalog_path: Path,
    lecture_bundle_dir: Path,
    seed_path: Path,
    glossary_path: Path,
    theory_map_path: Path,
    staleness_path: Path,
) -> dict[str, Any]:
    source_catalog = _load_json(source_catalog_path)
    lecture_bundle_index, bundle_by_key = _load_lecture_bundles(lecture_bundle_dir)
    seed_payload = _load_json(seed_path)

    terms_seed = seed_payload.get("terms")
    theories_seed = seed_payload.get("theories")
    if not isinstance(terms_seed, list):
        raise SystemExit(f"invalid terms list in {seed_path}")
    if not isinstance(theories_seed, list):
        raise SystemExit(f"invalid theories list in {seed_path}")

    ordered_lecture_keys = [
        str(entry.get("lecture_key") or "").strip().upper()
        for entry in lecture_bundle_index.get("bundles", [])
        if isinstance(entry, dict) and str(entry.get("lecture_key") or "").strip()
    ]
    ordered_lecture_set = set(ordered_lecture_keys)
    glossary_terms: list[dict[str, Any]] = []
    glossary_term_ids: set[str] = set()

    for raw_term in terms_seed:
        if not isinstance(raw_term, dict):
            continue
        term_id = str(raw_term.get("term_id") or "").strip()
        if not term_id:
            continue
        scoped_lecture_keys = [
            lecture_key
            for lecture_key in _normalize_id_list(raw_term.get("lecture_keys"))
            if lecture_key in ordered_lecture_set
        ]
        aliases = _unique_preserve_order([str(raw_term.get("label") or "").strip()] + _normalize_list(raw_term.get("aliases")))
        evidence_by_lecture: list[dict[str, Any]] = []
        matched_lecture_keys: list[str] = []
        all_source_ids: list[str] = []
        all_core_source_ids: list[str] = []
        all_supporting_source_ids: list[str] = []
        evidence_count = 0
        for lecture_key in scoped_lecture_keys:
            bundle = bundle_by_key.get(lecture_key)
            if not bundle:
                continue
            match_info = _collect_matches(bundle, aliases)
            if match_info["evidence_fragment_count"] <= 0:
                continue
            matched_lecture_keys.append(lecture_key)
            all_source_ids.extend(match_info["source_ids"])
            all_core_source_ids.extend(match_info["core_source_ids"])
            all_supporting_source_ids.extend(match_info["supporting_source_ids"])
            evidence_count += int(match_info["evidence_fragment_count"])
            evidence_by_lecture.append(
                {
                    "lecture_key": lecture_key,
                    "lecture_title": str(bundle.get("lecture_title") or "").strip(),
                    "matched_aliases": match_info["matched_aliases"],
                    "match_locations": match_info["match_locations"],
                    "representative_excerpts": match_info["representative_excerpts"],
                    "source_ids": match_info["source_ids"],
                    "core_source_ids": match_info["core_source_ids"],
                    "supporting_source_ids": match_info["supporting_source_ids"],
                }
            )

        importance = int(raw_term.get("importance") or 1)
        grounding_status = _grounding_status(
            scoped_count=len(scoped_lecture_keys),
            matched_count=len(matched_lecture_keys),
        )
        glossary_terms.append(
            {
                "term_id": term_id,
                "label": str(raw_term.get("label") or "").strip(),
                "category": str(raw_term.get("category") or "").strip() or "concept",
                "importance": importance,
                "aliases": aliases,
                "definition": str(raw_term.get("definition") or "").strip(),
                "course_role": str(raw_term.get("course_role") or "").strip(),
                "lecture_keys": scoped_lecture_keys,
                "lecture_titles": _lecture_titles(scoped_lecture_keys, bundle_by_key),
                "matched_lecture_keys": matched_lecture_keys,
                "grounding_status": grounding_status,
                "match_stats": {
                    "scoped_lecture_count": len(scoped_lecture_keys),
                    "matched_lecture_count": len(matched_lecture_keys),
                    "evidence_fragment_count": evidence_count,
                },
                "linked_terms": _normalize_id_list(raw_term.get("linked_terms")),
                "linked_theories": _normalize_id_list(raw_term.get("linked_theories")),
                "source_ids": _unique_preserve_order(all_source_ids),
                "core_source_ids": _unique_preserve_order(all_core_source_ids),
                "supporting_source_ids": _unique_preserve_order(all_supporting_source_ids),
                "salience_score": _term_salience(
                    importance=importance,
                    lecture_count=len(scoped_lecture_keys),
                    core_source_count=len(_unique_preserve_order(all_core_source_ids)),
                    evidence_count=evidence_count,
                ),
                "evidence_by_lecture": evidence_by_lecture,
                "provenance": {
                    "seed_path": _display_path(seed_path, repo_root),
                    "lecture_bundle_paths": [f"shows/personlighedspsykologi-en/lecture_bundles/{lecture_key}.json" for lecture_key in scoped_lecture_keys],
                },
            }
        )
        glossary_term_ids.add(term_id)

    glossary_terms.sort(key=lambda item: (-int(item["salience_score"]), str(item["label"]).casefold()))

    glossary_payload = {
        "version": SEMANTIC_ARTIFACT_VERSION,
        "subject_slug": str(source_catalog.get("subject_slug") or "personlighedspsykologi"),
        "generated_at": _now(),
        "build_inputs": {
            "source_catalog": _display_path(source_catalog_path, repo_root),
            "lecture_bundle_index": _display_path(lecture_bundle_dir / "index.json", repo_root),
            "seed_path": _display_path(seed_path, repo_root),
        },
        "stats": {
            "term_count": len(glossary_terms),
            "grounded_term_count": sum(1 for term in glossary_terms if term["grounding_status"] == "grounded"),
            "partially_grounded_term_count": sum(1 for term in glossary_terms if term["grounding_status"] == "partially_grounded"),
            "seed_only_term_count": sum(1 for term in glossary_terms if term["grounding_status"] == "seed_only"),
        },
        "terms": glossary_terms,
    }
    _write_json(glossary_path, glossary_payload)

    glossary_term_by_id = {term["term_id"]: term for term in glossary_terms}
    theory_entries: list[dict[str, Any]] = []
    relation_entries: list[dict[str, Any]] = []
    theory_ids: set[str] = set()
    for raw_theory in theories_seed:
        if not isinstance(raw_theory, dict):
            continue
        theory_id = str(raw_theory.get("theory_id") or "").strip()
        if not theory_id:
            continue
        theory_ids.add(theory_id)

    for raw_theory in theories_seed:
        if not isinstance(raw_theory, dict):
            continue
        theory_id = str(raw_theory.get("theory_id") or "").strip()
        if not theory_id:
            continue
        scoped_lecture_keys = [
            lecture_key
            for lecture_key in _normalize_id_list(raw_theory.get("lecture_keys"))
            if lecture_key in ordered_lecture_set
        ]
        aliases = _unique_preserve_order([str(raw_theory.get("label") or "").strip()] + _normalize_list(raw_theory.get("aliases")))
        core_term_ids = [term_id for term_id in _normalize_id_list(raw_theory.get("core_term_ids")) if term_id in glossary_term_by_id]
        theory_grounded_lecture_keys: set[str] = set()
        for term_id in core_term_ids:
            theory_grounded_lecture_keys.update(
                lecture_key
                for lecture_key in glossary_term_by_id[term_id].get("matched_lecture_keys", [])
                if lecture_key in scoped_lecture_keys
            )
        evidence_by_lecture: list[dict[str, Any]] = []
        representative_source_ids: list[str] = []
        matched_lecture_keys: list[str] = []
        for lecture_key in scoped_lecture_keys:
            bundle = bundle_by_key.get(lecture_key)
            if not bundle:
                continue
            match_info = _collect_matches(bundle, aliases)
            if match_info["evidence_fragment_count"] > 0 or lecture_key in theory_grounded_lecture_keys:
                matched_lecture_keys.append(lecture_key)
            representative_source_ids.extend(_normalize_list((bundle.get("source_intelligence") or {}).get("likely_core_sources")))
            evidence_by_lecture.append(
                {
                    "lecture_key": lecture_key,
                    "lecture_title": str(bundle.get("lecture_title") or "").strip(),
                    "representative_excerpts": match_info["representative_excerpts"] or _normalize_list((bundle.get("lecture_summary") or {}).get("summary_lines"))[:2],
                    "likely_core_sources": _normalize_list((bundle.get("source_intelligence") or {}).get("likely_core_sources")),
                }
            )

        related_theories: list[dict[str, Any]] = []
        for relation in raw_theory.get("related_theories", []):
            if not isinstance(relation, dict):
                continue
            target_theory_id = str(relation.get("theory_id") or "").strip()
            if not target_theory_id or target_theory_id not in theory_ids:
                continue
            related_theory_entry = {
                "theory_id": target_theory_id,
                "relation_type": str(relation.get("relation_type") or "").strip(),
                "rationale": str(relation.get("rationale") or "").strip(),
            }
            related_theories.append(related_theory_entry)
            relation_entries.append(
                {
                    "source_theory_id": theory_id,
                    "target_theory_id": target_theory_id,
                    "relation_type": related_theory_entry["relation_type"],
                    "rationale": related_theory_entry["rationale"],
                    "supporting_term_ids": core_term_ids,
                }
            )

        importance = int(raw_theory.get("importance") or 1)
        representative_source_ids = _unique_preserve_order(representative_source_ids)
        theory_entries.append(
            {
                "theory_id": theory_id,
                "label": str(raw_theory.get("label") or "").strip(),
                "importance": importance,
                "aliases": aliases,
                "summary": str(raw_theory.get("summary") or "").strip(),
                "course_role": str(raw_theory.get("course_role") or "").strip(),
                "lecture_keys": scoped_lecture_keys,
                "lecture_titles": _lecture_titles(scoped_lecture_keys, bundle_by_key),
                "matched_lecture_keys": matched_lecture_keys,
                "grounding_status": _grounding_status(scoped_count=len(scoped_lecture_keys), matched_count=len(matched_lecture_keys)),
                "core_term_ids": core_term_ids,
                "core_terms": [
                    {
                        "term_id": term_id,
                        "label": glossary_term_by_id[term_id]["label"],
                    }
                    for term_id in core_term_ids
                ],
                "representative_source_ids": representative_source_ids[:10],
                "salience_score": _theory_salience(
                    importance=importance,
                    lecture_count=len(scoped_lecture_keys),
                    core_term_count=len(core_term_ids),
                    source_count=len(representative_source_ids),
                ),
                "related_theories": related_theories,
                "evidence_by_lecture": evidence_by_lecture,
                "provenance": {
                    "seed_path": _display_path(seed_path, repo_root),
                    "lecture_bundle_paths": [f"shows/personlighedspsykologi-en/lecture_bundles/{lecture_key}.json" for lecture_key in scoped_lecture_keys],
                },
            }
        )

    theory_entries.sort(key=lambda item: (-int(item["salience_score"]), str(item["label"]).casefold()))
    theory_map_payload = {
        "version": SEMANTIC_ARTIFACT_VERSION,
        "subject_slug": str(source_catalog.get("subject_slug") or "personlighedspsykologi"),
        "generated_at": _now(),
        "build_inputs": {
            "course_glossary": _display_path(glossary_path, repo_root),
            "lecture_bundle_index": _display_path(lecture_bundle_dir / "index.json", repo_root),
            "seed_path": _display_path(seed_path, repo_root),
        },
        "stats": {
            "theory_count": len(theory_entries),
            "relation_count": len(relation_entries),
            "grounded_theory_count": sum(1 for theory in theory_entries if theory["grounding_status"] == "grounded"),
            "partially_grounded_theory_count": sum(
                1 for theory in theory_entries if theory["grounding_status"] == "partially_grounded"
            ),
            "seed_only_theory_count": sum(1 for theory in theory_entries if theory["grounding_status"] == "seed_only"),
        },
        "theories": theory_entries,
        "relations": relation_entries,
    }
    _write_json(theory_map_path, theory_map_payload)

    builder_path = Path(__file__).resolve()
    lecture_bundle_paths = _lecture_bundle_paths(lecture_bundle_dir, lecture_bundle_index)
    glossary_dependency_paths = [
        source_catalog_path,
        lecture_bundle_dir / "index.json",
        *lecture_bundle_paths,
        seed_path,
        builder_path,
    ]
    theory_dependency_paths = [
        glossary_path,
        lecture_bundle_dir / "index.json",
        *lecture_bundle_paths,
        seed_path,
        builder_path,
    ]
    glossary_input_signature = _signature_for_paths(glossary_dependency_paths)
    theory_input_signature = _signature_for_paths(theory_dependency_paths)

    lecture_bundle_hashes = []
    for bundle_path in lecture_bundle_paths:
        lecture_bundle_hashes.append(
            {
                "path": _display_path(bundle_path, repo_root),
                "sha256": _sha256_file(bundle_path),
            }
        )

    existing_staleness_payload = _load_json(staleness_path) if staleness_path.exists() else None
    existing_artifacts = (
        existing_staleness_payload.get("artifacts")
        if isinstance(existing_staleness_payload, dict) and isinstance(existing_staleness_payload.get("artifacts"), dict)
        else {}
    )
    existing_derivations = (
        existing_staleness_payload.get("derivations")
        if isinstance(existing_staleness_payload, dict) and isinstance(existing_staleness_payload.get("derivations"), list)
        else []
    )
    preserved_artifacts = {
        key: value
        for key, value in existing_artifacts.items()
        if key not in {"source_catalog", "lecture_bundle_index", "lecture_bundles", "semantic_seed", "builder_script", "course_glossary", "course_theory_map"}
    }
    preserved_derivations = [
        entry
        for entry in existing_derivations
        if not (
            isinstance(entry, dict)
            and str(entry.get("artifact_path") or "").strip()
            in {
                _display_path(glossary_path, repo_root),
                _display_path(theory_map_path, repo_root),
            }
        )
    ]

    staleness_payload = {
        "version": SEMANTIC_ARTIFACT_VERSION,
        "subject_slug": str(source_catalog.get("subject_slug") or "personlighedspsykologi"),
        "generated_at": _now(),
        "artifacts": preserved_artifacts | {
            "source_catalog": {
                "path": _display_path(source_catalog_path, repo_root),
                "sha256": _sha256_file(source_catalog_path),
            },
            "lecture_bundle_index": {
                "path": _display_path(lecture_bundle_dir / "index.json", repo_root),
                "sha256": _sha256_file(lecture_bundle_dir / "index.json"),
            },
            "lecture_bundles": {
                "count": len(lecture_bundle_hashes),
                "items": lecture_bundle_hashes,
            },
            "semantic_seed": {
                "path": _display_path(seed_path, repo_root),
                "sha256": _sha256_file(seed_path),
            },
            "builder_script": {
                "path": _display_path(builder_path, repo_root),
                "sha256": _sha256_file(builder_path),
            },
            "course_glossary": {
                "path": _display_path(glossary_path, repo_root),
                "sha256": _sha256_file(glossary_path),
                "input_signature_sha256": glossary_input_signature,
            },
            "course_theory_map": {
                "path": _display_path(theory_map_path, repo_root),
                "sha256": _sha256_file(theory_map_path),
                "input_signature_sha256": theory_input_signature,
            },
        },
        "derivations": preserved_derivations + [
            {
                "artifact_path": _display_path(glossary_path, repo_root),
                "depends_on": [_display_path(path, repo_root) for path in glossary_dependency_paths],
            },
            {
                "artifact_path": _display_path(theory_map_path, repo_root),
                "depends_on": [_display_path(path, repo_root) for path in theory_dependency_paths],
            },
        ],
    }
    _write_json(staleness_path, staleness_payload)
    return {
        "course_glossary": glossary_payload,
        "course_theory_map": theory_map_payload,
        "source_intelligence_staleness": staleness_payload,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-catalog", default=DEFAULT_SOURCE_CATALOG, help="Path to source_catalog.json.")
    parser.add_argument("--lecture-bundle-dir", default=DEFAULT_LECTURE_BUNDLE_DIR, help="Path to lecture_bundles directory.")
    parser.add_argument("--seed-path", default=DEFAULT_SEED_PATH, help="Path to source_intelligence_seed.json.")
    parser.add_argument("--glossary-path", default=DEFAULT_GLOSSARY_PATH, help="Path to course_glossary.json.")
    parser.add_argument("--theory-map-path", default=DEFAULT_THEORY_MAP_PATH, help="Path to course_theory_map.json.")
    parser.add_argument("--staleness-path", default=DEFAULT_STALENESS_PATH, help="Path to source_intelligence_staleness.json.")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    outputs = build_semantic_artifacts(
        repo_root=repo_root,
        source_catalog_path=_resolve_path(repo_root, args.source_catalog),
        lecture_bundle_dir=_resolve_path(repo_root, args.lecture_bundle_dir),
        seed_path=_resolve_path(repo_root, args.seed_path),
        glossary_path=_resolve_path(repo_root, args.glossary_path),
        theory_map_path=_resolve_path(repo_root, args.theory_map_path),
        staleness_path=_resolve_path(repo_root, args.staleness_path),
    )
    print(
        "Built semantic artifacts "
        f"(terms={outputs['course_glossary']['stats']['term_count']} "
        f"theories={outputs['course_theory_map']['stats']['theory_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
