#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from typing import Any

SHOW_DIR = Path("shows/personlighedspsykologi-en")
NOTEBOOKLM_DIR = Path("notebooklm-podcast-auto/personlighedspsykologi")
FREUDD_SUBJECTS = Path("freudd_portal/subjects.json")

CANONICAL_CONFIG = SHOW_DIR / "config.github.json"
COMPAT_CONFIG = SHOW_DIR / "config.local.json"
PRIMARY_READING_KEY = SHOW_DIR / "docs" / "reading-file-key.md"
LEGACY_READING_KEY = NOTEBOOKLM_DIR / "docs" / "reading-file-key.md"
PRIMARY_OVERBLIK = SHOW_DIR / "docs" / "overblik.md"
LEGACY_OVERBLIK = NOTEBOOKLM_DIR / "docs" / "overblik.md"
SOURCE_CATALOG = SHOW_DIR / "source_catalog.json"
LECTURE_BUNDLES_DIR = SHOW_DIR / "lecture_bundles"
LECTURE_BUNDLE_INDEX = LECTURE_BUNDLES_DIR / "index.json"
CONTENT_MANIFEST = SHOW_DIR / "content_manifest.json"
SOURCE_INTELLIGENCE_SEED = SHOW_DIR / "source_intelligence_seed.json"
SOURCE_INTELLIGENCE_POLICY = SHOW_DIR / "source_intelligence_policy.json"
COURSE_GLOSSARY = SHOW_DIR / "course_glossary.json"
COURSE_THEORY_MAP = SHOW_DIR / "course_theory_map.json"
SOURCE_INTELLIGENCE_STALENESS = SHOW_DIR / "source_intelligence_staleness.json"
SOURCE_WEIGHTING = SHOW_DIR / "source_weighting.json"
COURSE_CONCEPT_GRAPH = SHOW_DIR / "course_concept_graph.json"
ARTIFACT_OWNERSHIP = SHOW_DIR / "artifact_ownership.json"
VALID_OWNERSHIP_ROLES = {"canonical", "mirror", "derived", "runtime"}
PERSONLIGHEDS_SUBJECT_REQUIRED_PATHS = {
    "reading_key_path",
    "reading_summaries_path",
    "weekly_overview_summaries_path",
    "quiz_links_path",
    "quiz_files_root",
    "feed_rss_path",
    "episode_inventory_path",
    "spotify_map_path",
    "content_manifest_path",
    "reading_files_root",
    "reading_download_exclusions_path",
    "slides_catalog_path",
    "slides_files_root",
}
PERSONLIGHEDS_SUBJECT_PATH_TO_ARTIFACT = {
    "reading_key_path": "reading_key",
    "reading_summaries_path": "reading_summaries",
    "weekly_overview_summaries_path": "weekly_overview_summaries",
    "feed_rss_path": "rss_feed",
    "episode_inventory_path": "episode_inventory",
    "spotify_map_path": "spotify_map",
    "content_manifest_path": "content_manifest",
    "reading_download_exclusions_path": "reading_download_exclusions",
    "slides_catalog_path": "slides_catalog",
}

REFERENCE_FILES = [
    SHOW_DIR / "README.md",
    SHOW_DIR / "docs" / "README.md",
    SHOW_DIR / "docs" / "plan.md",
    SHOW_DIR / "docs" / "podcast-flow-artifacts.md",
    SHOW_DIR / "docs" / "podcast-flow-operations.md",
    SHOW_DIR / "docs" / "reading-name-sources-report-2026-03-05.md",
    NOTEBOOKLM_DIR / "README.md",
    NOTEBOOKLM_DIR / "docs" / "quiz-difficulty-overview-plan.md",
    "TECHNICAL.md",
]

FORBIDDEN_REFERENCES = {
    str(LEGACY_READING_KEY): "legacy NotebookLM reading-file-key mirror reference",
    str(LEGACY_OVERBLIK): "legacy NotebookLM overblik mirror reference",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_owned_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def _validate_artifact_ownership(repo_root: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    failures: list[str] = []
    contract_path = repo_root / ARTIFACT_OWNERSHIP
    if not contract_path.exists():
        return ([f"Missing artifact ownership contract: {ARTIFACT_OWNERSHIP}"], {})

    payload = _load_json(contract_path)
    if not isinstance(payload, dict):
        return ([f"Artifact ownership payload is invalid: {ARTIFACT_OWNERSHIP}"], {})
    if payload.get("version") != 1:
        failures.append(f"Artifact ownership contract has unsupported version in {ARTIFACT_OWNERSHIP}")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return ([f"Artifact ownership contract is missing artifacts list: {ARTIFACT_OWNERSHIP}"], {})

    artifacts_by_id: dict[str, dict[str, Any]] = {}
    concepts: dict[str, list[dict[str, Any]]] = {}
    for entry in artifacts:
        if not isinstance(entry, dict):
            failures.append(f"Artifact ownership entry is invalid in {ARTIFACT_OWNERSHIP}")
            continue
        artifact_id = str(entry.get("artifact_id") or "").strip()
        concept = str(entry.get("concept") or "").strip()
        role = str(entry.get("role") or "").strip()
        path_text = str(entry.get("path") or "").strip()
        if not artifact_id:
            failures.append(f"Artifact ownership entry missing artifact_id in {ARTIFACT_OWNERSHIP}")
            continue
        if artifact_id in artifacts_by_id:
            failures.append(f"Duplicate artifact ownership id {artifact_id} in {ARTIFACT_OWNERSHIP}")
            continue
        if not concept:
            failures.append(f"Artifact ownership entry {artifact_id} missing concept in {ARTIFACT_OWNERSHIP}")
        if role not in VALID_OWNERSHIP_ROLES:
            failures.append(f"Artifact ownership entry {artifact_id} has invalid role {role!r}")
        if not path_text:
            failures.append(f"Artifact ownership entry {artifact_id} missing path in {ARTIFACT_OWNERSHIP}")
        require_exists = bool(entry.get("require_exists", True))
        if path_text and require_exists and not _resolve_owned_path(repo_root, path_text).exists():
            failures.append(f"Owned artifact missing on disk for {artifact_id}: {path_text}")
        mirror_of = str(entry.get("mirror_of") or "").strip()
        if role == "mirror" and not mirror_of:
            failures.append(f"Mirror artifact {artifact_id} missing mirror_of in {ARTIFACT_OWNERSHIP}")
        artifacts_by_id[artifact_id] = entry
        concepts.setdefault(concept, []).append(entry)

    for artifact_id, entry in artifacts_by_id.items():
        if str(entry.get("role") or "").strip() != "mirror":
            continue
        mirror_of = str(entry.get("mirror_of") or "").strip()
        parent = artifacts_by_id.get(mirror_of)
        if parent is None:
            failures.append(f"Mirror artifact {artifact_id} references unknown parent {mirror_of}")
            continue
        if str(parent.get("role") or "").strip() != "canonical":
            failures.append(f"Mirror artifact {artifact_id} parent {mirror_of} is not canonical")
        if str(parent.get("concept") or "").strip() != str(entry.get("concept") or "").strip():
            failures.append(f"Mirror artifact {artifact_id} concept does not match parent {mirror_of}")

    for concept, entries in concepts.items():
        if not concept:
            continue
        if not any(str(entry.get("role") or "").strip() in {"canonical", "mirror"} for entry in entries):
            continue
        canonical_count = sum(1 for entry in entries if str(entry.get("role") or "").strip() == "canonical")
        if canonical_count != 1:
            failures.append(
                f"Ownership concept {concept!r} must have exactly one canonical artifact; found {canonical_count}"
            )

    return failures, artifacts_by_id


def _find_subject_definition(payload: Any, *, slug: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    subjects = payload.get("subjects")
    if not isinstance(subjects, list):
        return None
    normalized_slug = str(slug or "").strip().lower()
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        if str(subject.get("slug") or "").strip().lower() == normalized_slug:
            return subject
    return None


def _failures(repo_root: Path) -> list[str]:
    failures: list[str] = []
    canonical_config = repo_root / CANONICAL_CONFIG
    compat_config = repo_root / COMPAT_CONFIG
    primary_reading_key = repo_root / PRIMARY_READING_KEY
    legacy_reading_key = repo_root / LEGACY_READING_KEY
    primary_overblik = repo_root / PRIMARY_OVERBLIK
    legacy_overblik = repo_root / LEGACY_OVERBLIK
    source_catalog = repo_root / SOURCE_CATALOG
    lecture_bundle_index = repo_root / LECTURE_BUNDLE_INDEX
    lecture_bundles_dir = repo_root / LECTURE_BUNDLES_DIR
    content_manifest = repo_root / CONTENT_MANIFEST
    source_intelligence_seed = repo_root / SOURCE_INTELLIGENCE_SEED
    source_intelligence_policy = repo_root / SOURCE_INTELLIGENCE_POLICY
    course_glossary = repo_root / COURSE_GLOSSARY
    course_theory_map = repo_root / COURSE_THEORY_MAP
    source_intelligence_staleness = repo_root / SOURCE_INTELLIGENCE_STALENESS
    source_weighting = repo_root / SOURCE_WEIGHTING
    course_concept_graph = repo_root / COURSE_CONCEPT_GRAPH
    freudd_subjects = repo_root / FREUDD_SUBJECTS
    content_manifest_payload = _load_json(content_manifest) if content_manifest.exists() else None
    ownership_failures, owned_artifacts = _validate_artifact_ownership(repo_root)
    failures.extend(ownership_failures)

    if not canonical_config.exists():
        failures.append(f"Missing canonical config: {CANONICAL_CONFIG}")
    if not compat_config.exists():
        failures.append(f"Missing compatibility config: {COMPAT_CONFIG}")
    if canonical_config.exists() and compat_config.exists():
        if _load_json(canonical_config) != _load_json(compat_config):
            failures.append(
                "Compatibility config diverged from canonical config: "
                f"{COMPAT_CONFIG} != {CANONICAL_CONFIG}"
            )

    if not primary_reading_key.exists():
        failures.append(f"Missing canonical reading-file-key mirror: {PRIMARY_READING_KEY}")
    if legacy_reading_key.exists():
        failures.append(f"Legacy reading-file-key mirror should be absent: {LEGACY_READING_KEY}")

    if not primary_overblik.exists():
        failures.append(f"Missing canonical overblik doc: {PRIMARY_OVERBLIK}")
    if legacy_overblik.exists():
        failures.append(f"Legacy overblik mirror should be absent: {LEGACY_OVERBLIK}")

    if not source_catalog.exists():
        failures.append(f"Missing source catalog: {SOURCE_CATALOG}")
    if not lecture_bundles_dir.exists():
        failures.append(f"Missing lecture bundles directory: {LECTURE_BUNDLES_DIR}")
    if not lecture_bundle_index.exists():
        failures.append(f"Missing lecture bundle index: {LECTURE_BUNDLE_INDEX}")
    if not source_intelligence_seed.exists():
        failures.append(f"Missing source intelligence seed: {SOURCE_INTELLIGENCE_SEED}")
    if not source_intelligence_policy.exists():
        failures.append(f"Missing source intelligence policy: {SOURCE_INTELLIGENCE_POLICY}")
    if not course_glossary.exists():
        failures.append(f"Missing course glossary: {COURSE_GLOSSARY}")
    if not course_theory_map.exists():
        failures.append(f"Missing course theory map: {COURSE_THEORY_MAP}")
    if not source_intelligence_staleness.exists():
        failures.append(f"Missing source intelligence staleness index: {SOURCE_INTELLIGENCE_STALENESS}")
    if not source_weighting.exists():
        failures.append(f"Missing source weighting artifact: {SOURCE_WEIGHTING}")
    if not course_concept_graph.exists():
        failures.append(f"Missing course concept graph: {COURSE_CONCEPT_GRAPH}")
    if not freudd_subjects.exists():
        failures.append(f"Missing Freudd subject catalog: {FREUDD_SUBJECTS}")

    if freudd_subjects.exists():
        freudd_subjects_payload = _load_json(freudd_subjects)
        person_subject = _find_subject_definition(freudd_subjects_payload, slug="personlighedspsykologi")
        if person_subject is None:
            failures.append("Freudd subject catalog missing personlighedspsykologi subject definition")
        else:
            raw_paths = person_subject.get("paths")
            if not isinstance(raw_paths, dict):
                failures.append("Freudd personlighedspsykologi subject is missing explicit paths object")
            else:
                legacy_keys = {"reading_master_path", "reading_fallback_path"} & set(raw_paths.keys())
                if legacy_keys:
                    failures.append(
                        "Freudd personlighedspsykologi subject still uses legacy reading path keys: "
                        + ", ".join(sorted(legacy_keys))
                    )
                missing_paths = PERSONLIGHEDS_SUBJECT_REQUIRED_PATHS - set(raw_paths.keys())
                if missing_paths:
                    failures.append(
                        "Freudd personlighedspsykologi subject missing explicit ownership paths: "
                        + ", ".join(sorted(missing_paths))
                    )
                for subject_key, artifact_id in PERSONLIGHEDS_SUBJECT_PATH_TO_ARTIFACT.items():
                    if subject_key not in raw_paths:
                        continue
                    artifact_entry = owned_artifacts.get(artifact_id)
                    if artifact_entry is None:
                        failures.append(
                            f"Artifact ownership contract missing artifact {artifact_id} referenced by subject path {subject_key}"
                        )
                        continue
                    expected_path = str(artifact_entry.get("path") or "").strip()
                    actual_path = str(raw_paths.get(subject_key) or "").strip()
                    if actual_path != expected_path:
                        failures.append(
                            f"Freudd personlighedspsykologi path {subject_key} diverged from artifact ownership contract: "
                            f"{actual_path} != {expected_path}"
                        )

    if isinstance(content_manifest_payload, dict):
        if content_manifest_payload.get("version") != 5:
            failures.append("Content manifest schema version should now be 5")
        source_meta = content_manifest_payload.get("source_meta")
        if not isinstance(source_meta, dict):
            failures.append(f"Content manifest source_meta missing or invalid in {CONTENT_MANIFEST}")
        else:
            for legacy_field in (
                "reading_master_path",
                "reading_fallback_path",
                "reading_source_used",
                "reading_fallback_used",
            ):
                if legacy_field in source_meta:
                    failures.append(
                        f"Content manifest source_meta still exposes legacy ownership field {legacy_field}"
                    )
            if source_meta.get("manual_edit_allowed") is not False:
                failures.append("Content manifest source_meta must declare manual_edit_allowed=false")
            if str(source_meta.get("generated_by") or "").strip() != "freudd_portal/manage.py rebuild_content_manifest":
                failures.append("Content manifest source_meta generated_by is missing or invalid")
            expected_reading_key_path = str(
                (owned_artifacts.get("reading_key") or {}).get("path") or PRIMARY_READING_KEY.as_posix()
            )
            if str(source_meta.get("reading_key_path") or "").strip() != expected_reading_key_path:
                failures.append(
                    f"Content manifest source_meta reading_key_path diverged from canonical ownership path: "
                    f"{source_meta.get('reading_key_path')} != {expected_reading_key_path}"
                )
            expected_ownership_path = str(ARTIFACT_OWNERSHIP)
            if str(source_meta.get("artifact_ownership_path") or "").strip() != expected_ownership_path:
                failures.append(
                    f"Content manifest source_meta artifact_ownership_path diverged from canonical contract: "
                    f"{source_meta.get('artifact_ownership_path')} != {expected_ownership_path}"
                )

    if source_catalog.exists() and lecture_bundle_index.exists() and content_manifest.exists():
        source_catalog_payload = _load_json(source_catalog)
        lecture_bundle_index_payload = _load_json(lecture_bundle_index)

        source_catalog_lectures = source_catalog_payload.get("lectures") if isinstance(source_catalog_payload, dict) else None
        manifest_lectures = content_manifest_payload.get("lectures") if isinstance(content_manifest_payload, dict) else None
        bundle_entries = lecture_bundle_index_payload.get("bundles") if isinstance(lecture_bundle_index_payload, dict) else None
        bundle_stats = lecture_bundle_index_payload.get("stats") if isinstance(lecture_bundle_index_payload, dict) else None

        if not isinstance(source_catalog_lectures, list):
            failures.append(f"Source catalog lectures missing or invalid in {SOURCE_CATALOG}")
        if not isinstance(manifest_lectures, list):
            failures.append(f"Content manifest lectures missing or invalid in {CONTENT_MANIFEST}")
        if not isinstance(bundle_entries, list):
            failures.append(f"Lecture bundle index bundles missing or invalid in {LECTURE_BUNDLE_INDEX}")
        if not isinstance(bundle_stats, dict):
            failures.append(f"Lecture bundle index stats missing or invalid in {LECTURE_BUNDLE_INDEX}")

        if (
            isinstance(source_catalog_lectures, list)
            and isinstance(manifest_lectures, list)
            and isinstance(bundle_entries, list)
            and isinstance(bundle_stats, dict)
        ):
            expected_lecture_count = len(manifest_lectures)
            if len(source_catalog_lectures) != expected_lecture_count:
                failures.append(
                    "Source catalog lecture count diverged from content manifest: "
                    f"{len(source_catalog_lectures)} != {expected_lecture_count}"
                )
            if int(bundle_stats.get("lecture_count") or 0) != expected_lecture_count:
                failures.append(
                    "Lecture bundle index lecture count diverged from content manifest: "
                    f"{bundle_stats.get('lecture_count')} != {expected_lecture_count}"
                )
            ready_count = sum(1 for entry in bundle_entries if isinstance(entry, dict) and entry.get("bundle_status") == "ready")
            partial_count = sum(1 for entry in bundle_entries if isinstance(entry, dict) and entry.get("bundle_status") != "ready")
            if int(bundle_stats.get("ready_bundle_count") or 0) != ready_count:
                failures.append(
                    "Lecture bundle index ready count is inconsistent with bundle entries: "
                    f"{bundle_stats.get('ready_bundle_count')} != {ready_count}"
                )
            if int(bundle_stats.get("partial_bundle_count") or 0) != partial_count:
                failures.append(
                    "Lecture bundle index partial count is inconsistent with bundle entries: "
                    f"{bundle_stats.get('partial_bundle_count')} != {partial_count}"
                )
            for entry in bundle_entries:
                if not isinstance(entry, dict):
                    failures.append(f"Invalid lecture bundle entry in {LECTURE_BUNDLE_INDEX}")
                    continue
                lecture_key = str(entry.get("lecture_key") or "").strip()
                relative_path = str(entry.get("relative_path") or "").strip()
                if not lecture_key:
                    failures.append(f"Lecture bundle entry missing lecture_key in {LECTURE_BUNDLE_INDEX}")
                    continue
                expected_bundle_path = lecture_bundles_dir / f"{lecture_key}.json"
                if relative_path and relative_path != expected_bundle_path.name:
                    failures.append(
                        "Lecture bundle entry path mismatch: "
                        f"{lecture_key} -> {relative_path} != {expected_bundle_path.name}"
                    )
                if not expected_bundle_path.exists():
                    failures.append(f"Missing lecture bundle file: {LECTURE_BUNDLES_DIR / expected_bundle_path.name}")

    glossary_payload = _load_json(course_glossary) if course_glossary.exists() else None
    theory_map_payload = _load_json(course_theory_map) if course_theory_map.exists() else None
    staleness_payload = _load_json(source_intelligence_staleness) if source_intelligence_staleness.exists() else None
    source_weighting_payload = _load_json(source_weighting) if source_weighting.exists() else None
    concept_graph_payload = _load_json(course_concept_graph) if course_concept_graph.exists() else None

    glossary_terms = glossary_payload.get("terms") if isinstance(glossary_payload, dict) else None
    theory_entries = theory_map_payload.get("theories") if isinstance(theory_map_payload, dict) else None
    theory_relations = theory_map_payload.get("relations") if isinstance(theory_map_payload, dict) else None
    if isinstance(glossary_terms, list):
        term_ids = {
            str(term.get("term_id") or "").strip()
            for term in glossary_terms
            if isinstance(term, dict) and str(term.get("term_id") or "").strip()
        }
        if int((glossary_payload.get("stats") or {}).get("term_count") or 0) != len(glossary_terms):
            failures.append(
                f"Course glossary stats term_count mismatch in {COURSE_GLOSSARY}"
            )
        for term in glossary_terms:
            if not isinstance(term, dict):
                failures.append(f"Invalid glossary term entry in {COURSE_GLOSSARY}")
                continue
            for linked_term in term.get("linked_terms", []):
                if str(linked_term).strip() not in term_ids:
                    failures.append(
                        f"Glossary term {term.get('term_id')} links missing term {linked_term}"
                    )
            for lecture_key in term.get("lecture_keys", []):
                if not (lecture_bundles_dir / f"{lecture_key}.json").exists():
                    failures.append(
                        f"Glossary term {term.get('term_id')} references missing lecture bundle {lecture_key}"
                    )
    else:
        failures.append(f"Course glossary terms missing or invalid in {COURSE_GLOSSARY}")
        term_ids = set()

    if isinstance(theory_entries, list):
        theory_ids = {
            str(theory.get("theory_id") or "").strip()
            for theory in theory_entries
            if isinstance(theory, dict) and str(theory.get("theory_id") or "").strip()
        }
        if int((theory_map_payload.get("stats") or {}).get("theory_count") or 0) != len(theory_entries):
            failures.append(
                f"Course theory map stats theory_count mismatch in {COURSE_THEORY_MAP}"
            )
        if not isinstance(theory_relations, list):
            failures.append(f"Course theory map relations missing or invalid in {COURSE_THEORY_MAP}")
        for theory in theory_entries:
            if not isinstance(theory, dict):
                failures.append(f"Invalid theory entry in {COURSE_THEORY_MAP}")
                continue
            for term_id in theory.get("core_term_ids", []):
                if str(term_id).strip() not in term_ids:
                    failures.append(
                        f"Theory {theory.get('theory_id')} references missing core term {term_id}"
                    )
            for lecture_key in theory.get("lecture_keys", []):
                if not (lecture_bundles_dir / f"{lecture_key}.json").exists():
                    failures.append(
                        f"Theory {theory.get('theory_id')} references missing lecture bundle {lecture_key}"
                    )
            for related in theory.get("related_theories", []):
                related_id = str((related or {}).get("theory_id") or "").strip()
                if related_id and related_id not in theory_ids:
                    failures.append(
                        f"Theory {theory.get('theory_id')} links missing theory {related_id}"
                    )
    else:
        failures.append(f"Course theory entries missing or invalid in {COURSE_THEORY_MAP}")
        theory_ids = set()

    if isinstance(theory_relations, list):
        if int((theory_map_payload.get("stats") or {}).get("relation_count") or 0) != len(theory_relations):
            failures.append(
                f"Course theory map stats relation_count mismatch in {COURSE_THEORY_MAP}"
            )
        for relation in theory_relations:
            if not isinstance(relation, dict):
                failures.append(f"Invalid theory relation entry in {COURSE_THEORY_MAP}")
                continue
            source_theory_id = str(relation.get("source_theory_id") or "").strip()
            target_theory_id = str(relation.get("target_theory_id") or "").strip()
            if source_theory_id and source_theory_id not in theory_ids:
                failures.append(
                    f"Theory relation references missing source theory {source_theory_id}"
                )
            if target_theory_id and target_theory_id not in theory_ids:
                failures.append(
                    f"Theory relation references missing target theory {target_theory_id}"
                )
            for term_id in relation.get("supporting_term_ids", []):
                if str(term_id).strip() not in term_ids:
                    failures.append(
                        f"Theory relation references missing supporting term {term_id}"
                    )

    if isinstance(staleness_payload, dict):
        artifacts = staleness_payload.get("artifacts")
        if not isinstance(artifacts, dict):
            failures.append(f"Staleness index artifacts missing or invalid in {SOURCE_INTELLIGENCE_STALENESS}")
        else:
            for required_key in [
                "source_catalog",
                "lecture_bundle_index",
                "lecture_bundles",
                "semantic_seed",
                "builder_script",
                "course_glossary",
                "course_theory_map",
                "source_weighting",
                "course_concept_graph",
            ]:
                if required_key not in artifacts:
                    failures.append(
                        f"Staleness index missing artifact key {required_key} in {SOURCE_INTELLIGENCE_STALENESS}"
                    )
            for artifact_key, artifact in artifacts.items():
                if not isinstance(artifact, dict):
                    failures.append(f"Staleness artifact entry {artifact_key} is invalid in {SOURCE_INTELLIGENCE_STALENESS}")
                    continue
                relative_path = str(artifact.get("path") or "").strip()
                if relative_path:
                    artifact_path = repo_root / relative_path
                    if not artifact_path.exists():
                        failures.append(
                            f"Staleness artifact {artifact_key} points to missing file {relative_path}"
                        )
                    else:
                        recorded_sha = str(artifact.get("sha256") or "").strip()
                        if recorded_sha and _sha256_file(artifact_path) != recorded_sha:
                            failures.append(
                                f"Staleness artifact {artifact_key} sha mismatch for {relative_path}"
                            )
            derivation_by_artifact_path = {
                str(entry.get("artifact_path") or "").strip(): entry
                for entry in staleness_payload.get("derivations", [])
                if isinstance(entry, dict) and str(entry.get("artifact_path") or "").strip()
            }
            for artifact_key, artifact in artifacts.items():
                if not isinstance(artifact, dict):
                    continue
                signature = str(artifact.get("input_signature_sha256") or "").strip()
                relative_path = str(artifact.get("path") or "").strip()
                if not signature or not relative_path:
                    continue
                derivation = derivation_by_artifact_path.get(relative_path)
                if not isinstance(derivation, dict):
                    failures.append(
                        f"Staleness artifact {artifact_key} is missing a derivation entry for {relative_path}"
                    )
                    continue
                dependency_paths = [
                    repo_root / str(dep).strip()
                    for dep in derivation.get("depends_on", [])
                    if str(dep).strip()
                ]
                missing_dependencies = [str(path.relative_to(repo_root)) for path in dependency_paths if not path.exists()]
                if missing_dependencies:
                    failures.append(
                        f"Staleness artifact {artifact_key} has missing dependencies: {', '.join(missing_dependencies)}"
                    )
                    continue
                expected_signature = hashlib.sha256(
                    "\n".join(_sha256_file(path) for path in dependency_paths).encode("utf-8")
                ).hexdigest()
                if expected_signature != signature:
                    failures.append(
                        f"Staleness artifact {artifact_key} input signature mismatch for {relative_path}"
                    )
    else:
        failures.append(f"Staleness index missing or invalid in {SOURCE_INTELLIGENCE_STALENESS}")

    weighting_entries = source_weighting_payload.get("sources") if isinstance(source_weighting_payload, dict) else None
    weighting_lectures = source_weighting_payload.get("lectures") if isinstance(source_weighting_payload, dict) else None
    if isinstance(weighting_entries, list) and isinstance(weighting_lectures, list):
        if int((source_weighting_payload.get("stats") or {}).get("source_count") or 0) != len(weighting_entries):
            failures.append(f"Source weighting stats source_count mismatch in {SOURCE_WEIGHTING}")
        if int((source_weighting_payload.get("stats") or {}).get("lecture_count") or 0) != len(weighting_lectures):
            failures.append(f"Source weighting stats lecture_count mismatch in {SOURCE_WEIGHTING}")
        for lecture in weighting_lectures:
            if not isinstance(lecture, dict):
                failures.append(f"Invalid lecture weighting entry in {SOURCE_WEIGHTING}")
                continue
            lecture_key = str(lecture.get("lecture_key") or "").strip()
            if lecture_key and not (lecture_bundles_dir / f"{lecture_key}.json").exists():
                failures.append(
                    f"Source weighting references missing lecture bundle {lecture_key}"
                )
        if isinstance(glossary_terms, list):
            for entry in weighting_entries:
                if not isinstance(entry, dict):
                    failures.append(f"Invalid source weighting entry in {SOURCE_WEIGHTING}")
                    continue
                for term_id in entry.get("term_ids", []):
                    if str(term_id).strip() not in term_ids:
                        failures.append(
                            f"Source weighting entry {entry.get('source_id')} references missing term {term_id}"
                        )
                for theory_id in entry.get("theory_ids", []):
                    if str(theory_id).strip() not in theory_ids:
                        failures.append(
                            f"Source weighting entry {entry.get('source_id')} references missing theory {theory_id}"
                        )
    else:
        failures.append(f"Source weighting payload missing or invalid in {SOURCE_WEIGHTING}")

    concept_nodes = concept_graph_payload.get("nodes") if isinstance(concept_graph_payload, dict) else None
    concept_edges = concept_graph_payload.get("edges") if isinstance(concept_graph_payload, dict) else None
    concept_distinctions = concept_graph_payload.get("distinctions") if isinstance(concept_graph_payload, dict) else None
    if isinstance(concept_nodes, list) and isinstance(concept_edges, list) and isinstance(concept_distinctions, list):
        concept_stats = concept_graph_payload.get("stats") if isinstance(concept_graph_payload, dict) else {}
        if int((concept_stats or {}).get("node_count") or 0) != len(concept_nodes):
            failures.append(f"Course concept graph stats node_count mismatch in {COURSE_CONCEPT_GRAPH}")
        if int((concept_stats or {}).get("edge_count") or 0) != len(concept_edges):
            failures.append(f"Course concept graph stats edge_count mismatch in {COURSE_CONCEPT_GRAPH}")
        if int((concept_stats or {}).get("distinction_count") or 0) != len(concept_distinctions):
            failures.append(f"Course concept graph stats distinction_count mismatch in {COURSE_CONCEPT_GRAPH}")
        node_ids = {
            str(node.get("node_id") or "").strip()
            for node in concept_nodes
            if isinstance(node, dict) and str(node.get("node_id") or "").strip()
        }
        for edge in concept_edges:
            if not isinstance(edge, dict):
                failures.append(f"Invalid concept graph edge entry in {COURSE_CONCEPT_GRAPH}")
                continue
            source_id = str(edge.get("source_id") or "").strip()
            target_id = str(edge.get("target_id") or "").strip()
            if source_id and source_id not in node_ids:
                failures.append(f"Concept graph edge references missing source node {source_id}")
            if target_id and target_id not in node_ids:
                failures.append(f"Concept graph edge references missing target node {target_id}")
        for distinction in concept_distinctions:
            if not isinstance(distinction, dict):
                failures.append(f"Invalid distinction entry in {COURSE_CONCEPT_GRAPH}")
                continue
            for term_id in distinction.get("term_ids", []):
                if str(term_id).strip() not in term_ids:
                    failures.append(
                        f"Concept graph distinction {distinction.get('distinction_id')} references missing term {term_id}"
                    )
    else:
        failures.append(f"Course concept graph payload missing or invalid in {COURSE_CONCEPT_GRAPH}")

    for relative_path in REFERENCE_FILES:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"Reference file missing: {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        for forbidden, description in FORBIDDEN_REFERENCES.items():
            if forbidden in content:
                failures.append(f"{description} still present in {relative_path}")

    return failures


def main() -> int:
    repo_root = _repo_root()
    failures = _failures(repo_root)
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1
    print("OK: Personlighedspsykologi artifact invariants hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
