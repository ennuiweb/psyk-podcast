#!/usr/bin/env python3
"""Build the personlighedspsykologi student-synthesis exam theory matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import notebooklm_queue.personlighedspsykologi_student_synthesis as synthesis_module
from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_student_synthesis import (
    SUBJECT_SLUG,
    StudentSynthesisValidationError,
    build_exam_theory_matrix,
    build_source_note_promotion_review,
    build_source_notes_index,
    dependency_hashes,
    sha256_file,
    utc_now_iso,
    validate_exam_theory_matrix,
    validate_seed,
    validate_source_note_promotion_review,
    validate_source_note_registry,
    validate_source_notes_index,
)

DEFAULT_SHOW_DIR = Path("shows/personlighedspsykologi-en")
DEFAULT_STUDENT_SYNTHESIS_DIR = DEFAULT_SHOW_DIR / "student_synthesis"
DEFAULT_SOURCE_NOTE_REGISTRY_PATH = DEFAULT_STUDENT_SYNTHESIS_DIR / "source_notes.registry.json"
DEFAULT_SEED_PATH = DEFAULT_STUDENT_SYNTHESIS_DIR / "exam_theory_matrix.seed.json"
DEFAULT_SOURCE_NOTES_INDEX_PATH = DEFAULT_STUDENT_SYNTHESIS_DIR / "source_notes_index.json"
DEFAULT_PROMOTION_REVIEW_PATH = DEFAULT_STUDENT_SYNTHESIS_DIR / "source_note_promotion_review.json"
DEFAULT_OUTPUT_PATH = DEFAULT_STUDENT_SYNTHESIS_DIR / "exam_theory_matrix.json"
DEFAULT_SOURCE_CATALOG_PATH = DEFAULT_SHOW_DIR / "source_catalog.json"
DEFAULT_THEORY_MAP_PATH = DEFAULT_SHOW_DIR / "course_theory_map.json"
DEFAULT_CONCEPT_GRAPH_PATH = DEFAULT_SHOW_DIR / "course_concept_graph.json"
DEFAULT_SOURCE_WEIGHTING_PATH = DEFAULT_SHOW_DIR / "source_weighting.json"
DEFAULT_COURSE_SYNTHESIS_PATH = DEFAULT_SHOW_DIR / "source_intelligence/course_synthesis.json"
DEFAULT_STALENESS_PATH = DEFAULT_SHOW_DIR / "source_intelligence_staleness.json"

def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _known_theory_ids(theory_map: dict[str, Any]) -> set[str]:
    return {
        str(theory.get("theory_id") or "").strip()
        for theory in theory_map.get("theories", [])
        if isinstance(theory, dict) and str(theory.get("theory_id") or "").strip()
    }


def _known_lecture_keys(source_catalog: dict[str, Any], theory_map: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for lecture in source_catalog.get("lectures", []):
        if isinstance(lecture, dict) and lecture.get("lecture_key"):
            keys.add(str(lecture["lecture_key"]).strip())
    for theory in theory_map.get("theories", []):
        if not isinstance(theory, dict):
            continue
        for lecture_key in theory.get("lecture_keys", []):
            if str(lecture_key or "").strip():
                keys.add(str(lecture_key).strip())
    return keys


def _dependency_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "builder_script": Path(__file__),
        "student_synthesis_module": Path(synthesis_module.__file__),
        "source_note_registry": args.source_note_registry_path,
        "seed": args.seed_path,
        "source_catalog": args.source_catalog_path,
        "course_theory_map": args.theory_map_path,
        "course_concept_graph": args.concept_graph_path,
        "source_weighting": args.source_weighting_path,
        "course_synthesis": args.course_synthesis_path,
    }


def _build_staleness_entry(
    *,
    output_path: Path,
    source_notes_index_path: Path,
    source_notes_index: dict[str, Any],
    promotion_review_path: Path,
    dependency_hashes_payload: dict[str, str],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "artifact_path": str(output_path.relative_to(repo_root)) if output_path.is_absolute() else str(output_path),
        "source_note_index_path": str(source_notes_index_path.relative_to(repo_root))
        if source_notes_index_path.is_absolute()
        else str(source_notes_index_path),
        "source_note_count": len(source_notes_index.get("notes", [])),
        "promotion_review_path": str(promotion_review_path.relative_to(repo_root))
        if promotion_review_path.is_absolute()
        else str(promotion_review_path),
        "dependency_hashes": dependency_hashes_payload,
    }


def _update_staleness(
    *,
    staleness_path: Path,
    output_path: Path,
    source_notes_index_path: Path,
    source_notes_index: dict[str, Any],
    promotion_review_path: Path,
    promotion_review: dict[str, Any],
    dependency_hashes_payload: dict[str, str],
    generated_at: str,
    repo_root: Path,
) -> tuple[dict[str, Any], bool]:
    if staleness_path.exists():
        payload = _load_json(staleness_path)
    else:
        payload = {
            "version": 1,
            "subject_slug": SUBJECT_SLUG,
            "generated_at": generated_at,
            "artifacts": {},
            "derivations": [],
        }
    artifacts = payload.setdefault("artifacts", {})
    artifacts["student_synthesis_source_notes_index"] = {
        "path": str(source_notes_index_path),
        "sha256": sha256_file(source_notes_index_path) if source_notes_index_path.exists() else "pending",
        "count": len(source_notes_index.get("notes", [])),
    }
    artifacts["student_synthesis_source_note_promotion_review"] = {
        "path": str(promotion_review_path),
        "sha256": sha256_file(promotion_review_path) if promotion_review_path.exists() else "pending",
        "count": len(promotion_review.get("entries", [])),
    }
    artifacts["exam_theory_matrix"] = {
        "path": str(output_path),
        "sha256": sha256_file(output_path) if output_path.exists() else "pending",
        "dependency_hashes": dependency_hashes_payload,
    }
    derivations = [
        item
        for item in payload.get("derivations", [])
        if not (isinstance(item, dict) and item.get("artifact_path") == str(output_path))
    ]
    derivations.append(
        _build_staleness_entry(
            output_path=output_path,
            source_notes_index_path=source_notes_index_path,
            source_notes_index=source_notes_index,
            promotion_review_path=promotion_review_path,
            dependency_hashes_payload=dependency_hashes_payload,
            repo_root=repo_root,
        )
    )
    payload["derivations"] = derivations
    payload["generated_at"] = generated_at
    return write_json_stably(staleness_path, payload)


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    generated_at = utc_now_iso()

    source_catalog = _load_json(args.source_catalog_path)
    theory_map = _load_json(args.theory_map_path)
    concept_graph = _load_json(args.concept_graph_path)
    known_theories = _known_theory_ids(theory_map)
    known_lectures = _known_lecture_keys(source_catalog, theory_map)

    if args.validate_only:
        matrix = _load_json(args.output_path)
        return validate_exam_theory_matrix(
            matrix,
            known_theory_ids=known_theories,
            known_lecture_keys=known_lectures,
        )

    registry = validate_source_note_registry(_load_json(args.source_note_registry_path))
    source_notes_index = build_source_notes_index(
        registry["notes"],
        repo_root=repo_root,
        generated_at=generated_at,
    )
    validate_source_notes_index(source_notes_index)
    promotion_review = build_source_note_promotion_review(
        registry=registry,
        source_notes_index=source_notes_index,
        generated_at=generated_at,
    )
    validate_source_note_promotion_review(promotion_review)

    if args.extract_only:
        if not args.dry_run:
            write_json_stably(args.source_notes_index_path, source_notes_index)
            write_json_stably(args.promotion_review_path, promotion_review)
        return source_notes_index

    seed = validate_seed(
        _load_json(args.seed_path),
        known_theory_ids=known_theories,
        known_lecture_keys=known_lectures,
    )
    hashes = dependency_hashes(_dependency_paths(args))
    hashes["source_notes_index"] = sha256_file(args.source_notes_index_path) if args.source_notes_index_path.exists() else "pending"
    hashes["source_note_promotion_review"] = (
        sha256_file(args.promotion_review_path) if args.promotion_review_path.exists() else "pending"
    )

    matrix = build_exam_theory_matrix(
        seed=seed,
        source_notes_index=source_notes_index,
        theory_map=theory_map,
        concept_graph=concept_graph,
        dependency_hashes_payload=hashes,
        generated_at=generated_at,
    )
    validate_exam_theory_matrix(
        matrix,
        known_theory_ids=known_theories,
        known_lecture_keys=known_lectures,
    )

    if not args.dry_run:
        source_notes_index, _ = write_json_stably(args.source_notes_index_path, source_notes_index)
        promotion_review, _ = write_json_stably(args.promotion_review_path, promotion_review)
        matrix, _ = write_json_stably(args.output_path, matrix)
        hashes = dependency_hashes(_dependency_paths(args))
        hashes["source_notes_index"] = sha256_file(args.source_notes_index_path)
        hashes["source_note_promotion_review"] = sha256_file(args.promotion_review_path)
        matrix["provenance"]["dependency_hashes"] = hashes
        matrix, _ = write_json_stably(args.output_path, matrix)
        _update_staleness(
            staleness_path=args.staleness_path,
            output_path=args.output_path,
            source_notes_index_path=args.source_notes_index_path,
            source_notes_index=source_notes_index,
            promotion_review_path=args.promotion_review_path,
            promotion_review=promotion_review,
            dependency_hashes_payload=hashes,
            generated_at=generated_at,
            repo_root=repo_root,
        )
    return matrix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--source-note-registry-path", type=Path, default=DEFAULT_SOURCE_NOTE_REGISTRY_PATH)
    parser.add_argument("--seed-path", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--source-notes-index-path", type=Path, default=DEFAULT_SOURCE_NOTES_INDEX_PATH)
    parser.add_argument("--promotion-review-path", type=Path, default=DEFAULT_PROMOTION_REVIEW_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--source-catalog-path", type=Path, default=DEFAULT_SOURCE_CATALOG_PATH)
    parser.add_argument("--theory-map-path", type=Path, default=DEFAULT_THEORY_MAP_PATH)
    parser.add_argument("--concept-graph-path", type=Path, default=DEFAULT_CONCEPT_GRAPH_PATH)
    parser.add_argument("--source-weighting-path", type=Path, default=DEFAULT_SOURCE_WEIGHTING_PATH)
    parser.add_argument("--course-synthesis-path", type=Path, default=DEFAULT_COURSE_SYNTHESIS_PATH)
    parser.add_argument("--staleness-path", type=Path, default=DEFAULT_STALENESS_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    parser.add_argument("--extract-only", action="store_true", help="Only build the source notes index.")
    parser.add_argument("--validate-only", action="store_true", help="Only validate the existing matrix.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build(args)
    except StudentSynthesisValidationError as exc:
        raise SystemExit(f"student synthesis build failed: {exc}") from exc
    if args.validate_only:
        print(f"validated {args.output_path}")
    elif args.extract_only:
        print(f"indexed {payload['stats']['note_count']} student notes")
    else:
        print(
            "built exam theory matrix "
            f"(rows={payload['stats']['row_count']}, validated={payload['stats']['validated_row_count']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
