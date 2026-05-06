"""Problem-driven printable scaffold generation for Personlighedspsykologi."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue import personlighedspsykologi_scaffolding as canonical
from notebooklm_queue.gemini_preprocessing import (
    DEFAULT_GEMINI_PREPROCESSING_MODEL,
    GeminiPreprocessingBackend,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

SUBJECT_SLUG = recursive.SUBJECT_SLUG
DEFAULT_SOURCE_CATALOG = recursive.DEFAULT_SOURCE_CATALOG
DEFAULT_SOURCE_CARD_DIR = recursive.DEFAULT_SOURCE_CARD_DIR
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = recursive.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR
DEFAULT_COURSE_SYNTHESIS_PATH = recursive.DEFAULT_COURSE_SYNTHESIS_PATH
DEFAULT_SUBJECT_ROOT = recursive.DEFAULT_SUBJECT_ROOT
DEFAULT_EVALUATION_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review")
PROMPT_VERSION = "personlighedspsykologi-reading-scaffold-problem-driven-v1"
VARIANT_KEY = "problem_driven_v1"

JsonGenerator = canonical.JsonGenerator
ScaffoldingError = canonical.ScaffoldingError


def scaffold_system_instruction() -> str:
    return "\n".join(
        [
            "You generate printable Danish reading scaffolds for Personlighedspsykologi.",
            "Return only valid JSON that matches the output_contract exactly.",
            "Use the attached source file as authority. Use supplied source-card and course context only to prioritize what matters.",
            "The student has ADD and engages best when the material feels like a problem to solve, a question to answer, or something specific to find.",
            "Design the printout around reward loops: fast entry, visible progress, and small closure events every few minutes.",
            "Keep the schema-v3 section boundaries, but change their pedagogical role.",
            "reading_guide is a mission brief: define the main problem, the win condition, the first thing to find, and what to ignore on a first pass.",
            "abridged_reader is a guided solve path: each section should revolve around one local tension or question, then resolve it clearly.",
            "active_reading is an evidence hunt: prefer narrow decisions, proof tasks, source hunts, and trap detection over broad summary questions.",
            "consolidation_sheet is a model builder: help the learner reconstruct the mechanism, contrast, or causal chain with low working-memory load.",
            "exam_bridge is a boss fight: end with one meaningful challenge that proves the learner can use the model.",
            "Make every task operational: it should tell the student what to do, where to look, and when to stop.",
            "Use action language that signals closure, such as find, decide, prove, catch, defend, or settle.",
            "Do not reveal answers in active-reading checks or consolidation tasks.",
            "Never put the answer inside parentheses in answer_shape, locations, done_signal, or stop_signal.",
            "answer_shape must describe only the answer format, e.g. '1 ord', '2 ord', 'et navn', or 'en kort sætning'. Do not add semantic hints.",
            "A done_signal should say when to stop, for example 'når du har skrevet gruppen', not what the group is.",
            "Do not make broad essay prompts, vague blanks, or questions that can be answered without reading the source.",
            "Respect copyright: use only short quote anchors or short phrase targets, never long reproduced passages.",
            "Quote anchors and quote targets must be max 12 words and max 140 characters.",
            "Abridged-reader prose should be 80-90% rewritten explanation and 10-20% short original anchors/page references.",
            "Prefer concrete Danish wording and avoid generic study-skills language.",
            "Use a serious, practical university-student tone. Avoid hype, motivational language, and childish metaphors.",
        ]
    )


def scaffold_user_prompt(
    *,
    source: dict[str, Any],
    source_card: dict[str, Any],
    lecture_context: dict[str, Any] | None,
    course_context: dict[str, Any] | None,
) -> str:
    payload = {
        "design_variant": {
            "name": VARIANT_KEY,
            "reward_loop": ["entry hook", "micro-reward loops", "resolution payoff"],
            "cognitive_sequence": ["search", "model", "challenge"],
            "preferred_verbs": ["find", "decide", "prove", "catch", "defend", "settle"],
            "avoid_task_shapes": [
                "broad discussion prompts",
                "multi-page summary-from-memory prompts",
                "generic motivational study language",
            ],
            "section_roles": {
                "reading_guide": "mission_brief",
                "abridged_reader": "guided_solve_path",
                "active_reading": "evidence_hunt",
                "consolidation_sheet": "model_builder",
                "exam_bridge": "boss_fight",
            },
        },
        "source_metadata": source,
        "source_card": canonical._compact_source_card(source_card),
        "lecture_context": lecture_context,
        "course_context": course_context,
        "output_contract": canonical.scaffold_prompt_contract(),
        "required_outputs": {
            "reading_guide": [
                "Frame the reading as one concrete mission or dispute to settle.",
                "Explain the win condition and where the learner should look first.",
                "Keep the reading route chronological with short stop signals.",
                "Use short quote targets or search phrases the learner can hunt for.",
                "Tell the learner what not to spend energy on during the first pass.",
            ],
            "abridged_reader": [
                "Treat each section as a local solve step, not just a passive explanation.",
                "Open each section on a narrow question, tension, distinction, or decision.",
                "Resolve the local problem clearly before moving on.",
                "Keep the original source contact tiny and targeted through source touchpoints.",
                "Use mini checks as closure events, not broad comprehension essays.",
            ],
            "active_reading": [
                "Favor detective-work tasks: source hunts, proof tasks, narrow choices, and trap detection.",
                "Prefer prompts where the learner must find one thing, choose between two options, or prove a claim from the text.",
                "Avoid broad summary questions and whole-text reflection prompts.",
                "Keep every task short enough to feel finishable.",
            ],
            "consolidation_sheet": [
                "Make the learner reconstruct the model, mechanism, or contrast with low working-memory load.",
                "Use fill-ins and diagram tasks that help the theory lock into place.",
                "Do not turn this section into generic recall trivia.",
            ],
            "exam_bridge": [
                "End with one meaningful final challenge that feels like a boss fight.",
                "Use the text for concrete course and exam transfer, not generic exam tips.",
                "The mini exam prompt should require use of the model, not just repetition of terms.",
            ],
        },
    }
    return (
        "Generate problem-driven printable scaffolding outputs for the attached source file.\n"
        "Use Danish for student-facing text.\n"
        "Here is the source/context payload:\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def build_scaffold_for_source(
    *,
    repo_root: Path,
    subject_root: Path,
    source: dict[str, Any],
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise ScaffoldingError("source is missing source_id")
    source_paths = recursive.source_file_paths(subject_root, source)
    if not source_paths:
        raise ScaffoldingError(f"source has no subject_relative_path: {source_id}")
    missing_paths = [path for path in source_paths if not path.exists() or not path.is_file()]
    if missing_paths:
        raise ScaffoldingError(f"source file not found: {missing_paths[0]}")
    card_path = canonical.source_card_path(source_card_dir, source_id)
    if not card_path.exists():
        raise ScaffoldingError(f"source card not found: {card_path}")
    out_dir = canonical.output_dir_for_source(output_root, source)
    json_path = out_dir / "reading-scaffolds.json"
    if rerender_existing and not force and not json_path.exists():
        raise ScaffoldingError(f"existing scaffold JSON not found for rerender: {json_path}")
    if json_path.exists() and not force:
        if rerender_existing:
            artifact = canonical.read_json(json_path)
            if canonical._artifact_schema_version(artifact) >= canonical.SCHEMA_VERSION:
                artifact["schema_version"] = canonical.SCHEMA_VERSION
                artifact["scaffolds"] = canonical.validate_scaffold_payload(
                    canonical.normalize_scaffold_payload(artifact.get("scaffolds", {}))
                )
            else:
                artifact["schema_version"] = canonical.LEGACY_SCHEMA_VERSION
                artifact["scaffolds"] = canonical.validate_v2_scaffold_payload(
                    canonical.normalize_v2_scaffold_payload(artifact.get("scaffolds", {}))
                )
            canonical.write_json(json_path, artifact)
            rendered = canonical.render_scaffold_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
            return {
                "source_id": source_id,
                "status": "rerendered_existing",
                "output_dir": str(out_dir),
                "json_path": str(json_path),
                "markdown_paths": rendered["markdown_paths"],
                "pdf_paths": rendered["pdf_paths"],
            }
        return {
            "source_id": source_id,
            "status": "skipped_existing",
            "output_dir": str(out_dir),
            "json_path": str(json_path),
            "pdf_paths": canonical._existing_pdf_paths(out_dir),
        }

    source_card = canonical.read_json(card_path)
    lecture_key = str(source.get("lecture_key") or source_card.get("source", {}).get("lecture_key") or "").strip()
    response = canonical.call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=scaffold_system_instruction(),
        user_prompt=scaffold_user_prompt(
            source=source,
            source_card=source_card,
            lecture_context=canonical._compact_lecture_context(revised_lecture_substrate_dir, lecture_key),
            course_context=canonical._compact_course_context(course_synthesis_path),
        ),
        source_paths=source_paths,
        max_output_tokens=32768,
        response_json_schema=None,
    )
    scaffolds = canonical.validate_scaffold_payload(canonical.normalize_scaffold_payload(response))
    artifact = {
        "schema_version": canonical.SCHEMA_VERSION,
        "artifact_type": "reading_scaffolds",
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "generator": {
            "provider": "gemini",
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "generation_config": canonical.scaffold_generation_config_metadata(),
        },
        "variant": {
            "mode": "problem_driven",
            "variant_key": VARIANT_KEY,
            "design_doc": "shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md",
            "evaluation_workspace": "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/",
        },
        "provenance": {
            "source_file": recursive.sha256_file(source_paths[0])
            if len(source_paths) == 1
            else recursive.signature_for_files(source_paths),
            "source_files_signature": recursive.signature_for_files(source_paths),
            "source_card": recursive.sha256_file(card_path),
            "revised_lecture_substrate": canonical._sha256_if_exists(revised_lecture_substrate_dir / f"{lecture_key}.json"),
            "course_synthesis": canonical._sha256_if_exists(course_synthesis_path),
        },
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": str(source.get("title") or ""),
            "source_family": str(source.get("source_family") or ""),
            "evidence_origin": str(source.get("evidence_origin") or ""),
            "source_path": str(source_paths[0].resolve()),
            "source_paths": [str(path.resolve()) for path in source_paths],
            "repo_display_path": recursive.display_path(source_paths[0], repo_root),
            "repo_display_paths": [recursive.display_path(path, repo_root) for path in source_paths],
        },
        "scaffolds": scaffolds,
    }
    canonical.write_json(json_path, artifact)
    rendered = canonical.render_scaffold_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
    return {
        "source_id": source_id,
        "status": "written",
        "output_dir": str(out_dir),
        "json_path": str(json_path),
        "markdown_paths": rendered["markdown_paths"],
        "pdf_paths": rendered["pdf_paths"],
    }


def build_scaffolds(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
    dry_run: bool = False,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    sources = canonical.select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=source_families,
    )
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if dry_run:
        return {
            "status": "planned",
            "variant": VARIANT_KEY,
            "source_count": len(sources),
            "sources": [
                {
                    "source_id": str(source.get("source_id") or ""),
                    "lecture_key": str(source.get("lecture_key") or ""),
                    "title": str(source.get("title") or ""),
                    "output_dir": str(canonical.output_dir_for_source(output_root, source)),
                }
                for source in sources
            ],
        }
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        try:
            results.append(
                build_scaffold_for_source(
                    repo_root=repo_root,
                    subject_root=subject_root,
                    source=source,
                    source_card_dir=source_card_dir,
                    revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                    course_synthesis_path=course_synthesis_path,
                    output_root=output_root,
                    model=model,
                    backend=backend,
                    json_generator=json_generator,
                    render_pdf=render_pdf,
                    force=force,
                    rerender_existing=rerender_existing,
                )
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "error": recursive.format_error(exc)})
            if not continue_on_error:
                break
    return {
        "status": "error" if errors else "ok",
        "variant": VARIANT_KEY,
        "source_count": len(sources),
        "written_count": sum(1 for item in results if item.get("status") == "written"),
        "rerendered_count": sum(1 for item in results if item.get("status") == "rerendered_existing"),
        "skipped_count": sum(1 for item in results if item.get("status") == "skipped_existing"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


def parse_source_families(values: list[str], *, all_families: bool = False) -> set[str] | None:
    return canonical.parse_source_families(values, all_families=all_families)


def select_sources(
    *,
    source_catalog_path: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
) -> list[dict[str, Any]]:
    return canonical.select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=source_families,
    )

