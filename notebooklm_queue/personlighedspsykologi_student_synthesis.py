"""Student-synthesis artifacts for personlighedspsykologi.

The student-synthesis layer is intentionally lower-authority than course
readings, slides, and source-intelligence artifacts. It captures exam-useful
comparison structure from older high-performing student notes, then grounds the
result against current course artifacts before learner-facing reuse.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_file_fingerprint

STUDENT_SYNTHESIS_SCHEMA_VERSION = 1
SUBJECT_SLUG = "personlighedspsykologi"
AUTHORITY_LABEL = "student_exam_synthesis"
PROMPT_VERSION = "personlighedspsykologi-student-synthesis-v1"

ORIENTATION_POINT_IDS = (
    "essence_context",
    "determination",
    "agency",
    "historicity",
)
VALIDATION_STATUSES = {
    "validated",
    "partially_validated",
    "needs_review",
    "student_only_exam_hint",
    "outdated_or_mismatched",
}
NOTE_BASIS_STATUSES = {
    "primary_student_note",
    "secondary_student_note",
    "cross_note_agreement",
    "course_artifact_only",
}
MAX_STUDENT_BASIS_CHARS = 420
MAX_TEXT_FIELD_CHARS = 900
RAW_EXTRACTION_MARKERS = (
    "+----------------",
    "| **Retning",
    "Total output lines:",
    "\f",
)


class StudentSynthesisValidationError(ValueError):
    """Raised when a student-synthesis artifact is malformed or unsafe."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repo_root: Path | None = None) -> str:
    try:
        if repo_root is not None:
            return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        pass
    return str(path)


def _run_text_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise StudentSynthesisValidationError(
            f"Required extraction tool is missing: {command[0]}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise StudentSynthesisValidationError(
            f"Extraction command failed for {command[0]}: {stderr or exc}"
        ) from exc
    return completed.stdout


def extract_note_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _run_text_command(["pdftotext", "-layout", str(path), "-"]), "pdftotext -layout"
    if suffix == ".docx":
        return _run_text_command(["pandoc", str(path), "-t", "markdown"]), "pandoc -t markdown"
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8"), "plain-text"
    raise StudentSynthesisValidationError(f"Unsupported note format: {path}")


def count_docx_embedded_media(path: Path) -> int:
    if path.suffix.lower() != ".docx":
        return 0
    try:
        with zipfile.ZipFile(path) as archive:
            return sum(1 for name in archive.namelist() if name.startswith("word/media/"))
    except zipfile.BadZipFile as exc:
        raise StudentSynthesisValidationError(f"DOCX is not a valid zip archive: {path}") from exc


def keyword_hits(text: str) -> dict[str, int]:
    lowered = text.casefold()
    terms = {
        "essence_context": ("essens", "kontekst"),
        "determination": ("determination", "determiner"),
        "agency": ("agency", "agens"),
        "historicity": ("historicitet", "fylogenese", "ontogenese", "sociogenese"),
        "trait": ("trækpsykologi", "big five", "hexaco"),
        "psychoanalysis": ("psykoanalyse", "freud", "lacan", "laplanche"),
        "phenomenology": ("fænomenolog", "phenomenolog"),
        "existential": ("eksistentiel", "eksistens"),
        "humanistic": ("humanistisk", "maslow", "rogers"),
        "critical": ("kritisk psykologi", "kritisk personalisme"),
        "social_constructionism": ("socialkonstruktionisme", "social constructionism"),
        "poststructuralism": ("poststrukturalisme", "poststructuralism", "foucault"),
        "narrative": ("narrativ", "narrative"),
    }
    return {
        key: sum(lowered.count(term.casefold()) for term in needles)
        for key, needles in terms.items()
    }


def build_source_notes_index(
    note_specs: Iterable[Mapping[str, str]],
    *,
    repo_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    for spec in note_specs:
        note_id = str(spec.get("note_id") or "").strip()
        label = str(spec.get("label") or note_id).strip()
        path = Path(str(spec.get("path") or "")).expanduser()
        if not note_id:
            raise StudentSynthesisValidationError("Source note spec is missing note_id")
        if not path.exists() or not path.is_file():
            raise StudentSynthesisValidationError(f"Source note file is missing: {path}")
        text, extraction_method = extract_note_text(path)
        media_count = count_docx_embedded_media(path)
        notes.append(
            {
                "note_id": note_id,
                "label": label,
                "path": _display_path(path, repo_root),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "format": path.suffix.lower().lstrip("."),
                "extraction_method": extraction_method,
                "extraction_status": "ok",
                "extracted_character_count": len(text),
                "extracted_line_count": len(text.splitlines()),
                "embedded_media_count": media_count,
                "embedded_media_review_status": "needs_review" if media_count else "not_applicable",
                "keyword_hits": keyword_hits(text),
            }
        )
    return {
        "version": STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "artifact_type": "student_synthesis_source_notes_index",
        "subject_slug": SUBJECT_SLUG,
        "generated_at": generated_at or utc_now_iso(),
        "authority": AUTHORITY_LABEL,
        "notes": notes,
        "stats": {
            "note_count": len(notes),
            "embedded_media_count": sum(int(note["embedded_media_count"]) for note in notes),
        },
        "warnings": [
            "DOCX embedded images are detected but not OCR-expanded; matrix rows must remain reviewable."
        ]
        if any(int(note["embedded_media_count"]) for note in notes)
        else [],
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_or_file_hash(path: Path) -> str:
    if path.suffix.lower() == ".json":
        try:
            return semantic_file_fingerprint(path)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    return sha256_file(path)


def dependency_hashes(paths: Mapping[str, Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, path in sorted(paths.items()):
        if path.exists() and path.is_file():
            hashes[key] = _semantic_or_file_hash(path)
        else:
            hashes[key] = "missing"
    return hashes


def note_signature(source_notes_index: Mapping[str, Any]) -> str:
    notes = source_notes_index.get("notes")
    if not isinstance(notes, list):
        raise StudentSynthesisValidationError("source_notes_index.notes must be a list")
    rendered = json.dumps(
        [
            {
                "note_id": note.get("note_id"),
                "sha256": note.get("sha256"),
                "extraction_method": note.get("extraction_method"),
                "embedded_media_count": note.get("embedded_media_count"),
            }
            for note in notes
            if isinstance(note, dict)
        ],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _normalize_token(value: object) -> str:
    return re.sub(r"[^a-z0-9æøå]+", "_", str(value or "").strip().casefold()).strip("_")


def _known_lecture_keys(source_catalog: Mapping[str, Any], theory_map: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for lecture in _as_list(source_catalog.get("lectures")):
        if isinstance(lecture, dict) and lecture.get("lecture_key"):
            keys.add(str(lecture["lecture_key"]).strip())
    for theory in _as_list(theory_map.get("theories")):
        if isinstance(theory, dict):
            keys.update(_as_str_list(theory.get("lecture_keys")))
    return keys


def _theory_by_id(theory_map: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(theory.get("theory_id")).strip(): theory
        for theory in _as_list(theory_map.get("theories"))
        if isinstance(theory, dict) and str(theory.get("theory_id") or "").strip()
    }


def _concept_grounding(theory_id: str, concept_graph: Mapping[str, Any]) -> dict[str, list[str]]:
    node_ids: list[str] = []
    distinction_ids: list[str] = []
    for node in _as_list(concept_graph.get("nodes")):
        if not isinstance(node, dict):
            continue
        theory_ids = _as_str_list(node.get("theory_ids"))
        if theory_id in theory_ids or str(node.get("node_id") or "") == theory_id:
            node_id = str(node.get("node_id") or "").strip()
            if node_id:
                node_ids.append(node_id)
    node_id_set = set(node_ids)
    for distinction in _as_list(concept_graph.get("distinctions")):
        if not isinstance(distinction, dict):
            continue
        term_ids = set(_as_str_list(distinction.get("term_ids")))
        if node_id_set & term_ids:
            distinction_id = str(distinction.get("distinction_id") or "").strip()
            if distinction_id:
                distinction_ids.append(distinction_id)
    return {
        "concept_node_ids": sorted(set(node_ids)),
        "distinction_ids": sorted(set(distinction_ids)),
    }


def _merge_grounding(
    theory_id: str,
    theory: Mapping[str, Any],
    concept_graph: Mapping[str, Any],
) -> dict[str, Any]:
    concept_links = _concept_grounding(theory_id, concept_graph)
    return {
        "course_theory_map_ids": [theory_id],
        "concept_node_ids": concept_links["concept_node_ids"],
        "distinction_ids": concept_links["distinction_ids"],
        "representative_source_ids": _as_str_list(theory.get("representative_source_ids")),
        "representative_evidence_origins": _as_str_list(theory.get("representative_evidence_origins")),
    }


def _derive_validation_status(row: Mapping[str, Any], grounding: Mapping[str, Any]) -> str:
    requested = str(row.get("validation_intent") or "").strip()
    if requested in {"student_only_exam_hint", "needs_review", "outdated_or_mismatched"}:
        return requested
    if grounding.get("representative_source_ids") and grounding.get("concept_node_ids"):
        return "validated"
    if grounding.get("representative_source_ids") or grounding.get("concept_node_ids"):
        return "partially_validated"
    return "needs_review"


def build_exam_theory_matrix(
    *,
    seed: Mapping[str, Any],
    source_notes_index: Mapping[str, Any],
    theory_map: Mapping[str, Any],
    concept_graph: Mapping[str, Any],
    dependency_hashes_payload: Mapping[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    theory_lookup = _theory_by_id(theory_map)
    rows: list[dict[str, Any]] = []
    for seed_row in _as_list(seed.get("rows")):
        if not isinstance(seed_row, dict):
            raise StudentSynthesisValidationError("seed.rows entries must be objects")
        theory_id = str(seed_row.get("theory_id") or "").strip()
        theory = theory_lookup.get(theory_id)
        if theory is None:
            raise StudentSynthesisValidationError(f"Seed row references unknown theory_id: {theory_id}")
        grounding = _merge_grounding(theory_id, theory, concept_graph)
        validation_status = _derive_validation_status(seed_row, grounding)
        rows.append(
            {
                "theory_id": theory_id,
                "label": str(theory.get("label") or seed_row.get("label") or theory_id),
                "aliases": _as_str_list(theory.get("aliases")) or _as_str_list(seed_row.get("aliases")),
                "lecture_keys": _as_str_list(theory.get("lecture_keys")) or _as_str_list(seed_row.get("lecture_keys")),
                "course_role": str(theory.get("course_role") or "").strip(),
                "course_summary": str(theory.get("summary") or "").strip(),
                "student_note_labels": _as_str_list(seed_row.get("student_note_labels")),
                "model_of_person": str(seed_row.get("model_of_person") or "").strip(),
                "personality_or_subjectivity_model": str(
                    seed_row.get("personality_or_subjectivity_model") or ""
                ).strip(),
                "method_evidence_style": str(seed_row.get("method_evidence_style") or "").strip(),
                "main_thinkers": _as_str_list(seed_row.get("main_thinkers")),
                "central_concepts": _as_str_list(seed_row.get("central_concepts")),
                "orientation_points": seed_row.get("orientation_points"),
                "strengths": _as_str_list(seed_row.get("strengths")),
                "limitations": _as_str_list(seed_row.get("limitations")),
                "comparison_targets": _as_list(seed_row.get("comparison_targets")),
                "likely_misunderstandings": _as_str_list(seed_row.get("likely_misunderstandings")),
                "student_synthesis_notes": str(seed_row.get("student_synthesis_notes") or "").strip(),
                "source_note_basis": _as_list(seed_row.get("source_note_basis")),
                "source_grounding": grounding,
                "validation_status": validation_status,
                "warnings": _as_str_list(seed_row.get("warnings")),
            }
        )
    payload = {
        "artifact_type": "exam_theory_matrix",
        "schema_version": STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": generated_at or utc_now_iso(),
        "authority": AUTHORITY_LABEL,
        "build": {
            "builder": "scripts/build_personlighedspsykologi_exam_theory_matrix.py",
            "model": "deterministic-curated-student-synthesis",
            "prompt_version": PROMPT_VERSION,
        },
        "provenance": {
            "input_source_ids": _as_str_list(seed.get("source_note_ids")),
            "source_notes_signature": note_signature(source_notes_index),
            "dependency_hashes": dict(dependency_hashes_payload),
        },
        "orientation_points": [
            {
                "orientation_point_id": "essence_context",
                "label": "Essens vs kontekst",
                "question": "Where does the theory locate personality or subjectivity: inside the person, in context, or in their relation?",
            },
            {
                "orientation_point_id": "determination",
                "label": "Determination",
                "question": "What does the theory treat as shaping or constraining the person?",
            },
            {
                "orientation_point_id": "agency",
                "label": "Agency",
                "question": "Where, if anywhere, is active steering or action located?",
            },
            {
                "orientation_point_id": "historicity",
                "label": "Historicitet",
                "question": "How do phylogenesis, ontogenesis, and sociogenesis matter?",
            },
        ],
        "rows": rows,
        "stats": {
            "row_count": len(rows),
            "validated_row_count": sum(1 for row in rows if row["validation_status"] == "validated"),
            "partially_validated_row_count": sum(
                1 for row in rows if row["validation_status"] == "partially_validated"
            ),
            "needs_review_row_count": sum(1 for row in rows if row["validation_status"] == "needs_review"),
            "student_only_exam_hint_row_count": sum(
                1 for row in rows if row["validation_status"] == "student_only_exam_hint"
            ),
        },
        "warnings": _as_str_list(seed.get("warnings")),
    }
    return validate_exam_theory_matrix(payload, known_theory_ids=set(theory_lookup), known_lecture_keys=None)


def _require_dict(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StudentSynthesisValidationError(f"{path} must be an object")
    return value


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise StudentSynthesisValidationError(f"{path} must be a list")
    return value


def _require_nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudentSynthesisValidationError(f"{path} must be a non-empty string")
    _reject_unsafe_text(value, path)
    return value.strip()


def _reject_unsafe_text(value: object, path: str) -> None:
    if isinstance(value, str):
        if any(marker in value for marker in RAW_EXTRACTION_MARKERS):
            raise StudentSynthesisValidationError(f"{path} appears to contain raw extracted table text")
        if len(value) > MAX_TEXT_FIELD_CHARS:
            raise StudentSynthesisValidationError(f"{path} is too long for a normalized synthesis field")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_unsafe_text(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_text(item, f"{path}[{index}]")


def validate_source_notes_index(payload: object) -> dict[str, Any]:
    artifact = _require_dict(payload, "$")
    if artifact.get("artifact_type") != "student_synthesis_source_notes_index":
        raise StudentSynthesisValidationError("$.artifact_type must be student_synthesis_source_notes_index")
    if artifact.get("version") != STUDENT_SYNTHESIS_SCHEMA_VERSION:
        raise StudentSynthesisValidationError(f"$.version must be {STUDENT_SYNTHESIS_SCHEMA_VERSION}")
    if artifact.get("subject_slug") != SUBJECT_SLUG:
        raise StudentSynthesisValidationError(f"$.subject_slug must be {SUBJECT_SLUG}")
    notes = _require_list(artifact.get("notes"), "$.notes")
    if not notes:
        raise StudentSynthesisValidationError("$.notes must not be empty")
    for index, note in enumerate(notes):
        note_obj = _require_dict(note, f"$.notes[{index}]")
        _require_nonempty_string(note_obj.get("note_id"), f"$.notes[{index}].note_id")
        _require_nonempty_string(note_obj.get("sha256"), f"$.notes[{index}].sha256")
        if note_obj.get("extraction_status") != "ok":
            raise StudentSynthesisValidationError(f"$.notes[{index}].extraction_status must be ok")
        if int(note_obj.get("extracted_character_count") or 0) <= 0:
            raise StudentSynthesisValidationError(f"$.notes[{index}].extracted_character_count must be positive")
    return artifact


def validate_exam_theory_matrix(
    payload: object,
    *,
    known_theory_ids: set[str] | None = None,
    known_lecture_keys: set[str] | None = None,
) -> dict[str, Any]:
    artifact = _require_dict(payload, "$")
    if artifact.get("artifact_type") != "exam_theory_matrix":
        raise StudentSynthesisValidationError("$.artifact_type must be exam_theory_matrix")
    if artifact.get("schema_version") != STUDENT_SYNTHESIS_SCHEMA_VERSION:
        raise StudentSynthesisValidationError(f"$.schema_version must be {STUDENT_SYNTHESIS_SCHEMA_VERSION}")
    if artifact.get("subject_slug") != SUBJECT_SLUG:
        raise StudentSynthesisValidationError(f"$.subject_slug must be {SUBJECT_SLUG}")
    _require_nonempty_string(artifact.get("generated_at"), "$.generated_at")
    _require_nonempty_string(artifact.get("authority"), "$.authority")
    build = _require_dict(artifact.get("build"), "$.build")
    _require_nonempty_string(build.get("builder"), "$.build.builder")
    _require_nonempty_string(build.get("model"), "$.build.model")
    _require_nonempty_string(build.get("prompt_version"), "$.build.prompt_version")
    provenance = _require_dict(artifact.get("provenance"), "$.provenance")
    _require_list(provenance.get("input_source_ids"), "$.provenance.input_source_ids")
    _require_nonempty_string(provenance.get("source_notes_signature"), "$.provenance.source_notes_signature")
    _require_dict(provenance.get("dependency_hashes"), "$.provenance.dependency_hashes")
    orientation_meta = _require_list(artifact.get("orientation_points"), "$.orientation_points")
    seen_orientation = {
        str(item.get("orientation_point_id") or "")
        for item in orientation_meta
        if isinstance(item, dict)
    }
    missing_orientation = set(ORIENTATION_POINT_IDS) - seen_orientation
    if missing_orientation:
        raise StudentSynthesisValidationError(
            "$.orientation_points missing ids: " + ", ".join(sorted(missing_orientation))
        )
    rows = _require_list(artifact.get("rows"), "$.rows")
    if not rows:
        raise StudentSynthesisValidationError("$.rows must not be empty")
    seen_theory_ids: set[str] = set()
    for index, row in enumerate(rows):
        row_obj = _require_dict(row, f"$.rows[{index}]")
        theory_id = _require_nonempty_string(row_obj.get("theory_id"), f"$.rows[{index}].theory_id")
        if _normalize_token(theory_id) != theory_id:
            raise StudentSynthesisValidationError(f"$.rows[{index}].theory_id must be normalized snake_case")
        if theory_id in seen_theory_ids:
            raise StudentSynthesisValidationError(f"Duplicate theory_id in rows: {theory_id}")
        seen_theory_ids.add(theory_id)
        if known_theory_ids is not None and theory_id not in known_theory_ids:
            raise StudentSynthesisValidationError(f"Unknown theory_id in rows: {theory_id}")
        _require_nonempty_string(row_obj.get("label"), f"$.rows[{index}].label")
        lecture_keys = _as_str_list(row_obj.get("lecture_keys"))
        if not lecture_keys:
            raise StudentSynthesisValidationError(f"$.rows[{index}].lecture_keys must not be empty")
        if known_lecture_keys is not None:
            unknown_keys = sorted(set(lecture_keys) - known_lecture_keys)
            if unknown_keys:
                raise StudentSynthesisValidationError(
                    f"$.rows[{index}].lecture_keys contains unknown keys: {', '.join(unknown_keys)}"
                )
        for field in (
            "course_role",
            "course_summary",
            "model_of_person",
            "personality_or_subjectivity_model",
            "method_evidence_style",
        ):
            _require_nonempty_string(row_obj.get(field), f"$.rows[{index}].{field}")
        for list_field in ("central_concepts", "strengths", "limitations", "likely_misunderstandings"):
            if not _as_str_list(row_obj.get(list_field)):
                raise StudentSynthesisValidationError(f"$.rows[{index}].{list_field} must not be empty")
        orientation = _require_dict(row_obj.get("orientation_points"), f"$.rows[{index}].orientation_points")
        missing = set(ORIENTATION_POINT_IDS) - set(orientation)
        if missing:
            raise StudentSynthesisValidationError(
                f"$.rows[{index}].orientation_points missing: {', '.join(sorted(missing))}"
            )
        for point_id in ORIENTATION_POINT_IDS:
            point = _require_dict(orientation.get(point_id), f"$.rows[{index}].orientation_points.{point_id}")
            _require_nonempty_string(
                point.get("summary"),
                f"$.rows[{index}].orientation_points.{point_id}.summary",
            )
            _require_nonempty_string(
                point.get("placement"),
                f"$.rows[{index}].orientation_points.{point_id}.placement",
            )
        basis = _require_list(row_obj.get("source_note_basis"), f"$.rows[{index}].source_note_basis")
        if not basis:
            raise StudentSynthesisValidationError(f"$.rows[{index}].source_note_basis must not be empty")
        for basis_index, basis_item in enumerate(basis):
            basis_obj = _require_dict(
                basis_item,
                f"$.rows[{index}].source_note_basis[{basis_index}]",
            )
            _require_nonempty_string(
                basis_obj.get("note_id"),
                f"$.rows[{index}].source_note_basis[{basis_index}].note_id",
            )
            status = str(basis_obj.get("basis_status") or "").strip()
            if status not in NOTE_BASIS_STATUSES:
                raise StudentSynthesisValidationError(
                    f"$.rows[{index}].source_note_basis[{basis_index}].basis_status is invalid"
                )
            summary = _require_nonempty_string(
                basis_obj.get("summary"),
                f"$.rows[{index}].source_note_basis[{basis_index}].summary",
            )
            if len(summary) > MAX_STUDENT_BASIS_CHARS:
                raise StudentSynthesisValidationError(
                    f"$.rows[{index}].source_note_basis[{basis_index}].summary is too long"
                )
        grounding = _require_dict(row_obj.get("source_grounding"), f"$.rows[{index}].source_grounding")
        status = str(row_obj.get("validation_status") or "").strip()
        if status not in VALIDATION_STATUSES:
            raise StudentSynthesisValidationError(f"$.rows[{index}].validation_status is invalid")
        if status == "validated" and not _as_str_list(grounding.get("representative_source_ids")):
            raise StudentSynthesisValidationError(
                f"$.rows[{index}] cannot be validated without representative_source_ids"
            )
        _reject_unsafe_text(row_obj, f"$.rows[{index}]")
    return artifact


def validate_seed(
    seed: object,
    *,
    known_theory_ids: set[str],
    known_lecture_keys: set[str],
) -> dict[str, Any]:
    payload = _require_dict(seed, "$")
    if payload.get("version") != STUDENT_SYNTHESIS_SCHEMA_VERSION:
        raise StudentSynthesisValidationError(f"seed.version must be {STUDENT_SYNTHESIS_SCHEMA_VERSION}")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise StudentSynthesisValidationError(f"seed.subject_slug must be {SUBJECT_SLUG}")
    rows = _require_list(payload.get("rows"), "$.rows")
    if not rows:
        raise StudentSynthesisValidationError("seed.rows must not be empty")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        row_obj = _require_dict(row, f"$.rows[{index}]")
        theory_id = _require_nonempty_string(row_obj.get("theory_id"), f"$.rows[{index}].theory_id")
        if theory_id in seen:
            raise StudentSynthesisValidationError(f"Duplicate seed theory_id: {theory_id}")
        seen.add(theory_id)
        if theory_id not in known_theory_ids:
            raise StudentSynthesisValidationError(f"Unknown seed theory_id: {theory_id}")
        for lecture_key in _as_str_list(row_obj.get("lecture_keys")):
            if lecture_key not in known_lecture_keys:
                raise StudentSynthesisValidationError(f"Unknown seed lecture_key {lecture_key} for {theory_id}")
    return payload
