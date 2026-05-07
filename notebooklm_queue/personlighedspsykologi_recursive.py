"""Course-specific recursive preprocessing builders for Personlighedspsykologi."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_queue.course_context import canonicalize_lecture_key
from notebooklm_queue.gemini_preprocessing import (
    DEFAULT_GEMINI_PREPROCESSING_MODEL,
    GeminiPreprocessingBackend,
    generate_json,
    generation_config_metadata,
    make_gemini_backend,
)
from notebooklm_queue.json_artifact_utils import (
    semantic_fingerprint,
    semantic_file_fingerprint,
    write_json_stably,
)
from notebooklm_queue.personlighedspsykologi_prompt_versions import configured_prompt_versions
from notebooklm_queue.source_intelligence_schemas import (
    RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION,
    utc_now_iso,
    validate_course_synthesis,
    validate_lecture_substrate,
    validate_podcast_substrate,
    validate_revised_lecture_substrate,
    validate_source_card,
)

SUBJECT_SLUG = "personlighedspsykologi"
COURSE_TITLE = "Personlighedspsykologi"
DEFAULT_SHOW_DIR = Path("shows/personlighedspsykologi-en")
DEFAULT_SOURCE_CATALOG = DEFAULT_SHOW_DIR / "source_catalog.json"
DEFAULT_POLICY_PATH = DEFAULT_SHOW_DIR / "source_intelligence_policy.json"
DEFAULT_LECTURE_BUNDLE_DIR = DEFAULT_SHOW_DIR / "lecture_bundles"
DEFAULT_RECURSIVE_DIR = DEFAULT_SHOW_DIR / "source_intelligence"
DEFAULT_SOURCE_CARD_DIR = DEFAULT_RECURSIVE_DIR / "source_cards"
DEFAULT_LECTURE_SUBSTRATE_DIR = DEFAULT_RECURSIVE_DIR / "lecture_substrates"
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = DEFAULT_RECURSIVE_DIR / "revised_lecture_substrates"
DEFAULT_PODCAST_SUBSTRATE_DIR = DEFAULT_RECURSIVE_DIR / "podcast_substrates"
DEFAULT_COURSE_SYNTHESIS_PATH = DEFAULT_RECURSIVE_DIR / "course_synthesis.json"
DEFAULT_RECURSIVE_INDEX_PATH = DEFAULT_RECURSIVE_DIR / "index.json"
DEFAULT_SOURCE_WEIGHTING_PATH = DEFAULT_SHOW_DIR / "source_weighting.json"
DEFAULT_COURSE_GLOSSARY_PATH = DEFAULT_SHOW_DIR / "course_glossary.json"
DEFAULT_COURSE_THEORY_MAP_PATH = DEFAULT_SHOW_DIR / "course_theory_map.json"
DEFAULT_CONCEPT_GRAPH_PATH = DEFAULT_SHOW_DIR / "course_concept_graph.json"
DEFAULT_SUBJECT_ROOT = Path(
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi"
)

PROMPT_VERSIONS = configured_prompt_versions()

JsonGenerator = Callable[..., dict[str, Any]]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    stored_payload, _ = write_json_stably(path, payload)
    if isinstance(stored_payload, dict):
        return stored_payload
    return payload


def format_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def signature_for_hashes(hashes: list[str]) -> str:
    return sha256_bytes("\n".join(hashes).encode("utf-8"))


def signature_for_files(paths: list[Path]) -> str:
    existing = [path for path in paths if path.exists() and path.is_file()]
    return signature_for_hashes([sha256_file(path) for path in existing])


def semantic_signature_for_artifacts(
    paths: list[Path],
    *,
    validator: Callable[[object], dict[str, Any]],
) -> str:
    fingerprints: list[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        fingerprints.append(semantic_fingerprint(validator(load_json(path))))
    return signature_for_hashes(fingerprints)


def semantic_fingerprint_for_artifact(
    path: Path,
    *,
    validator: Callable[[object], dict[str, Any]],
) -> str:
    return semantic_fingerprint(validator(load_json(path)))


def maybe_semantic_file_fingerprint(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return semantic_file_fingerprint(path)


def signature_for_source_records(sources: list[dict[str, Any]]) -> str:
    hashes: list[str] = []
    for source in sources:
        if not source.get("source_exists"):
            continue
        hashes.extend(_source_record_hashes(source))
    return signature_for_hashes(hashes)


def _source_record_hashes(source: dict[str, Any]) -> list[str]:
    file_info = source.get("file") if isinstance(source.get("file"), dict) else {}
    parts = file_info.get("parts") if isinstance(file_info.get("parts"), list) else []
    part_hashes = [str(part.get("sha256") or "").strip() for part in parts if isinstance(part, dict) and str(part.get("sha256") or "").strip()]
    if part_hashes:
        return part_hashes
    source_hash = str(file_info.get("sha256") or "").strip()
    return [source_hash] if source_hash else []


def _legacy_source_file_dependency(source: dict[str, Any]) -> str:
    hashes = _source_record_hashes(source)
    if len(hashes) == 1:
        return hashes[0]
    return signature_for_hashes(hashes)


def count_error_results(results: list[dict[str, Any]]) -> int:
    return sum(1 for item in results if item.get("status") in {"error", "missing_local_file"})


def normalize_lecture_keys(raw: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if raw is None:
        return []
    values: list[str] = []
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    else:
        for item in raw:
            values.extend(str(item).split(","))
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = canonicalize_lecture_key(value)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _load_source_catalog(source_catalog_path: Path) -> dict[str, Any]:
    payload = load_json(source_catalog_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise RuntimeError(f"invalid source catalog: {source_catalog_path}")
    return payload


def _source_catalog_lecture_keys(catalog: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for lecture in catalog.get("lectures", []):
        if not isinstance(lecture, dict):
            continue
        key = canonicalize_lecture_key(str(lecture.get("lecture_key") or ""))
        if key:
            keys.append(key)
    return keys


def _selected_sources(
    catalog: dict[str, Any],
    *,
    lecture_keys: list[str],
    source_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    allowed_lectures = set(lecture_keys)
    allowed_sources = set(source_ids or [])
    selected: list[dict[str, Any]] = []
    for source in catalog.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "").strip()
        lecture_key = canonicalize_lecture_key(str(source.get("lecture_key") or ""))
        if allowed_sources and source_id not in allowed_sources:
            continue
        if allowed_lectures and lecture_key not in allowed_lectures:
            continue
        selected.append(source)
    return selected


def source_file_path(subject_root: Path, source: dict[str, Any]) -> Path:
    paths = source_file_paths(subject_root, source)
    if not paths:
        raise RuntimeError(f"source has no subject_relative_path: {source.get('source_id')}")
    return paths[0]


def source_relative_paths(source: dict[str, Any]) -> list[str]:
    relative_paths: list[str] = []
    raw_relative_paths = source.get("subject_relative_paths")
    if isinstance(raw_relative_paths, list):
        relative_paths.extend(str(item or "").strip() for item in raw_relative_paths if str(item or "").strip())
    raw_file_parts = (source.get("file") or {}).get("parts") if isinstance(source.get("file"), dict) else None
    if isinstance(raw_file_parts, list):
        for part in raw_file_parts:
            if not isinstance(part, dict):
                continue
            relative_path = str(part.get("subject_relative_path") or "").strip()
            if relative_path:
                relative_paths.append(relative_path)
    relative_path = str(source.get("subject_relative_path") or "").strip()
    if relative_path:
        relative_paths.append(relative_path)

    paths: list[Path] = []
    seen: set[str] = set()
    for relative_path in relative_paths:
        if relative_path in seen:
            continue
        seen.add(relative_path)
        paths.append(relative_path)
    return paths


def source_file_paths(subject_root: Path, source: dict[str, Any]) -> list[Path]:
    return [subject_root / relative_path for relative_path in source_relative_paths(source)]


def _source_card_path(source_card_dir: Path, source_id: str) -> Path:
    return source_card_dir / f"{source_id}.json"


def _lecture_substrate_path(lecture_substrate_dir: Path, lecture_key: str) -> Path:
    return lecture_substrate_dir / f"{lecture_key}.json"


def _coerce_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _analysis_from_response(
    response: dict[str, Any],
    *,
    string_fields: list[str],
    list_fields: list[str],
    dict_fields: list[str] | None = None,
) -> dict[str, Any]:
    raw = response.get("analysis")
    if not isinstance(raw, dict):
        raw = response
    analysis: dict[str, Any] = {}
    for field in string_fields:
        analysis[field] = _coerce_string(raw.get(field))
    for field in list_fields:
        analysis[field] = _coerce_list(raw.get(field))
    for field in dict_fields or []:
        analysis[field] = _coerce_dict(raw.get(field))
    return analysis


def _call_json_generator(
    *,
    backend: GeminiPreprocessingBackend | None,
    json_generator: JsonGenerator | None,
    model: str,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path] | None = None,
    max_output_tokens: int = 8192,
    response_json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if json_generator is not None:
        return json_generator(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            source_paths=source_paths or [],
            max_output_tokens=max_output_tokens,
        )
    active_backend = backend or make_gemini_backend(model=model)
    return generate_json(
        backend=active_backend,
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        source_paths=source_paths or [],
        max_output_tokens=max_output_tokens,
        response_json_schema=response_json_schema,
    )


def _string_schema(description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if description:
        schema["description"] = description
    return schema


def _string_list_schema(*, min_items: int = 0, description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if min_items:
        schema["minItems"] = min_items
    if description:
        schema["description"] = description
    return schema


def _object_list_schema(*, min_items: int = 0, description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "object"}}
    if min_items:
        schema["minItems"] = min_items
    if description:
        schema["description"] = description
    return schema


def _analysis_response_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        },
        "required": ["analysis"],
    }


def _source_card_response_schema() -> dict[str, Any]:
    central_claim_schema = {
        "type": "object",
        "properties": {
            "claim": _string_schema("Concrete claim grounded in the attached source."),
            "grounding": _string_schema("One of: source-grounded, slide-framed, course-inferred."),
            "confidence": _string_schema("One of: high, medium, low."),
        },
        "required": ["claim", "grounding", "confidence"],
    }
    key_concept_schema = {
        "type": "object",
        "properties": {
            "term": _string_schema("Source-specific concept term."),
            "definition": _string_schema("Course-relevant definition from the attached source."),
            "role": _string_schema("Why this concept matters for the lecture."),
        },
        "required": ["term", "definition", "role"],
    }
    distinction_schema = {
        "type": "object",
        "properties": {
            "label": _string_schema("Name of the distinction."),
            "summary": _string_schema("What is being distinguished."),
            "stakes": _string_schema("Why the distinction matters."),
        },
        "required": ["label", "summary", "stakes"],
    }
    quote_target_schema = {
        "type": "object",
        "properties": {
            "target": _string_schema("Short phrase, section, or page target if available."),
            "why": _string_schema("Why the student should look for it."),
        },
        "required": ["target", "why"],
    }
    return _analysis_response_schema(
        {
            "central_claims": {"type": "array", "items": central_claim_schema, "minItems": 2},
            "key_concepts": {"type": "array", "items": key_concept_schema, "minItems": 2},
            "distinctions": {"type": "array", "items": distinction_schema},
            "theory_role": _string_schema(),
            "source_role": _string_schema(),
            "relation_to_lecture": _string_schema(),
            "likely_misunderstandings": _string_list_schema(),
            "quote_targets": {"type": "array", "items": quote_target_schema},
            "grounding_notes": _string_list_schema(),
            "warnings": _string_list_schema(),
        },
        [
            "central_claims",
            "key_concepts",
            "distinctions",
            "theory_role",
            "source_role",
            "relation_to_lecture",
            "likely_misunderstandings",
            "quote_targets",
            "grounding_notes",
            "warnings",
        ],
    )


def _lecture_substrate_response_schema() -> dict[str, Any]:
    return _analysis_response_schema(
        {
            "lecture_question": _string_schema(),
            "central_learning_problem": _string_schema(),
            "source_roles": _object_list_schema(min_items=1),
            "source_relations": _object_list_schema(),
            "core_concepts": _object_list_schema(min_items=1),
            "core_tensions": _object_list_schema(),
            "likely_misunderstandings": _string_list_schema(),
            "must_carry_ideas": _string_list_schema(min_items=1),
            "missing_sources": _object_list_schema(),
            "warnings": _string_list_schema(),
        },
        [
            "lecture_question",
            "central_learning_problem",
            "source_roles",
            "source_relations",
            "core_concepts",
            "core_tensions",
            "likely_misunderstandings",
            "must_carry_ideas",
            "missing_sources",
            "warnings",
        ],
    )


def _course_synthesis_response_schema() -> dict[str, Any]:
    return _analysis_response_schema(
        {
            "course_arc": _string_schema(),
            "theory_tradition_map": _object_list_schema(min_items=1),
            "concept_map": _object_list_schema(min_items=1),
            "distinction_map": _object_list_schema(),
            "sideways_relations": _object_list_schema(),
            "lecture_clusters": _object_list_schema(),
            "top_down_priorities": _object_list_schema(min_items=1),
            "weak_spots": _string_list_schema(),
            "podcast_generation_guidance": _string_list_schema(),
        },
        [
            "course_arc",
            "theory_tradition_map",
            "concept_map",
            "distinction_map",
            "sideways_relations",
            "lecture_clusters",
            "top_down_priorities",
            "weak_spots",
            "podcast_generation_guidance",
        ],
    )


def _downward_revision_response_schema() -> dict[str, Any]:
    return _analysis_response_schema(
        {
            "what_matters_more": _string_list_schema(min_items=1),
            "de_emphasize": _string_list_schema(),
            "strongest_sideways_connections": _object_list_schema(),
            "top_down_course_relevance": _string_schema(),
            "revised_podcast_priorities": _string_list_schema(min_items=1),
            "carry_forward": _string_list_schema(min_items=1),
            "warnings": _string_list_schema(),
        },
        [
            "what_matters_more",
            "de_emphasize",
            "strongest_sideways_connections",
            "top_down_course_relevance",
            "revised_podcast_priorities",
            "carry_forward",
            "warnings",
        ],
    )


def _podcast_substrate_response_schema() -> dict[str, Any]:
    list_schema = _string_list_schema()
    required_section = {
        "type": "object",
        "properties": {
            "angle": _string_schema(),
            "must_cover": _string_list_schema(min_items=1),
            "avoid": list_schema,
        },
        "required": ["angle", "must_cover", "avoid"],
    }
    return {
        "type": "object",
        "properties": {
            "podcast": {
                "type": "object",
                "properties": {
                    "weekly": {
                        "type": "object",
                        "properties": {
                            "angle": _string_schema(),
                            "must_cover": _string_list_schema(min_items=1),
                            "avoid": list_schema,
                            "grounding": list_schema,
                        },
                        "required": ["angle", "must_cover", "avoid", "grounding"],
                    },
                    "per_reading": _object_list_schema(),
                    "per_slide": _object_list_schema(),
                    "short": required_section,
                    "selected_concepts": _object_list_schema(min_items=1),
                    "selected_tensions": _object_list_schema(),
                    "grounding_notes": list_schema,
                    "source_selection": _object_list_schema(),
                },
                "required": [
                    "weekly",
                    "per_reading",
                    "per_slide",
                    "short",
                    "selected_concepts",
                    "selected_tensions",
                    "grounding_notes",
                    "source_selection",
                ],
            }
        },
        "required": ["podcast"],
    }


def _source_identity(source: dict[str, Any], source_paths: list[Path], repo_root: Path, subject_root: Path) -> dict[str, Any]:
    file_info = source.get("file") if isinstance(source.get("file"), dict) else {}
    source_exists = bool(source.get("source_exists"))
    source_sha256 = str(file_info.get("sha256") or "").strip()
    existing_paths = [path for path in source_paths if path.exists() and path.is_file()]
    if source_exists and existing_paths:
        source_sha256 = sha256_file(existing_paths[0]) if len(existing_paths) == 1 else signature_for_files(existing_paths)
    source_path = existing_paths[0] if existing_paths else (source_paths[0] if source_paths else Path(""))
    source_relative_paths: list[str] = []
    for path in source_paths:
        try:
            source_relative_paths.append(str(path.resolve().relative_to(subject_root.resolve())))
        except ValueError:
            source_relative_paths.append(str(path))
    return {
        "source_id": str(source.get("source_id") or "").strip(),
        "lecture_key": canonicalize_lecture_key(str(source.get("lecture_key") or "")),
        "title": str(source.get("title") or "").strip(),
        "source_family": str(source.get("source_family") or "").strip(),
        "evidence_origin": str(source.get("evidence_origin") or "").strip(),
        "source_path": source_relative_paths[0] if source_relative_paths else str(source.get("subject_relative_path") or ""),
        "source_paths": source_relative_paths,
        "repo_display_path": display_path(source_path, repo_root) if source_paths else "",
        "repo_display_paths": [display_path(path, repo_root) for path in source_paths],
        "source_exists": source_exists,
        "source_sha256": source_sha256,
        "length_band": str(source.get("length_band") or "").strip(),
        "page_count": file_info.get("page_count"),
        "estimated_token_count": file_info.get("estimated_token_count"),
        "text_extraction_status": str(file_info.get("text_extraction_status") or "").strip(),
    }


def _build_metadata(
    *,
    artifact_type: str,
    model: str,
    dependency_hashes: dict[str, str],
    input_source_ids: list[str],
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "schema_version": RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "build": {
            "model": model,
            "prompt_version": PROMPT_VERSIONS[artifact_type],
            "generation_config": generation_config_metadata(),
        },
        "provenance": {
            "input_source_ids": input_source_ids,
            "dependency_hashes": dependency_hashes,
        },
    }


def _dependencies(payload: dict[str, Any]) -> dict[str, Any]:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return {}
    dependencies = provenance.get("dependency_hashes")
    return dependencies if isinstance(dependencies, dict) else {}


def _artifact_input_source_ids(payload: dict[str, Any]) -> list[str]:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return []
    return [str(item or "").strip() for item in provenance.get("input_source_ids", []) if str(item or "").strip()]


def _bundle_input_source_ids(bundle: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    seen: set[str] = set()
    for source in _bundle_source_entries(bundle):
        if not source.get("source_exists"):
            continue
        source_id = str(source.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        source_ids.append(source_id)
    return source_ids


def _legacy_source_identity_projection(source: dict[str, Any], source_paths: list[Path]) -> dict[str, Any]:
    file_info = source.get("file") if isinstance(source.get("file"), dict) else {}
    existing_paths = [path for path in source_paths if path.exists() and path.is_file()]
    source_sha256 = str(file_info.get("sha256") or "").strip()
    if existing_paths:
        source_sha256 = sha256_file(existing_paths[0]) if len(existing_paths) == 1 else signature_for_files(existing_paths)
    relative_paths = source_relative_paths(source)
    return {
        "source_id": str(source.get("source_id") or "").strip(),
        "lecture_key": canonicalize_lecture_key(str(source.get("lecture_key") or "")),
        "title": str(source.get("title") or "").strip(),
        "source_family": str(source.get("source_family") or "").strip(),
        "evidence_origin": str(source.get("evidence_origin") or "").strip(),
        "source_path": relative_paths[0] if relative_paths else str(source.get("subject_relative_path") or ""),
        "source_paths": relative_paths,
        "source_exists": bool(source.get("source_exists")),
        "source_sha256": source_sha256,
        "length_band": str(source.get("length_band") or "").strip(),
        "page_count": file_info.get("page_count"),
        "estimated_token_count": file_info.get("estimated_token_count"),
        "text_extraction_status": str(file_info.get("text_extraction_status") or "").strip(),
    }


def _legacy_source_identity_matches(
    artifact_source: dict[str, Any],
    *,
    source: dict[str, Any],
    source_paths: list[Path],
) -> bool:
    expected = _legacy_source_identity_projection(source, source_paths)
    return all(artifact_source.get(key) == value for key, value in expected.items())


def _source_card_dependency_hashes(
    *,
    source: dict[str, Any],
    source_paths: list[Path],
    policy_path: Path,
) -> dict[str, str]:
    return {
        "source_files_signature": signature_for_files(source_paths),
        "source_record_fingerprint": semantic_fingerprint(source),
        "source_intelligence_policy_fingerprint": maybe_semantic_file_fingerprint(policy_path),
    }


def _lecture_substrate_dependency_hashes(
    *,
    bundle: dict[str, Any],
    source_card_paths: list[Path],
    raw_source_paths: list[Path],
) -> dict[str, str]:
    return {
        "lecture_bundle_fingerprint": semantic_fingerprint(bundle),
        "source_cards_signature": semantic_signature_for_artifacts(
            source_card_paths,
            validator=validate_source_card,
        ),
        "raw_sources_signature": signature_for_files(raw_source_paths),
    }


def _course_synthesis_dependency_hashes(
    *,
    lecture_substrate_paths: list[Path],
    glossary_path: Path,
    theory_map_path: Path,
    concept_graph_path: Path,
) -> dict[str, str]:
    return {
        "lecture_substrates_signature": semantic_signature_for_artifacts(
            lecture_substrate_paths,
            validator=validate_lecture_substrate,
        ),
        "course_glossary_fingerprint": maybe_semantic_file_fingerprint(glossary_path),
        "course_theory_map_fingerprint": maybe_semantic_file_fingerprint(theory_map_path),
        "concept_graph_fingerprint": maybe_semantic_file_fingerprint(concept_graph_path),
    }


def _revised_lecture_substrate_dependency_hashes(
    *,
    lecture_path: Path,
    course_synthesis_path: Path,
) -> dict[str, str]:
    return {
        "lecture_substrate_fingerprint": semantic_fingerprint_for_artifact(
            lecture_path,
            validator=validate_lecture_substrate,
        ),
        "course_synthesis_fingerprint": semantic_fingerprint_for_artifact(
            course_synthesis_path,
            validator=validate_course_synthesis,
        ),
    }


def _podcast_substrate_dependency_hashes(
    *,
    revised_path: Path,
    course_synthesis_path: Path,
    source_card_paths: list[Path],
    source_weighting_path: Path,
) -> dict[str, str]:
    return {
        "revised_lecture_substrate_fingerprint": semantic_fingerprint_for_artifact(
            revised_path,
            validator=validate_revised_lecture_substrate,
        ),
        "course_synthesis_fingerprint": semantic_fingerprint_for_artifact(
            course_synthesis_path,
            validator=validate_course_synthesis,
        ),
        "source_cards_signature": semantic_signature_for_artifacts(
            source_card_paths,
            validator=validate_source_card,
        ),
        "source_weighting_fingerprint": maybe_semantic_file_fingerprint(source_weighting_path),
    }


def _source_card_stale_reasons(
    *,
    artifact: dict[str, Any],
    source: dict[str, Any],
    source_paths: list[Path],
    policy_path: Path,
) -> list[str]:
    dependencies = _dependencies(artifact)
    reasons: list[str] = []
    if all(source_path.exists() and source_path.is_file() for source_path in source_paths):
        source_signature = signature_for_files(source_paths)
        legacy_source_file = sha256_file(source_paths[0]) if len(source_paths) == 1 else source_signature
    else:
        source_signature = signature_for_source_records([source])
        legacy_source_file = _legacy_source_file_dependency(source)
    if dependencies.get("source_files_signature") not in {source_signature, legacy_source_file}:
        reasons.append("source_files_signature")

    policy_fingerprint = maybe_semantic_file_fingerprint(policy_path)
    legacy_policy_hash = sha256_file(policy_path) if policy_path.exists() and policy_path.is_file() else ""
    if dependencies.get("source_intelligence_policy_fingerprint") not in {policy_fingerprint, legacy_policy_hash}:
        reasons.append("source_intelligence_policy")

    if dependencies.get("source_record_fingerprint"):
        if dependencies.get("source_record_fingerprint") != semantic_fingerprint(source):
            reasons.append("source_record")
    else:
        artifact_source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
        if not _legacy_source_identity_matches(artifact_source, source=source, source_paths=source_paths):
            reasons.append("source_record")
    return reasons


def _lecture_substrate_stale_reasons(
    *,
    artifact: dict[str, Any],
    lecture_key: str,
    subject_root: Path | None,
    lecture_bundle_dir: Path,
    source_card_dir: Path,
) -> list[str]:
    bundle = _load_bundle(lecture_bundle_dir, lecture_key)
    expected_source_ids = _bundle_input_source_ids(bundle)
    source_card_paths = [_source_card_path(source_card_dir, source_id) for source_id in expected_source_ids]
    expected_dependencies = _lecture_substrate_dependency_hashes(
        bundle=bundle,
        source_card_paths=source_card_paths,
        raw_source_paths=_raw_source_paths_for_bundle(subject_root, bundle),
    )
    expected_dependencies["raw_sources_signature"] = signature_for_source_records(_bundle_source_entries(bundle))
    dependencies = _dependencies(artifact)
    reasons: list[str] = []
    if _artifact_input_source_ids(artifact) != expected_source_ids:
        reasons.append("input_source_ids")
    for key, reason in (
        ("lecture_bundle_fingerprint", "lecture_bundle"),
        ("source_cards_signature", "source_cards_signature"),
        ("raw_sources_signature", "raw_sources_signature"),
    ):
        if dependencies.get(key) != expected_dependencies[key]:
            reasons.append(reason)
    return reasons


def _course_synthesis_stale_reasons(
    *,
    artifact: dict[str, Any],
    lecture_keys: list[str],
    lecture_substrate_dir: Path,
    partial_scope: bool,
    glossary_path: Path,
    theory_map_path: Path,
    concept_graph_path: Path,
) -> list[str]:
    course = artifact.get("course") if isinstance(artifact.get("course"), dict) else {}
    existing_scope = str(course.get("scope") or "").strip()
    expected_scope = "partial" if partial_scope else "full"
    existing_keys = [canonicalize_lecture_key(str(item or "")) for item in course.get("lecture_keys", [])]
    existing_keys = [key for key in existing_keys if key]
    reasons: list[str] = []
    if existing_scope != expected_scope:
        reasons.append("scope")
    if existing_keys != lecture_keys:
        reasons.append("lecture_keys")

    expected_dependencies = _course_synthesis_dependency_hashes(
        lecture_substrate_paths=[_lecture_substrate_path(lecture_substrate_dir, key) for key in lecture_keys],
        glossary_path=glossary_path,
        theory_map_path=theory_map_path,
        concept_graph_path=concept_graph_path,
    )
    dependencies = _dependencies(artifact)
    for key, reason in (
        ("lecture_substrates_signature", "lecture_substrates_signature"),
        ("course_glossary_fingerprint", "course_glossary"),
        ("course_theory_map_fingerprint", "course_theory_map"),
        ("concept_graph_fingerprint", "concept_graph"),
    ):
        if dependencies.get(key) != expected_dependencies[key]:
            reasons.append(reason)
    return reasons


def _revised_lecture_substrate_stale_reasons(
    *,
    artifact: dict[str, Any],
    lecture_key: str,
    lecture_substrate_dir: Path,
    course_synthesis_path: Path,
) -> list[str]:
    lecture_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
    expected_dependencies = _revised_lecture_substrate_dependency_hashes(
        lecture_path=lecture_path,
        course_synthesis_path=course_synthesis_path,
    )
    reasons: list[str] = []
    if _artifact_input_source_ids(artifact) != _artifact_input_source_ids(validate_lecture_substrate(load_json(lecture_path))):
        reasons.append("input_source_ids")
    dependencies = _dependencies(artifact)
    for key, reason in (
        ("lecture_substrate_fingerprint", "lecture_substrate"),
        ("course_synthesis_fingerprint", "course_synthesis"),
    ):
        if dependencies.get(key) != expected_dependencies[key]:
            reasons.append(reason)
    return reasons


def _podcast_substrate_stale_reasons(
    *,
    artifact: dict[str, Any],
    lecture_key: str,
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    source_weighting_path: Path,
) -> list[str]:
    revised_path = _lecture_substrate_path(revised_lecture_substrate_dir, lecture_key)
    revised = validate_revised_lecture_substrate(load_json(revised_path))
    source_card_paths = [
        _source_card_path(source_card_dir, source_id)
        for source_id in _artifact_input_source_ids(revised)
    ]
    expected_dependencies = _podcast_substrate_dependency_hashes(
        revised_path=revised_path,
        course_synthesis_path=course_synthesis_path,
        source_card_paths=source_card_paths,
        source_weighting_path=source_weighting_path,
    )
    reasons: list[str] = []
    if _artifact_input_source_ids(artifact) != _artifact_input_source_ids(revised):
        reasons.append("input_source_ids")
    dependencies = _dependencies(artifact)
    for key, reason in (
        ("revised_lecture_substrate_fingerprint", "revised_lecture_substrate"),
        ("course_synthesis_fingerprint", "course_synthesis"),
        ("source_cards_signature", "source_cards_signature"),
        ("source_weighting_fingerprint", "source_weighting"),
    ):
        if dependencies.get(key) != expected_dependencies[key]:
            reasons.append(reason)
    return reasons


def source_card_is_fresh(
    *,
    path: Path,
    source: dict[str, Any],
    source_paths: list[Path],
    source_catalog_path: Path,
    policy_path: Path,
) -> bool:
    if (
        not path.exists()
        or not path.is_file()
        or not source_paths
        or not all(source_path.exists() and source_path.is_file() for source_path in source_paths)
    ):
        return False
    try:
        artifact = validate_source_card(load_json(path))
    except Exception:
        return False
    return not _source_card_stale_reasons(
        artifact=artifact,
        source=source,
        source_paths=source_paths,
        policy_path=policy_path,
    )


def lecture_substrate_is_fresh(
    *,
    path: Path,
    lecture_key: str,
    subject_root: Path | None,
    lecture_bundle_dir: Path,
    source_card_dir: Path,
    source_catalog_path: Path,
) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        artifact = validate_lecture_substrate(load_json(path))
    except Exception:
        return False
    return not _lecture_substrate_stale_reasons(
        artifact=artifact,
        lecture_key=lecture_key,
        subject_root=subject_root,
        lecture_bundle_dir=lecture_bundle_dir,
        source_card_dir=source_card_dir,
    )


def course_synthesis_is_fresh(
    *,
    path: Path,
    lecture_keys: list[str],
    lecture_substrate_dir: Path,
    source_catalog_path: Path,
    partial_scope: bool,
    glossary_path: Path = DEFAULT_COURSE_GLOSSARY_PATH,
    theory_map_path: Path = DEFAULT_COURSE_THEORY_MAP_PATH,
    concept_graph_path: Path = DEFAULT_CONCEPT_GRAPH_PATH,
) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        artifact = validate_course_synthesis(load_json(path))
    except Exception:
        return False
    return not _course_synthesis_stale_reasons(
        artifact=artifact,
        lecture_keys=lecture_keys,
        lecture_substrate_dir=lecture_substrate_dir,
        partial_scope=partial_scope,
        glossary_path=glossary_path,
        theory_map_path=theory_map_path,
        concept_graph_path=concept_graph_path,
    )


def revised_lecture_substrate_is_fresh(
    *,
    path: Path,
    lecture_key: str,
    lecture_substrate_dir: Path,
    course_synthesis_path: Path,
) -> bool:
    if not path.exists() or not path.is_file():
        return False
    lecture_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
    if not lecture_path.exists() or not course_synthesis_path.exists():
        return False
    try:
        artifact = validate_revised_lecture_substrate(load_json(path))
    except Exception:
        return False
    return not _revised_lecture_substrate_stale_reasons(
        artifact=artifact,
        lecture_key=lecture_key,
        lecture_substrate_dir=lecture_substrate_dir,
        course_synthesis_path=course_synthesis_path,
    )


def podcast_substrate_is_fresh(
    *,
    path: Path,
    lecture_key: str,
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    source_weighting_path: Path,
) -> bool:
    if not path.exists() or not path.is_file():
        return False
    revised_path = _lecture_substrate_path(revised_lecture_substrate_dir, lecture_key)
    if not revised_path.exists() or not course_synthesis_path.exists():
        return False
    try:
        artifact = validate_podcast_substrate(load_json(path))
    except Exception:
        return False
    return not _podcast_substrate_stale_reasons(
        artifact=artifact,
        lecture_key=lecture_key,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=revised_lecture_substrate_dir,
        course_synthesis_path=course_synthesis_path,
        source_weighting_path=source_weighting_path,
    )


def _source_card_system_instruction() -> str:
    return (
        "You are building a structured source card for a Danish university course in personality "
        "psychology. Read the attached source directly. Return only valid JSON. Be precise about "
        "what is source-grounded versus inferred from course metadata. Do not invent citations, "
        "studies, page numbers, or author positions."
    )


def _source_card_prompt(*, source: dict[str, Any], policy: dict[str, Any]) -> str:
    payload = {
        "course_title": COURSE_TITLE,
        "source_metadata": source,
        "course_specific_policy": policy,
        "task": (
            "Read the attached file(s) and fill every field with concrete, source-specific content. "
            "Never copy example labels or placeholder text from the field rules or response schema. If a field cannot "
            "be answered from the source, write a concrete caveat in warnings instead of a template string."
        ),
        "field_rules": {
            "central_claims": "Return 2-6 concrete claims. Each item must include claim, grounding, and confidence.",
            "key_concepts": "Return 2-8 concrete concepts. Each item must include term, definition, and role.",
            "distinctions": "Return concrete distinctions if the source contains them; otherwise use an empty list.",
            "quote_targets": "Return concrete phrases, sections, or pages to look for if available; otherwise use an empty list.",
            "warnings": "Use an empty list unless there are concrete source, OCR, confidence, or scope caveats.",
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _repair_source_card_analysis(analysis: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    warnings = _coerce_list(analysis.get("warnings"))
    title = str(source.get("title") or source.get("source_id") or "source").strip()
    lecture_key = canonicalize_lecture_key(str(source.get("lecture_key") or "")) or "the lecture"
    source_family = str(source.get("source_family") or source.get("source_kind") or "source").replace("_", " ")

    if not _coerce_string(analysis.get("source_role")):
        analysis["source_role"] = (
            f"{title} is treated as a {source_family} source for {lecture_key}; "
            "the model response omitted a more specific role."
        )
        warnings.append("source_role was empty in the model response and was filled by a fallback.")
    if not _coerce_string(analysis.get("relation_to_lecture")):
        analysis["relation_to_lecture"] = (
            f"{title} should be related to {lecture_key} according to its source metadata and source-grounded claims."
        )
        warnings.append("relation_to_lecture was empty in the model response and was filled by a fallback.")

    analysis["warnings"] = warnings
    return analysis


def build_source_card_for_source(
    *,
    repo_root: Path,
    subject_root: Path,
    source: dict[str, Any],
    source_catalog_path: Path,
    policy_path: Path,
    source_card_dir: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise RuntimeError("source is missing source_id")
    source_paths = source_file_paths(subject_root, source)
    if not source_paths:
        raise RuntimeError(f"source has no subject_relative_path: {source_id}")
    missing_paths = [path for path in source_paths if not path.exists() or not path.is_file()]
    if missing_paths:
        raise RuntimeError(f"source file not found: {missing_paths[0]}")
    policy = load_json(policy_path) if policy_path.exists() else {}
    response = _call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=_source_card_system_instruction(),
        user_prompt=_source_card_prompt(source=source, policy=policy),
        source_paths=source_paths,
        max_output_tokens=8192,
        response_json_schema=_source_card_response_schema(),
    )
    analysis = _analysis_from_response(
        response,
        string_fields=["theory_role", "source_role", "relation_to_lecture"],
        list_fields=[
            "central_claims",
            "key_concepts",
            "distinctions",
            "likely_misunderstandings",
            "quote_targets",
            "grounding_notes",
            "warnings",
        ],
    )
    analysis = _repair_source_card_analysis(analysis, source)
    artifact = {
        **_build_metadata(
            artifact_type="source_card",
            model=model,
            dependency_hashes=_source_card_dependency_hashes(
                source=source,
                source_paths=source_paths,
                policy_path=policy_path,
            ),
            input_source_ids=[source_id],
        ),
        "source": _source_identity(source, source_paths, repo_root, subject_root),
        "analysis": analysis,
    }
    validate_source_card(artifact)
    write_json(_source_card_path(source_card_dir, source_id), artifact)
    return artifact


def build_source_cards(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    policy_path: Path,
    source_card_dir: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    force: bool = False,
    skip_existing: bool = True,
    dry_run: bool = False,
    continue_on_error: bool = False,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    catalog = _load_source_catalog(source_catalog_path)
    selected = _selected_sources(catalog, lecture_keys=lecture_keys or [], source_ids=source_ids)
    results: list[dict[str, Any]] = []
    for source in selected:
        source_id = str(source.get("source_id") or "").strip()
        output_path = _source_card_path(source_card_dir, source_id)
        if not source_id:
            continue
        if not source.get("source_exists"):
            results.append({"source_id": source_id, "status": "missing_source"})
            continue
        source_paths = source_file_paths(subject_root, source)
        missing_paths = [path for path in source_paths if not path.exists() or not path.is_file()]
        if not source_paths or missing_paths:
            missing_path = missing_paths[0] if missing_paths else subject_root
            item = {
                "source_id": source_id,
                "status": "missing_local_file",
                "source_paths": [str(path) for path in source_paths],
                "source_path": str(missing_path),
                "error": f"source file not found: {missing_path}",
            }
            if dry_run or continue_on_error:
                results.append(item)
                continue
            raise RuntimeError(str(item["error"]))
        if output_path.exists() and skip_existing and not force:
            if source_card_is_fresh(
                path=output_path,
                source=source,
                source_paths=source_paths,
                source_catalog_path=source_catalog_path,
                policy_path=policy_path,
            ):
                results.append({"source_id": source_id, "status": "skipped_existing", "output_path": str(output_path)})
                continue
            if dry_run:
                results.append(
                    {
                        "source_id": source_id,
                        "status": "planned_stale_rebuild",
                        "source_paths": [str(path) for path in source_paths],
                        "source_path": str(source_paths[0]) if source_paths else "",
                    }
                )
                continue
        if dry_run:
            results.append(
                {
                    "source_id": source_id,
                    "status": "planned",
                    "source_paths": [str(path) for path in source_paths],
                    "source_path": str(source_paths[0]) if source_paths else "",
                }
            )
            continue
        try:
            build_source_card_for_source(
                repo_root=repo_root,
                subject_root=subject_root,
                source=source,
                source_catalog_path=source_catalog_path,
                policy_path=policy_path,
                source_card_dir=source_card_dir,
                model=model,
                backend=backend,
                json_generator=json_generator,
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append(
                {
                    "source_id": source_id,
                    "status": "error",
                    "source_paths": [str(path) for path in source_paths],
                    "source_path": str(source_paths[0]) if source_paths else "",
                    "error": format_error(exc),
                }
            )
            continue
        results.append({"source_id": source_id, "status": "written", "output_path": str(output_path)})
    return {
        "selected_count": len(selected),
        "written_count": sum(1 for item in results if item["status"] == "written"),
        "skipped_count": sum(1 for item in results if item["status"].startswith("skipped")),
        "missing_count": sum(1 for item in results if item["status"] == "missing_source"),
        "planned_count": sum(1 for item in results if item["status"].startswith("planned")),
        "error_count": count_error_results(results),
        "results": results,
    }


def _bundle_source_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    sources = bundle.get("sources")
    if not isinstance(sources, dict):
        return entries
    for group_name, group_entries in sources.items():
        if not isinstance(group_entries, list):
            continue
        for source in group_entries:
            if isinstance(source, dict):
                item = dict(source)
                item["bundle_group"] = group_name
                entries.append(item)
    return entries


def _load_bundle(lecture_bundle_dir: Path, lecture_key: str) -> dict[str, Any]:
    bundle_path = lecture_bundle_dir / f"{lecture_key}.json"
    if not bundle_path.exists():
        raise RuntimeError(f"lecture bundle not found: {bundle_path}")
    payload = load_json(bundle_path)
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid lecture bundle: {bundle_path}")
    return payload


def _source_cards_for_bundle(source_card_dir: Path, bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cards: list[dict[str, Any]] = []
    missing_sources: list[dict[str, Any]] = []
    for source in _bundle_source_entries(bundle):
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        if not source.get("source_exists"):
            missing_sources.append(
                {
                    "source_id": source_id,
                    "title": str(source.get("title") or "").strip(),
                    "reason": str(source.get("missing_reason") or "missing_source"),
                }
            )
            continue
        card_path = _source_card_path(source_card_dir, source_id)
        if card_path.exists() and card_path.is_file():
            cards.append(validate_source_card(load_json(card_path)))
        else:
            missing_sources.append(
                {
                    "source_id": source_id,
                    "title": str(source.get("title") or "").strip(),
                    "reason": "source_card_missing",
                }
            )
    return cards, missing_sources


def _raw_source_paths_for_bundle(subject_root: Path | None, bundle: dict[str, Any]) -> list[Path]:
    if subject_root is None:
        return []
    paths: list[Path] = []
    seen: set[Path] = set()
    for source in _bundle_source_entries(bundle):
        if not source.get("source_exists"):
            continue
        for path in source_file_paths(subject_root, source):
            if not path.exists() or not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


def _compact_source_card(card: dict[str, Any]) -> dict[str, Any]:
    analysis = card.get("analysis") if isinstance(card.get("analysis"), dict) else {}
    source = card.get("source") if isinstance(card.get("source"), dict) else {}
    return {
        "source": {
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "source_family": source.get("source_family"),
            "evidence_origin": source.get("evidence_origin"),
            "length_band": source.get("length_band"),
        },
        "analysis": {
            "central_claims": _coerce_list(analysis.get("central_claims"))[:8],
            "key_concepts": _coerce_list(analysis.get("key_concepts"))[:8],
            "distinctions": _coerce_list(analysis.get("distinctions"))[:6],
            "theory_role": _coerce_string(analysis.get("theory_role")),
            "source_role": _coerce_string(analysis.get("source_role")),
            "relation_to_lecture": _coerce_string(analysis.get("relation_to_lecture")),
            "likely_misunderstandings": _coerce_list(analysis.get("likely_misunderstandings"))[:5],
            "grounding_notes": _coerce_list(analysis.get("grounding_notes"))[:4],
            "warnings": _coerce_list(analysis.get("warnings")),
        },
    }


def _lecture_substrate_system_instruction() -> str:
    return (
        "You are building a lecture-level learning substrate for a personality psychology course. "
        "Use the supplied source cards, lecture metadata, and attached raw source files. Return only "
        "valid JSON. Preserve missing-source caveats. Do not add claims that are not supported by "
        "the source cards, attached files, or explicit course metadata."
    )


def _lecture_substrate_prompt(*, bundle: dict[str, Any], source_cards: list[dict[str, Any]], missing_sources: list[dict[str, Any]]) -> str:
    payload = {
        "course_title": COURSE_TITLE,
        "lecture_bundle": bundle,
        "source_cards": [_compact_source_card(card) for card in source_cards],
        "missing_sources": missing_sources,
        "task": (
            "Synthesize the lecture as a learning substrate. Show how readings and slides relate, "
            "what problem organizes the lecture, which concepts and tensions matter, and what must "
            "be carried forward."
        ),
        "required_json_shape": {
            "analysis": {
                "lecture_question": "central question the lecture helps answer",
                "central_learning_problem": "one-paragraph learning problem",
                "source_roles": [{"source_id": "id", "role": "anchor | framing | supporting | application"}],
                "source_relations": [{"relation": "how sources qualify, extend, or correct one another"}],
                "core_concepts": [{"concept": "term", "why_it_matters": "reason"}],
                "core_tensions": [{"tension": "distinction or disagreement", "stakes": "why it matters"}],
                "likely_misunderstandings": ["misunderstanding to prevent"],
                "must_carry_ideas": ["idea that later outputs must preserve"],
                "missing_sources": [{"source_id": "id", "impact": "what cannot be known"}],
                "warnings": ["caveats or empty list"],
            }
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_lecture_substrate_for_lecture(
    *,
    repo_root: Path,
    subject_root: Path | None = None,
    lecture_key: str,
    lecture_bundle_dir: Path,
    source_card_dir: Path,
    lecture_substrate_dir: Path,
    source_catalog_path: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    lecture_key = canonicalize_lecture_key(lecture_key)
    bundle = _load_bundle(lecture_bundle_dir, lecture_key)
    source_cards, missing_sources = _source_cards_for_bundle(source_card_dir, bundle)
    raw_source_paths = _raw_source_paths_for_bundle(subject_root, bundle)
    response = _call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=_lecture_substrate_system_instruction(),
        user_prompt=_lecture_substrate_prompt(bundle=bundle, source_cards=source_cards, missing_sources=missing_sources),
        source_paths=raw_source_paths,
        max_output_tokens=10000,
        response_json_schema=_lecture_substrate_response_schema(),
    )
    analysis = _analysis_from_response(
        response,
        string_fields=["lecture_question", "central_learning_problem"],
        list_fields=[
            "source_roles",
            "source_relations",
            "core_concepts",
            "core_tensions",
            "likely_misunderstandings",
            "must_carry_ideas",
            "missing_sources",
            "warnings",
        ],
    )
    card_paths = [
        _source_card_path(source_card_dir, str((card.get("source") or {}).get("source_id") or ""))
        for card in source_cards
    ]
    artifact = {
        **_build_metadata(
            artifact_type="lecture_substrate",
            model=model,
            dependency_hashes=_lecture_substrate_dependency_hashes(
                bundle=bundle,
                source_card_paths=card_paths,
                raw_source_paths=raw_source_paths,
            ),
            input_source_ids=_bundle_input_source_ids(bundle),
        ),
        "lecture": {
            "lecture_key": lecture_key,
            "lecture_title": str(bundle.get("lecture_title") or lecture_key).strip(),
            "sequence_index": bundle.get("sequence_index"),
        },
        "analysis": analysis,
    }
    validate_lecture_substrate(artifact)
    write_json(_lecture_substrate_path(lecture_substrate_dir, lecture_key), artifact)
    return artifact


def build_lecture_substrates(
    *,
    repo_root: Path,
    subject_root: Path | None = None,
    lecture_keys: list[str],
    lecture_bundle_dir: Path,
    source_card_dir: Path,
    lecture_substrate_dir: Path,
    source_catalog_path: Path,
    force: bool = False,
    skip_existing: bool = True,
    dry_run: bool = False,
    continue_on_error: bool = False,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for lecture_key in lecture_keys:
        output_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
        if output_path.exists() and skip_existing and not force:
            if lecture_substrate_is_fresh(
                path=output_path,
                lecture_key=lecture_key,
                subject_root=subject_root,
                lecture_bundle_dir=lecture_bundle_dir,
                source_card_dir=source_card_dir,
                source_catalog_path=source_catalog_path,
            ):
                results.append({"lecture_key": lecture_key, "status": "skipped_existing", "output_path": str(output_path)})
                continue
            if dry_run:
                results.append({"lecture_key": lecture_key, "status": "planned_stale_rebuild", "output_path": str(output_path)})
                continue
        if dry_run:
            results.append({"lecture_key": lecture_key, "status": "planned", "output_path": str(output_path)})
            continue
        try:
            build_lecture_substrate_for_lecture(
                repo_root=repo_root,
                subject_root=subject_root,
                lecture_key=lecture_key,
                lecture_bundle_dir=lecture_bundle_dir,
                source_card_dir=source_card_dir,
                lecture_substrate_dir=lecture_substrate_dir,
                source_catalog_path=source_catalog_path,
                model=model,
                backend=backend,
                json_generator=json_generator,
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append(
                {
                    "lecture_key": lecture_key,
                    "status": "error",
                    "output_path": str(output_path),
                    "error": format_error(exc),
                }
            )
            continue
        results.append({"lecture_key": lecture_key, "status": "written", "output_path": str(output_path)})
    return {
        "selected_count": len(lecture_keys),
        "written_count": sum(1 for item in results if item["status"] == "written"),
        "skipped_count": sum(1 for item in results if item["status"].startswith("skipped")),
        "planned_count": sum(1 for item in results if item["status"].startswith("planned")),
        "error_count": count_error_results(results),
        "results": results,
    }


def _compact_lecture_substrate(substrate: dict[str, Any]) -> dict[str, Any]:
    lecture = substrate.get("lecture") if isinstance(substrate.get("lecture"), dict) else {}
    analysis = substrate.get("analysis") if isinstance(substrate.get("analysis"), dict) else {}
    return {
        "lecture": lecture,
        "analysis": {
            "lecture_question": analysis.get("lecture_question"),
            "central_learning_problem": analysis.get("central_learning_problem"),
            "source_roles": _coerce_list(analysis.get("source_roles"))[:10],
            "source_relations": _coerce_list(analysis.get("source_relations"))[:10],
            "core_concepts": _coerce_list(analysis.get("core_concepts"))[:10],
            "core_tensions": _coerce_list(analysis.get("core_tensions"))[:8],
            "must_carry_ideas": _coerce_list(analysis.get("must_carry_ideas"))[:8],
            "missing_sources": _coerce_list(analysis.get("missing_sources")),
            "warnings": _coerce_list(analysis.get("warnings")),
        },
    }


def _load_existing_lecture_substrates(lecture_substrate_dir: Path, lecture_keys: list[str]) -> list[dict[str, Any]]:
    substrates: list[dict[str, Any]] = []
    missing_keys: list[str] = []
    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
        if path.exists() and path.is_file():
            substrates.append(validate_lecture_substrate(load_json(path)))
        else:
            missing_keys.append(lecture_key)
    if missing_keys:
        raise RuntimeError(
            "missing lecture substrates for selected lectures: "
            + ", ".join(missing_keys)
        )
    return substrates


def _supporting_course_artifacts(
    *,
    glossary_path: Path,
    theory_map_path: Path,
    concept_graph_path: Path,
) -> dict[str, Any]:
    def maybe(path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        payload = load_json(path)
        return payload if isinstance(payload, dict) else None

    glossary = maybe(glossary_path)
    theory_map = maybe(theory_map_path)
    concept_graph = maybe(concept_graph_path)
    return {
        "glossary_terms": (glossary or {}).get("terms", [])[:80] if isinstance((glossary or {}).get("terms"), list) else [],
        "theories": (theory_map or {}).get("theories", [])[:60] if isinstance((theory_map or {}).get("theories"), list) else [],
        "distinctions": (concept_graph or {}).get("distinctions", [])[:80]
        if isinstance((concept_graph or {}).get("distinctions"), list)
        else [],
    }


def _course_synthesis_system_instruction() -> str:
    return (
        "You are synthesizing an entire personality psychology course from lecture substrates. "
        "This is a top-down course map used to improve later learning-material generation. Return "
        "only valid JSON. Keep weak spots and partial scope explicit."
    )


def _course_synthesis_prompt(
    *,
    lecture_substrates: list[dict[str, Any]],
    supporting_artifacts: dict[str, Any],
    partial_scope: bool,
) -> str:
    payload = {
        "course_title": COURSE_TITLE,
        "scope": "partial" if partial_scope else "full",
        "lecture_substrates": [_compact_lecture_substrate(item) for item in lecture_substrates],
        "deterministic_supporting_artifacts": supporting_artifacts,
        "task": (
            "Build a course-level synthesis with bottom-up grounding from lecture substrates, "
            "sideways relations between lectures/theories/concepts, and top-down priorities that "
            "can later revise each lecture."
        ),
        "required_json_shape": {
            "analysis": {
                "course_arc": "short but substantive course arc",
                "theory_tradition_map": [{"label": "theory/tradition", "role": "course role"}],
                "concept_map": [{"concept": "term", "role": "course role"}],
                "distinction_map": [{"distinction": "label", "stakes": "why it matters"}],
                "sideways_relations": [{"from": "lecture/concept", "to": "lecture/concept", "relation": "relation"}],
                "lecture_clusters": [{"label": "cluster", "lecture_keys": ["W##L#"], "theme": "theme"}],
                "top_down_priorities": [{"priority": "what later outputs should emphasize", "lecture_keys": ["W##L#"]}],
                "weak_spots": ["missing or weak evidence caveat"],
                "podcast_generation_guidance": ["guidance for compact NotebookLM podcast prompts"],
            }
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_course_synthesis(
    *,
    repo_root: Path,
    lecture_keys: list[str],
    lecture_substrate_dir: Path,
    output_path: Path,
    source_catalog_path: Path,
    glossary_path: Path = DEFAULT_COURSE_GLOSSARY_PATH,
    theory_map_path: Path = DEFAULT_COURSE_THEORY_MAP_PATH,
    concept_graph_path: Path = DEFAULT_CONCEPT_GRAPH_PATH,
    force: bool = False,
    dry_run: bool = False,
    partial_scope: bool = False,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    resolved_glossary_path = repo_root / glossary_path if not glossary_path.is_absolute() else glossary_path
    resolved_theory_map_path = repo_root / theory_map_path if not theory_map_path.is_absolute() else theory_map_path
    resolved_concept_graph_path = repo_root / concept_graph_path if not concept_graph_path.is_absolute() else concept_graph_path
    if output_path.exists() and not force:
        if course_synthesis_is_fresh(
            path=output_path,
            lecture_keys=lecture_keys,
            lecture_substrate_dir=lecture_substrate_dir,
            source_catalog_path=source_catalog_path,
            partial_scope=partial_scope,
            glossary_path=resolved_glossary_path,
            theory_map_path=resolved_theory_map_path,
            concept_graph_path=resolved_concept_graph_path,
        ):
            return {"status": "skipped_existing", "output_path": str(output_path)}
        if dry_run:
            return {"status": "planned_stale_rebuild", "output_path": str(output_path), "lecture_count": len(lecture_keys)}
    if dry_run:
        return {"status": "planned", "output_path": str(output_path), "lecture_count": len(lecture_keys)}
    lecture_substrates = _load_existing_lecture_substrates(lecture_substrate_dir, lecture_keys)
    if not lecture_substrates:
        raise RuntimeError("no lecture substrates available for course synthesis")
    supporting_artifacts = _supporting_course_artifacts(
        glossary_path=resolved_glossary_path,
        theory_map_path=resolved_theory_map_path,
        concept_graph_path=resolved_concept_graph_path,
    )
    response = _call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=_course_synthesis_system_instruction(),
        user_prompt=_course_synthesis_prompt(
            lecture_substrates=lecture_substrates,
            supporting_artifacts=supporting_artifacts,
            partial_scope=partial_scope,
        ),
        max_output_tokens=12000,
        response_json_schema=_course_synthesis_response_schema(),
    )
    analysis = _analysis_from_response(
        response,
        string_fields=["course_arc"],
        list_fields=[
            "theory_tradition_map",
            "concept_map",
            "distinction_map",
            "sideways_relations",
            "lecture_clusters",
            "top_down_priorities",
            "weak_spots",
            "podcast_generation_guidance",
        ],
    )
    substrate_paths = [_lecture_substrate_path(lecture_substrate_dir, key) for key in lecture_keys]
    artifact = {
        **_build_metadata(
            artifact_type="course_synthesis",
            model=model,
            dependency_hashes=_course_synthesis_dependency_hashes(
                lecture_substrate_paths=substrate_paths,
                glossary_path=resolved_glossary_path,
                theory_map_path=resolved_theory_map_path,
                concept_graph_path=resolved_concept_graph_path,
            ),
            input_source_ids=[
                source_id
                for substrate in lecture_substrates
                for source_id in substrate.get("provenance", {}).get("input_source_ids", [])
            ],
        ),
        "course": {
            "course_title": COURSE_TITLE,
            "lecture_count": len(lecture_substrates),
            "scope": "partial" if partial_scope else "full",
            "lecture_keys": lecture_keys,
        },
        "analysis": analysis,
    }
    validate_course_synthesis(artifact)
    write_json(output_path, artifact)
    return {"status": "written", "output_path": str(output_path), "lecture_count": len(lecture_substrates)}


def _downward_revision_system_instruction() -> str:
    return (
        "You are revising one lecture substrate after seeing the course-level synthesis. Return only "
        "valid JSON. The goal is top-down correction and prioritization, not adding unsupported detail."
    )


def _downward_revision_prompt(*, lecture_substrate: dict[str, Any], course_synthesis: dict[str, Any]) -> str:
    payload = {
        "course_title": COURSE_TITLE,
        "course_synthesis": course_synthesis,
        "lecture_substrate": lecture_substrate,
        "task": (
            "Revise the lecture with the whole-course map in view. Identify what matters more, what "
            "should be de-emphasized, the strongest sideways connections, and podcast priorities."
        ),
        "required_json_shape": {
            "analysis": {
                "what_matters_more": ["priority after whole-course view"],
                "de_emphasize": ["item to keep secondary"],
                "strongest_sideways_connections": [{"target": "lecture/concept/theory", "relation": "relation"}],
                "top_down_course_relevance": "why this lecture matters in the course arc",
                "revised_podcast_priorities": ["podcast priority"],
                "carry_forward": ["idea to carry into later material"],
                "warnings": ["caveats or empty list"],
            }
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_revised_lecture_substrate_for_lecture(
    *,
    lecture_key: str,
    lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    revised_lecture_substrate_dir: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    lecture_key = canonicalize_lecture_key(lecture_key)
    lecture_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
    lecture_substrate = validate_lecture_substrate(load_json(lecture_path))
    course_synthesis = validate_course_synthesis(load_json(course_synthesis_path))
    response = _call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=_downward_revision_system_instruction(),
        user_prompt=_downward_revision_prompt(
            lecture_substrate=lecture_substrate,
            course_synthesis=course_synthesis,
        ),
        max_output_tokens=8192,
        response_json_schema=_downward_revision_response_schema(),
    )
    analysis = _analysis_from_response(
        response,
        string_fields=["top_down_course_relevance"],
        list_fields=[
            "what_matters_more",
            "de_emphasize",
            "strongest_sideways_connections",
            "revised_podcast_priorities",
            "carry_forward",
            "warnings",
        ],
    )
    artifact = {
        **_build_metadata(
            artifact_type="revised_lecture_substrate",
            model=model,
            dependency_hashes=_revised_lecture_substrate_dependency_hashes(
                lecture_path=lecture_path,
                course_synthesis_path=course_synthesis_path,
            ),
            input_source_ids=lecture_substrate.get("provenance", {}).get("input_source_ids", []),
        ),
        "lecture": lecture_substrate["lecture"],
        "analysis": analysis,
    }
    validate_revised_lecture_substrate(artifact)
    write_json(_lecture_substrate_path(revised_lecture_substrate_dir, lecture_key), artifact)
    return artifact


def build_revised_lecture_substrates(
    *,
    lecture_keys: list[str],
    lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    revised_lecture_substrate_dir: Path,
    force: bool = False,
    skip_existing: bool = True,
    dry_run: bool = False,
    continue_on_error: bool = False,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for lecture_key in lecture_keys:
        output_path = _lecture_substrate_path(revised_lecture_substrate_dir, lecture_key)
        if output_path.exists() and skip_existing and not force:
            if revised_lecture_substrate_is_fresh(
                path=output_path,
                lecture_key=lecture_key,
                lecture_substrate_dir=lecture_substrate_dir,
                course_synthesis_path=course_synthesis_path,
            ):
                results.append({"lecture_key": lecture_key, "status": "skipped_existing", "output_path": str(output_path)})
                continue
            if dry_run:
                results.append({"lecture_key": lecture_key, "status": "planned_stale_rebuild", "output_path": str(output_path)})
                continue
        if dry_run:
            results.append({"lecture_key": lecture_key, "status": "planned", "output_path": str(output_path)})
            continue
        try:
            build_revised_lecture_substrate_for_lecture(
                lecture_key=lecture_key,
                lecture_substrate_dir=lecture_substrate_dir,
                course_synthesis_path=course_synthesis_path,
                revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                model=model,
                backend=backend,
                json_generator=json_generator,
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append(
                {
                    "lecture_key": lecture_key,
                    "status": "error",
                    "output_path": str(output_path),
                    "error": format_error(exc),
                }
            )
            continue
        results.append({"lecture_key": lecture_key, "status": "written", "output_path": str(output_path)})
    return {
        "selected_count": len(lecture_keys),
        "written_count": sum(1 for item in results if item["status"] == "written"),
        "skipped_count": sum(1 for item in results if item["status"].startswith("skipped")),
        "planned_count": sum(1 for item in results if item["status"].startswith("planned")),
        "error_count": count_error_results(results),
        "results": results,
    }


def _podcast_substrate_system_instruction() -> str:
    return (
        "You are preparing a compact substrate for NotebookLM podcast prompting. Return only valid "
        "JSON. The substrate must be concise, source-grounded, and useful for a bachelor's-level "
        "psychology student preparing for exam-relevant understanding."
    )


def _podcast_substrate_prompt(
    *,
    revised_lecture_substrate: dict[str, Any],
    source_cards: list[dict[str, Any]],
    course_synthesis: dict[str, Any],
    source_weighting: dict[str, Any] | None,
) -> str:
    payload = {
        "course_title": COURSE_TITLE,
        "revised_lecture_substrate": revised_lecture_substrate,
        "source_cards": [_compact_source_card(card) for card in source_cards],
        "course_synthesis_excerpt": {
            "course": course_synthesis.get("course"),
            "analysis": course_synthesis.get("analysis"),
        },
        "source_weighting": source_weighting,
        "task": (
            "Create the compact boundary artifact that the prompt system can inject. Keep it useful "
            "but not bloated. Include weekly, per-reading, per-slide, and short-podcast substrate."
        ),
        "required_json_shape": {
            "podcast": {
                "weekly": {
                    "angle": "episode angle",
                    "must_cover": ["point"],
                    "avoid": ["overcorrection or trap"],
                    "grounding": ["source-grounding note"],
                },
                "per_reading": [
                    {
                        "source_id": "id",
                        "angle": "source-specific angle",
                        "must_cover": ["point"],
                        "avoid": ["trap"],
                    }
                ],
                "per_slide": [
                    {
                        "source_id": "id",
                        "angle": "slide-specific angle",
                        "must_cover": ["point"],
                        "avoid": ["trap"],
                    }
                ],
                "short": {"angle": "compact episode angle", "must_cover": ["one or two priorities"], "avoid": ["trap"]},
                "selected_concepts": [{"concept": "term", "role": "why selected"}],
                "selected_tensions": [{"tension": "label", "stakes": "why it matters"}],
                "grounding_notes": ["source-grounding rule"],
                "source_selection": [{"source_id": "id", "priority": "anchor | major | supporting", "why": "reason"}],
            }
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _source_weighting_for_lecture(source_weighting_path: Path, lecture_key: str) -> dict[str, Any] | None:
    if not source_weighting_path.exists() or not source_weighting_path.is_file():
        return None
    payload = load_json(source_weighting_path)
    if not isinstance(payload, dict):
        return None
    for lecture in payload.get("lectures", []):
        if isinstance(lecture, dict) and canonicalize_lecture_key(str(lecture.get("lecture_key") or "")) == lecture_key:
            return lecture
    return None


def build_podcast_substrate_for_lecture(
    *,
    lecture_key: str,
    source_card_dir: Path,
    lecture_bundle_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    podcast_substrate_dir: Path,
    source_weighting_path: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    lecture_key = canonicalize_lecture_key(lecture_key)
    revised_path = _lecture_substrate_path(revised_lecture_substrate_dir, lecture_key)
    revised = validate_revised_lecture_substrate(load_json(revised_path))
    course_synthesis = validate_course_synthesis(load_json(course_synthesis_path))
    bundle = _load_bundle(lecture_bundle_dir, lecture_key)
    source_cards, _missing_sources = _source_cards_for_bundle(source_card_dir, bundle)
    source_weighting = _source_weighting_for_lecture(source_weighting_path, lecture_key)
    response = _call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=_podcast_substrate_system_instruction(),
        user_prompt=_podcast_substrate_prompt(
            revised_lecture_substrate=revised,
            source_cards=source_cards,
            course_synthesis=course_synthesis,
            source_weighting=source_weighting,
        ),
        max_output_tokens=10000,
        response_json_schema=_podcast_substrate_response_schema(),
    )
    podcast = _coerce_dict(response.get("podcast") if "podcast" in response else response)
    normalized_podcast = {
        "weekly": _coerce_dict(podcast.get("weekly")),
        "per_reading": _coerce_list(podcast.get("per_reading")),
        "per_slide": _coerce_list(podcast.get("per_slide")),
        "short": _coerce_dict(podcast.get("short")),
        "selected_concepts": _coerce_list(podcast.get("selected_concepts")),
        "selected_tensions": _coerce_list(podcast.get("selected_tensions")),
        "grounding_notes": _coerce_list(podcast.get("grounding_notes")),
        "source_selection": _coerce_list(podcast.get("source_selection")),
    }
    source_card_paths = [
        _source_card_path(source_card_dir, str((card.get("source") or {}).get("source_id") or ""))
        for card in source_cards
    ]
    artifact = {
        **_build_metadata(
            artifact_type="podcast_substrate",
            model=model,
            dependency_hashes=_podcast_substrate_dependency_hashes(
                revised_path=revised_path,
                course_synthesis_path=course_synthesis_path,
                source_card_paths=source_card_paths,
                source_weighting_path=source_weighting_path,
            ),
            input_source_ids=revised.get("provenance", {}).get("input_source_ids", []),
        ),
        "lecture": revised["lecture"],
        "podcast": normalized_podcast,
    }
    validate_podcast_substrate(artifact)
    write_json(_lecture_substrate_path(podcast_substrate_dir, lecture_key), artifact)
    return artifact


def build_podcast_substrates(
    *,
    lecture_keys: list[str],
    source_card_dir: Path,
    lecture_bundle_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    podcast_substrate_dir: Path,
    source_weighting_path: Path,
    force: bool = False,
    skip_existing: bool = True,
    dry_run: bool = False,
    continue_on_error: bool = False,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for lecture_key in lecture_keys:
        output_path = _lecture_substrate_path(podcast_substrate_dir, lecture_key)
        if output_path.exists() and skip_existing and not force:
            if podcast_substrate_is_fresh(
                path=output_path,
                lecture_key=lecture_key,
                source_card_dir=source_card_dir,
                revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                course_synthesis_path=course_synthesis_path,
                source_weighting_path=source_weighting_path,
            ):
                results.append({"lecture_key": lecture_key, "status": "skipped_existing", "output_path": str(output_path)})
                continue
            if dry_run:
                results.append({"lecture_key": lecture_key, "status": "planned_stale_rebuild", "output_path": str(output_path)})
                continue
        if dry_run:
            results.append({"lecture_key": lecture_key, "status": "planned", "output_path": str(output_path)})
            continue
        try:
            build_podcast_substrate_for_lecture(
                lecture_key=lecture_key,
                source_card_dir=source_card_dir,
                lecture_bundle_dir=lecture_bundle_dir,
                revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                course_synthesis_path=course_synthesis_path,
                podcast_substrate_dir=podcast_substrate_dir,
                source_weighting_path=source_weighting_path,
                model=model,
                backend=backend,
                json_generator=json_generator,
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append(
                {
                    "lecture_key": lecture_key,
                    "status": "error",
                    "output_path": str(output_path),
                    "error": format_error(exc),
                }
            )
            continue
        results.append({"lecture_key": lecture_key, "status": "written", "output_path": str(output_path)})
    return {
        "selected_count": len(lecture_keys),
        "written_count": sum(1 for item in results if item["status"] == "written"),
        "skipped_count": sum(1 for item in results if item["status"].startswith("skipped")),
        "planned_count": sum(1 for item in results if item["status"].startswith("planned")),
        "error_count": count_error_results(results),
        "results": results,
    }


def refresh_recursive_provenance(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    recursive_dir: Path,
) -> dict[str, Any]:
    catalog = _load_source_catalog(source_catalog_path)
    lecture_keys = _source_catalog_lecture_keys(catalog)
    source_by_id = {
        str(source.get("source_id") or "").strip(): source
        for source in catalog.get("sources", [])
        if isinstance(source, dict) and str(source.get("source_id") or "").strip()
    }
    expected_source_ids = [
        str(source.get("source_id") or "").strip()
        for source in catalog.get("sources", [])
        if isinstance(source, dict) and source.get("source_exists") and str(source.get("source_id") or "").strip()
    ]
    show_dir = source_catalog_path.parent
    policy_path = show_dir / "source_intelligence_policy.json"
    lecture_bundle_dir = show_dir / "lecture_bundles"
    source_weighting_path = show_dir / "source_weighting.json"
    glossary_path = show_dir / "course_glossary.json"
    theory_map_path = show_dir / "course_theory_map.json"
    concept_graph_path = show_dir / "course_concept_graph.json"

    source_card_dir = recursive_dir / "source_cards"
    lecture_substrate_dir = recursive_dir / "lecture_substrates"
    revised_dir = recursive_dir / "revised_lecture_substrates"
    podcast_dir = recursive_dir / "podcast_substrates"
    course_synthesis_path = recursive_dir / "course_synthesis.json"

    counts = {
        "source_cards": 0,
        "lecture_substrates": 0,
        "course_synthesis": 0,
        "revised_lecture_substrates": 0,
        "podcast_substrates": 0,
    }
    errors: list[str] = []

    for source_id in expected_source_ids:
        path = _source_card_path(source_card_dir, source_id)
        if not path.exists() or not path.is_file():
            continue
        try:
            source = source_by_id[source_id]
            artifact = validate_source_card(load_json(path))
            source_paths = source_file_paths(subject_root, source)
            artifact["provenance"]["input_source_ids"] = [source_id]
            artifact["provenance"]["dependency_hashes"] = _source_card_dependency_hashes(
                source=source,
                source_paths=source_paths,
                policy_path=policy_path,
            )
            artifact["source"] = _source_identity(source, source_paths, repo_root, subject_root)
            validate_source_card(artifact)
            write_json(path, artifact)
            counts["source_cards"] += 1
        except Exception as exc:
            errors.append(f"{display_path(path, repo_root)}: {exc}")

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_lecture_substrate(load_json(path))
            bundle = _load_bundle(lecture_bundle_dir, lecture_key)
            source_cards, _missing_sources = _source_cards_for_bundle(source_card_dir, bundle)
            raw_source_paths = _raw_source_paths_for_bundle(subject_root, bundle)
            source_card_paths = [
                _source_card_path(source_card_dir, str((card.get("source") or {}).get("source_id") or ""))
                for card in source_cards
            ]
            artifact["provenance"]["input_source_ids"] = _bundle_input_source_ids(bundle)
            artifact["provenance"]["dependency_hashes"] = _lecture_substrate_dependency_hashes(
                bundle=bundle,
                source_card_paths=source_card_paths,
                raw_source_paths=raw_source_paths,
            )
            artifact["lecture"] = {
                "lecture_key": lecture_key,
                "lecture_title": str(bundle.get("lecture_title") or lecture_key).strip(),
                "sequence_index": bundle.get("sequence_index"),
            }
            validate_lecture_substrate(artifact)
            write_json(path, artifact)
            counts["lecture_substrates"] += 1
        except Exception as exc:
            errors.append(f"{display_path(path, repo_root)}: {exc}")

    if course_synthesis_path.exists() and course_synthesis_path.is_file():
        try:
            artifact = validate_course_synthesis(load_json(course_synthesis_path))
            course = artifact.get("course") if isinstance(artifact.get("course"), dict) else {}
            synthesis_keys = [canonicalize_lecture_key(str(item or "")) for item in course.get("lecture_keys", [])]
            synthesis_keys = [key for key in synthesis_keys if key] or lecture_keys
            lecture_substrates = _load_existing_lecture_substrates(lecture_substrate_dir, synthesis_keys)
            artifact["provenance"]["input_source_ids"] = [
                source_id
                for substrate in lecture_substrates
                for source_id in _artifact_input_source_ids(substrate)
            ]
            artifact["provenance"]["dependency_hashes"] = _course_synthesis_dependency_hashes(
                lecture_substrate_paths=[_lecture_substrate_path(lecture_substrate_dir, key) for key in synthesis_keys],
                glossary_path=glossary_path,
                theory_map_path=theory_map_path,
                concept_graph_path=concept_graph_path,
            )
            artifact["course"] = {
                "course_title": str(course.get("course_title") or COURSE_TITLE),
                "lecture_count": len(synthesis_keys),
                "scope": str(course.get("scope") or "full").strip() or "full",
                "lecture_keys": synthesis_keys,
            }
            validate_course_synthesis(artifact)
            write_json(course_synthesis_path, artifact)
            counts["course_synthesis"] = 1
        except Exception as exc:
            errors.append(f"{display_path(course_synthesis_path, repo_root)}: {exc}")

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(revised_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_revised_lecture_substrate(load_json(path))
            lecture_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
            lecture_substrate = validate_lecture_substrate(load_json(lecture_path))
            artifact["provenance"]["input_source_ids"] = _artifact_input_source_ids(lecture_substrate)
            artifact["provenance"]["dependency_hashes"] = _revised_lecture_substrate_dependency_hashes(
                lecture_path=lecture_path,
                course_synthesis_path=course_synthesis_path,
            )
            artifact["lecture"] = lecture_substrate["lecture"]
            validate_revised_lecture_substrate(artifact)
            write_json(path, artifact)
            counts["revised_lecture_substrates"] += 1
        except Exception as exc:
            errors.append(f"{display_path(path, repo_root)}: {exc}")

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(podcast_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_podcast_substrate(load_json(path))
            revised_path = _lecture_substrate_path(revised_dir, lecture_key)
            revised = validate_revised_lecture_substrate(load_json(revised_path))
            bundle = _load_bundle(lecture_bundle_dir, lecture_key)
            source_cards, _missing_sources = _source_cards_for_bundle(source_card_dir, bundle)
            source_card_paths = [
                _source_card_path(source_card_dir, str((card.get("source") or {}).get("source_id") or ""))
                for card in source_cards
            ]
            artifact["provenance"]["input_source_ids"] = _artifact_input_source_ids(revised)
            artifact["provenance"]["dependency_hashes"] = _podcast_substrate_dependency_hashes(
                revised_path=revised_path,
                course_synthesis_path=course_synthesis_path,
                source_card_paths=source_card_paths,
                source_weighting_path=source_weighting_path,
            )
            artifact["lecture"] = revised["lecture"]
            validate_podcast_substrate(artifact)
            write_json(path, artifact)
            counts["podcast_substrates"] += 1
        except Exception as exc:
            errors.append(f"{display_path(path, repo_root)}: {exc}")

    return {
        "refreshed": counts,
        "error_count": len(errors),
        "errors": errors,
    }


def build_recursive_index(
    *,
    repo_root: Path,
    source_catalog_path: Path,
    recursive_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    catalog = _load_source_catalog(source_catalog_path)
    lecture_keys = _source_catalog_lecture_keys(catalog)
    source_by_id = {
        str(source.get("source_id") or "").strip(): source
        for source in catalog.get("sources", [])
        if isinstance(source, dict) and str(source.get("source_id") or "").strip()
    }
    expected_source_ids = [
        str(source.get("source_id") or "").strip()
        for source in catalog.get("sources", [])
        if isinstance(source, dict) and source.get("source_exists") and str(source.get("source_id") or "").strip()
    ]
    show_dir = source_catalog_path.parent
    policy_path = show_dir / "source_intelligence_policy.json"
    lecture_bundle_dir = show_dir / "lecture_bundles"
    source_weighting_path = show_dir / "source_weighting.json"
    glossary_path = show_dir / "course_glossary.json"
    theory_map_path = show_dir / "course_theory_map.json"
    concept_graph_path = show_dir / "course_concept_graph.json"

    source_card_dir = recursive_dir / "source_cards"
    lecture_substrate_dir = recursive_dir / "lecture_substrates"
    revised_dir = recursive_dir / "revised_lecture_substrates"
    podcast_dir = recursive_dir / "podcast_substrates"
    course_synthesis_path = recursive_dir / "course_synthesis.json"

    core_types = [
        "source_cards",
        "lecture_substrates",
        "course_synthesis",
        "revised_lecture_substrates",
    ]
    optional_types = ["podcast_substrates"]

    def valid_files(paths: list[Path], validator: Callable[[object], dict[str, Any]]) -> tuple[int, list[str]]:
        count = 0
        errors: list[str] = []
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            try:
                validator(load_json(path))
            except Exception as exc:
                errors.append(f"{display_path(path, repo_root)}: {exc}")
                continue
            count += 1
        return count, errors

    source_card_paths = [_source_card_path(source_card_dir, source_id) for source_id in expected_source_ids]
    lecture_paths = [_lecture_substrate_path(lecture_substrate_dir, key) for key in lecture_keys]
    revised_paths = [_lecture_substrate_path(revised_dir, key) for key in lecture_keys]
    podcast_paths = [_lecture_substrate_path(podcast_dir, key) for key in lecture_keys]
    source_card_count, source_card_errors = valid_files(source_card_paths, validate_source_card)
    lecture_count, lecture_errors = valid_files(lecture_paths, validate_lecture_substrate)
    revised_count, revised_errors = valid_files(revised_paths, validate_revised_lecture_substrate)
    podcast_count, podcast_errors = valid_files(podcast_paths, validate_podcast_substrate)

    error_groups = {
        "source_cards": source_card_errors,
        "lecture_substrates": lecture_errors,
        "course_synthesis": [],
        "revised_lecture_substrates": revised_errors,
        "podcast_substrates": podcast_errors,
    }
    core_stale_artifacts: list[str] = []
    optional_stale_artifacts: list[str] = []

    for source_id in expected_source_ids:
        path = _source_card_path(source_card_dir, source_id)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_source_card(load_json(path))
            source = source_by_id[source_id]
            source_paths_for_id = source_file_paths(DEFAULT_SUBJECT_ROOT, source)
            for reason in _source_card_stale_reasons(
                artifact=artifact,
                source=source,
                source_paths=source_paths_for_id,
                policy_path=policy_path,
            ):
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: {reason}")
        except Exception:
            continue

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_lecture_substrate(load_json(path))
            bundle_path = lecture_bundle_dir / f"{lecture_key}.json"
            if not bundle_path.exists() or not bundle_path.is_file():
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: lecture_bundle_missing")
                continue
            for reason in _lecture_substrate_stale_reasons(
                artifact=artifact,
                lecture_key=lecture_key,
                subject_root=DEFAULT_SUBJECT_ROOT,
                lecture_bundle_dir=lecture_bundle_dir,
                source_card_dir=source_card_dir,
            ):
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: {reason}")
        except Exception:
            continue

    course_synthesis_present = False
    course_synthesis_scope = ""
    course_synthesis_lecture_keys: list[str] = []
    if course_synthesis_path.exists() and course_synthesis_path.is_file():
        try:
            course_synthesis = validate_course_synthesis(load_json(course_synthesis_path))
            course_synthesis_present = True
            course = course_synthesis.get("course") if isinstance(course_synthesis.get("course"), dict) else {}
            course_synthesis_scope = str(course.get("scope") or "").strip()
            course_synthesis_lecture_keys = [
                canonicalize_lecture_key(str(item or ""))
                for item in course.get("lecture_keys", [])
            ]
            course_synthesis_lecture_keys = [key for key in course_synthesis_lecture_keys if key]
            partial_scope = course_synthesis_scope == "partial"
            for reason in _course_synthesis_stale_reasons(
                artifact=course_synthesis,
                lecture_keys=course_synthesis_lecture_keys or lecture_keys,
                lecture_substrate_dir=lecture_substrate_dir,
                partial_scope=partial_scope,
                glossary_path=glossary_path,
                theory_map_path=theory_map_path,
                concept_graph_path=concept_graph_path,
            ):
                core_stale_artifacts.append(f"{display_path(course_synthesis_path, repo_root)}: {reason}")
        except Exception as exc:
            error_groups["course_synthesis"].append(f"{display_path(course_synthesis_path, repo_root)}: {exc}")

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(revised_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_revised_lecture_substrate(load_json(path))
            lecture_path = _lecture_substrate_path(lecture_substrate_dir, lecture_key)
            if not lecture_path.exists() or not lecture_path.is_file():
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: lecture_substrate_missing")
                continue
            if not course_synthesis_path.exists() or not course_synthesis_path.is_file():
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: course_synthesis_missing")
                continue
            for reason in _revised_lecture_substrate_stale_reasons(
                artifact=artifact,
                lecture_key=lecture_key,
                lecture_substrate_dir=lecture_substrate_dir,
                course_synthesis_path=course_synthesis_path,
            ):
                core_stale_artifacts.append(f"{display_path(path, repo_root)}: {reason}")
        except Exception:
            continue

    for lecture_key in lecture_keys:
        path = _lecture_substrate_path(podcast_dir, lecture_key)
        if not path.exists() or not path.is_file():
            continue
        try:
            artifact = validate_podcast_substrate(load_json(path))
            revised_path = _lecture_substrate_path(revised_dir, lecture_key)
            if not revised_path.exists() or not revised_path.is_file():
                optional_stale_artifacts.append(f"{display_path(path, repo_root)}: revised_lecture_substrate_missing")
                continue
            if not course_synthesis_path.exists() or not course_synthesis_path.is_file():
                optional_stale_artifacts.append(f"{display_path(path, repo_root)}: course_synthesis_missing")
                continue
            for reason in _podcast_substrate_stale_reasons(
                artifact=artifact,
                lecture_key=lecture_key,
                source_card_dir=source_card_dir,
                revised_lecture_substrate_dir=revised_dir,
                course_synthesis_path=course_synthesis_path,
                source_weighting_path=source_weighting_path,
            ):
                optional_stale_artifacts.append(f"{display_path(path, repo_root)}: {reason}")
        except Exception:
            continue

    complete = {
        "source_cards": source_card_count == len(expected_source_ids),
        "lecture_substrates": lecture_count == len(lecture_keys),
        "course_synthesis": (
            course_synthesis_present
            and course_synthesis_scope == "full"
            and course_synthesis_lecture_keys == lecture_keys
        ),
        "revised_lecture_substrates": revised_count == len(lecture_keys),
        "podcast_substrates": podcast_count == len(lecture_keys),
    }
    errors = (
        error_groups["source_cards"]
        + error_groups["lecture_substrates"]
        + error_groups["course_synthesis"]
        + error_groups["revised_lecture_substrates"]
        + error_groups["podcast_substrates"]
    )
    payload = {
        "version": RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "build_inputs": {
            "source_catalog": display_path(source_catalog_path, repo_root),
            "recursive_dir": display_path(recursive_dir, repo_root),
        },
        "expected": {
            "source_card_count": len(expected_source_ids),
            "lecture_count": len(lecture_keys),
        },
        "coverage": {
            "source_cards": source_card_count,
            "lecture_substrates": lecture_count,
            "course_synthesis": 1 if course_synthesis_present else 0,
            "revised_lecture_substrates": revised_count,
            "podcast_substrates": podcast_count,
        },
        "course_synthesis": {
            "scope": course_synthesis_scope,
            "lecture_keys": course_synthesis_lecture_keys,
        },
        "complete": complete,
        "required": {
            "core_artifact_types": core_types,
            "optional_artifact_types": optional_types,
            "core_complete": all(complete[key] for key in core_types),
            "strict_complete": all(complete.values()),
        },
        "fresh": {
            "stale_artifact_count": len(core_stale_artifacts) + len(optional_stale_artifacts),
            "stale_artifacts": core_stale_artifacts + optional_stale_artifacts,
            "core_stale_artifact_count": len(core_stale_artifacts),
            "core_stale_artifacts": core_stale_artifacts,
            "optional_stale_artifact_count": len(optional_stale_artifacts),
            "optional_stale_artifacts": optional_stale_artifacts,
        },
        "error_groups": error_groups,
        "errors": errors,
        "known_partial_allowances": [
            "W03L2 may remain partial only because its manual lecture/reading summaries are incomplete, not because of missing sources."
        ],
    }
    payload = write_json(output_path, payload)
    return payload
