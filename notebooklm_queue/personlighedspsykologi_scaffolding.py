"""Printable reading scaffold generation for Personlighedspsykologi."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue.gemini_preprocessing import (
    DEFAULT_GEMINI_PREPROCESSING_MODEL,
    GeminiPreprocessingBackend,
    generate_json,
    generation_config_metadata,
    make_gemini_backend,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

SUBJECT_SLUG = recursive.SUBJECT_SLUG
DEFAULT_SOURCE_CATALOG = recursive.DEFAULT_SOURCE_CATALOG
DEFAULT_SOURCE_CARD_DIR = recursive.DEFAULT_SOURCE_CARD_DIR
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = recursive.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR
DEFAULT_COURSE_SYNTHESIS_PATH = recursive.DEFAULT_COURSE_SYNTHESIS_PATH
DEFAULT_SUBJECT_ROOT = recursive.DEFAULT_SUBJECT_ROOT
DEFAULT_OUTPUT_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/output")
PROMPT_VERSION = "personlighedspsykologi-reading-scaffold-v1"
SCHEMA_VERSION = 1

JsonGenerator = Callable[..., dict[str, Any]]


class ScaffoldingError(RuntimeError):
    """Raised when a printable scaffold cannot be generated or rendered."""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def source_card_path(source_card_dir: Path, source_id: str) -> Path:
    return source_card_dir / f"{source_id}.json"


def output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    lecture_key = str(source.get("lecture_key") or "UNKNOWN").strip().upper() or "UNKNOWN"
    source_id = str(source.get("source_id") or "source").strip()
    return output_root / lecture_key / "scaffolding" / source_id


def select_sources(
    *,
    source_catalog_path: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
) -> list[dict[str, Any]]:
    catalog = read_json(source_catalog_path)
    if not isinstance(catalog, dict):
        raise ScaffoldingError(f"invalid source catalog: {source_catalog_path}")
    normalized_lectures = set(recursive.normalize_lecture_keys(",".join(lecture_keys or [])))
    normalized_source_ids = {item.strip() for item in source_ids or [] if item.strip()}
    selected: list[dict[str, Any]] = []
    for source in catalog.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "").strip()
        source_family = str(source.get("source_family") or "").strip()
        lecture_values = set(recursive.normalize_lecture_keys(str(source.get("lecture_key") or "")))
        for value in source.get("lecture_keys", []) or []:
            lecture_values.update(recursive.normalize_lecture_keys(str(value or "")))
        if normalized_source_ids and source_id not in normalized_source_ids:
            continue
        if normalized_lectures and not lecture_values.intersection(normalized_lectures):
            continue
        if source_families is not None and source_family not in source_families:
            continue
        if not source.get("source_exists", False):
            continue
        selected.append(source)
    return sorted(
        selected,
        key=lambda item: (
            str(item.get("lecture_key") or ""),
            int(item.get("sequence_index") or 0),
            str(item.get("source_id") or ""),
        ),
    )


def _compact_source_card(source_card: dict[str, Any]) -> dict[str, Any]:
    analysis = source_card.get("analysis") if isinstance(source_card.get("analysis"), dict) else {}
    return {
        "source": source_card.get("source", {}),
        "analysis": {
            "theory_role": analysis.get("theory_role", ""),
            "source_role": analysis.get("source_role", ""),
            "relation_to_lecture": analysis.get("relation_to_lecture", ""),
            "central_claims": analysis.get("central_claims", [])[:6],
            "key_concepts": analysis.get("key_concepts", [])[:8],
            "distinctions": analysis.get("distinctions", [])[:6],
            "likely_misunderstandings": analysis.get("likely_misunderstandings", [])[:5],
            "quote_targets": analysis.get("quote_targets", [])[:4],
            "grounding_notes": analysis.get("grounding_notes", [])[:4],
        },
    }


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _compact_lecture_context(revised_substrate_dir: Path, lecture_key: str) -> dict[str, Any] | None:
    payload = _load_optional_json(revised_substrate_dir / f"{lecture_key}.json")
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "lecture_key": lecture_key,
        "what_matters_more": analysis.get("what_matters_more", [])[:5],
        "de_emphasize": analysis.get("de_emphasize", [])[:4],
        "strongest_sideways_connections": analysis.get("strongest_sideways_connections", [])[:5],
        "top_down_course_relevance": analysis.get("top_down_course_relevance", ""),
        "carry_forward": analysis.get("carry_forward", [])[:5],
    }


def _compact_course_context(course_synthesis_path: Path) -> dict[str, Any] | None:
    payload = _load_optional_json(course_synthesis_path)
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "scope": payload.get("scope", {}),
        "course_arc": analysis.get("course_arc", ""),
        "top_down_priorities": analysis.get("top_down_priorities", [])[:8],
        "sideways_relations": analysis.get("sideways_relations", [])[:8],
        "weak_spots": analysis.get("weak_spots", [])[:5],
    }


def _string_schema() -> dict[str, str]:
    return {"type": "string"}


def _string_list_schema(*, min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": _string_schema()}
    if min_items:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def _object_list_schema(
    *,
    properties: dict[str, Any],
    required: list[str],
    min_items: int = 0,
    max_items: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": {"type": "object", "properties": properties, "required": required},
    }
    if min_items:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def scaffold_response_schema() -> dict[str, Any]:
    quote_target = {
        "target": _string_schema(),
        "why": _string_schema(),
    }
    numbered_question = {
        "number": {"type": "integer"},
        "question": _string_schema(),
    }
    cloze_sentence = {
        "number": {"type": "integer"},
        "sentence": _string_schema(),
    }
    diagram_task = {
        "number": {"type": "integer"},
        "task": _string_schema(),
        "blank_space_hint": _string_schema(),
    }
    return {
        "type": "object",
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "language": _string_schema(),
                    "source_id": _string_schema(),
                    "lecture_key": _string_schema(),
                    "source_title": _string_schema(),
                },
                "required": ["language", "source_id", "lecture_key", "source_title"],
            },
            "abridged_guide": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "structure_and_main_arguments": _string_list_schema(min_items=3, max_items=7),
                    "key_quote_targets": _object_list_schema(
                        properties=quote_target,
                        required=["target", "why"],
                        min_items=3,
                        max_items=4,
                    ),
                },
                "required": [
                    "title",
                    "overview",
                    "structure_and_main_arguments",
                    "key_quote_targets",
                ],
            },
            "unit_test_suite": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "questions": _object_list_schema(
                        properties=numbered_question,
                        required=["number", "question"],
                        min_items=15,
                        max_items=20,
                    ),
                },
                "required": ["title", "instructions", "questions"],
            },
            "cloze_scaffold": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "fill_in_sentences": _object_list_schema(
                        properties=cloze_sentence,
                        required=["number", "sentence"],
                        min_items=5,
                        max_items=8,
                    ),
                    "diagram_tasks": _object_list_schema(
                        properties=diagram_task,
                        required=["number", "task", "blank_space_hint"],
                        min_items=1,
                        max_items=3,
                    ),
                },
                "required": ["title", "overview", "fill_in_sentences", "diagram_tasks"],
            },
        },
        "required": ["metadata", "abridged_guide", "unit_test_suite", "cloze_scaffold"],
    }


def scaffold_system_instruction() -> str:
    return "\n".join(
        [
            "You generate printable Danish reading scaffolds for Personlighedspsykologi.",
            "Return only valid JSON that matches the requested schema.",
            "Use the attached source file as authority. Use supplied source-card and course context only to prioritize what matters.",
            "The student has ADD and needs offline, short, dopamine-friendly tasks while reading.",
            "Do not reveal answers in the unit-test questions or cloze/diagram tasks.",
            "Respect copyright: use only short quote targets or short phrases, never long reproduced passages.",
            "Prefer concrete Danish wording and avoid generic study-skills language.",
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
        "source_metadata": source,
        "source_card": _compact_source_card(source_card),
        "lecture_context": lecture_context,
        "course_context": course_context,
        "required_outputs": {
            "abridged_guide": [
                "A one-page preparatory overview in Danish.",
                "Explain the text's structure and main arguments before detail.",
                "Include exactly 3-4 short quote targets or short phrases the student should look for.",
            ],
            "unit_test_suite": [
                "15-20 highly specific short-answer questions.",
                "Questions must follow the exact chronological order of the source.",
                "Do not include answers.",
                "Each question should feel like finding a hidden object in the text.",
            ],
            "cloze_scaffold": [
                "Three-sentence overview of what the text is about.",
                "5-8 fill-in-the-blank sentences where the key term/result/connection is removed.",
                "1-3 blank diagram tasks; describe what to draw but do not draw it.",
                "Leave all answer fields blank and do not explain answers.",
            ],
        },
    }
    return (
        "Generate printable scaffolding outputs for the attached source file.\n"
        "Use Danish for student-facing text.\n"
        "Here is the source/context payload:\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ScaffoldingError("scaffold payload must be a JSON object")
    for key in ("metadata", "abridged_guide", "unit_test_suite", "cloze_scaffold"):
        if not isinstance(payload.get(key), dict):
            raise ScaffoldingError(f"scaffold payload missing object: {key}")
    guide = payload["abridged_guide"]
    tests = payload["unit_test_suite"]
    cloze = payload["cloze_scaffold"]
    quote_targets = _coerce_list(guide.get("key_quote_targets"))
    questions = _coerce_list(tests.get("questions"))
    fill_ins = _coerce_list(cloze.get("fill_in_sentences"))
    diagrams = _coerce_list(cloze.get("diagram_tasks"))
    overview = _coerce_list(cloze.get("overview"))
    if not 3 <= len(quote_targets) <= 4:
        raise ScaffoldingError("abridged guide must include 3-4 quote targets")
    if not 15 <= len(questions) <= 20:
        raise ScaffoldingError("unit-test suite must include 15-20 questions")
    if len(overview) != 3:
        raise ScaffoldingError("cloze scaffold must include a three-sentence overview")
    if not 5 <= len(fill_ins) <= 8:
        raise ScaffoldingError("cloze scaffold must include 5-8 fill-in sentences")
    if not 1 <= len(diagrams) <= 3:
        raise ScaffoldingError("cloze scaffold must include 1-3 diagram tasks")
    for item in fill_ins:
        sentence = str(item.get("sentence") if isinstance(item, dict) else item)
        if "____" not in sentence and "___" not in sentence:
            raise ScaffoldingError("each cloze sentence must contain a blank marker")
    return payload


def call_json_generator(
    *,
    backend: GeminiPreprocessingBackend | None,
    json_generator: JsonGenerator | None,
    model: str,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path],
    max_output_tokens: int,
    response_json_schema: dict[str, Any],
) -> dict[str, Any]:
    if json_generator is not None:
        return json_generator(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            source_paths=source_paths,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
        )
    active_backend = backend or make_gemini_backend(model=model)
    return generate_json(
        backend=active_backend,
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        source_paths=source_paths,
        max_output_tokens=max_output_tokens,
        response_json_schema=response_json_schema,
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
) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise ScaffoldingError("source is missing source_id")
    source_path = recursive.source_file_path(subject_root, source)
    if not source_path.exists() or not source_path.is_file():
        raise ScaffoldingError(f"source file not found: {source_path}")
    card_path = source_card_path(source_card_dir, source_id)
    if not card_path.exists():
        raise ScaffoldingError(f"source card not found: {card_path}")
    out_dir = output_dir_for_source(output_root, source)
    json_path = out_dir / "reading-scaffolds.json"
    if json_path.exists() and not force:
        artifact = read_json(json_path)
        return {
            "source_id": source_id,
            "status": "skipped_existing",
            "output_dir": str(out_dir),
            "json_path": str(json_path),
            "pdf_paths": _existing_pdf_paths(out_dir),
            "artifact": artifact,
        }

    source_card = read_json(card_path)
    lecture_key = str(source.get("lecture_key") or source_card.get("source", {}).get("lecture_key") or "").strip()
    response = call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=scaffold_system_instruction(),
        user_prompt=scaffold_user_prompt(
            source=source,
            source_card=source_card,
            lecture_context=_compact_lecture_context(revised_lecture_substrate_dir, lecture_key),
            course_context=_compact_course_context(course_synthesis_path),
        ),
        source_paths=[source_path],
        max_output_tokens=12288,
        response_json_schema=scaffold_response_schema(),
    )
    scaffolds = validate_scaffold_payload(response)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "reading_scaffolds",
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "generator": {
            "provider": "gemini",
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "generation_config": generation_config_metadata(),
        },
        "provenance": {
            "source_file": recursive.sha256_file(source_path),
            "source_card": recursive.sha256_file(card_path),
            "revised_lecture_substrate": _sha256_if_exists(revised_lecture_substrate_dir / f"{lecture_key}.json"),
            "course_synthesis": _sha256_if_exists(course_synthesis_path),
        },
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": str(source.get("title") or ""),
            "source_family": str(source.get("source_family") or ""),
            "evidence_origin": str(source.get("evidence_origin") or ""),
            "source_path": str(source_path.resolve()),
            "repo_display_path": recursive.display_path(source_path, repo_root),
        },
        "scaffolds": scaffolds,
    }
    write_json(json_path, artifact)
    rendered = render_scaffold_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
    return {
        "source_id": source_id,
        "status": "written",
        "output_dir": str(out_dir),
        "json_path": str(json_path),
        "markdown_paths": rendered["markdown_paths"],
        "pdf_paths": rendered["pdf_paths"],
    }


def _sha256_if_exists(path: Path) -> str:
    return recursive.sha256_file(path) if path.exists() and path.is_file() else ""


def _existing_pdf_paths(out_dir: Path) -> list[str]:
    return [str(path) for path in sorted(out_dir.glob("*.pdf"))]


def render_scaffold_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    scaffolds = artifact.get("scaffolds") if isinstance(artifact.get("scaffolds"), dict) else {}
    markdown_items = [
        ("01-abridged-guide", render_abridged_markdown(artifact, scaffolds.get("abridged_guide", {}))),
        ("02-unit-test-suite", render_unit_test_markdown(artifact, scaffolds.get("unit_test_suite", {}))),
        ("03-cloze-scaffold", render_cloze_markdown(artifact, scaffolds.get("cloze_scaffold", {}))),
    ]
    markdown_paths: list[str] = []
    pdf_paths: list[str] = []
    for stem, markdown in markdown_items:
        markdown_path = output_dir / f"{stem}.md"
        write_text(markdown_path, markdown)
        markdown_paths.append(str(markdown_path))
        if render_pdf:
            pdf_path = output_dir / f"{stem}.pdf"
            markdown_to_pdf(markdown_path, pdf_path)
            pdf_paths.append(str(pdf_path))
    return {"markdown_paths": markdown_paths, "pdf_paths": pdf_paths}


def _source_heading(artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    title = str(source.get("title") or "Ukendt kilde").strip()
    lecture_key = str(source.get("lecture_key") or "").strip()
    return f"**Kilde:** {title}\n\n**Forelæsning:** {lecture_key}"


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def render_abridged_markdown(artifact: dict[str, Any], guide: dict[str, Any]) -> str:
    lines = [f"# {guide.get('title') or 'Forberedende oversigt'}", "", _source_heading(artifact), ""]
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(guide.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Struktur og hovedargumenter", ""])
    for point in _as_strings(guide.get("structure_and_main_arguments")):
        lines.append(f"- {point}")
    lines.extend(["", "## Nøglecitater at finde", ""])
    for item in _as_dicts(guide.get("key_quote_targets")):
        target = str(item.get("target") or "").strip()
        why = str(item.get("why") or "").strip()
        lines.append(f"- **{target}**: {why}")
    return "\n".join(lines)


def render_unit_test_markdown(artifact: dict[str, Any], suite: dict[str, Any]) -> str:
    lines = [f"# {suite.get('title') or 'Unit Test Suite'}", "", _source_heading(artifact), ""]
    instructions = str(suite.get("instructions") or "").strip()
    if instructions:
        lines.extend([f"*{instructions}*", ""])
    lines.extend(["## Spørgsmål i tekstens rækkefølge", ""])
    for item in _as_dicts(suite.get("questions")):
        number = int(item.get("number") or len(lines))
        question = str(item.get("question") or "").strip()
        lines.append(f"{number}. [ ] {question}")
        lines.append("")
    return "\n".join(lines)


def render_cloze_markdown(artifact: dict[str, Any], cloze: dict[str, Any]) -> str:
    lines = [f"# {cloze.get('title') or 'Scaffolding-opgaver'}", "", _source_heading(artifact), ""]
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(cloze.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Udfyldningssætninger", ""])
    for item in _as_dicts(cloze.get("fill_in_sentences")):
        number = int(item.get("number") or len(lines))
        sentence = str(item.get("sentence") or "").strip()
        lines.append(f"{number}. {sentence}")
        lines.append("")
    lines.extend(["", "## Tomme diagramopgaver", ""])
    diagram_items = _as_dicts(cloze.get("diagram_tasks"))
    space_cm = 2.2 if len(diagram_items) == 1 else 1.5 if len(diagram_items) == 2 else 1.0
    for item in diagram_items:
        number = int(item.get("number") or len(lines))
        task = str(item.get("task") or "").strip()
        hint = str(item.get("blank_space_hint") or "Brug feltet nedenfor.").strip()
        lines.append(f"{number}. {task}")
        lines.append("")
        lines.append(f"*{hint}*")
        lines.append("")
        lines.append(f"\\vspace{{{space_cm:.1f}cm}}")
        lines.append("")
        lines.append("\\hrule")
        lines.append("")
    return "\n".join(lines)


def markdown_to_pdf(markdown_path: Path, pdf_path: Path) -> None:
    if shutil.which("pandoc") is None:
        raise ScaffoldingError("pandoc is required to render scaffold PDFs")
    engine = "xelatex" if shutil.which("xelatex") else None
    command = [
        "pandoc",
        str(markdown_path),
        "-o",
        str(pdf_path),
        "-V",
        "papersize=a4",
        "-V",
        "geometry:margin=1.8cm",
        "-V",
        "fontsize=11pt",
    ]
    if engine:
        command.extend(["--pdf-engine", engine])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ScaffoldingError(f"pandoc failed for {markdown_path}: {detail}") from exc


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
    dry_run: bool = False,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    sources = select_sources(
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
            "source_count": len(sources),
            "sources": [
                {
                    "source_id": str(source.get("source_id") or ""),
                    "lecture_key": str(source.get("lecture_key") or ""),
                    "title": str(source.get("title") or ""),
                    "output_dir": str(output_dir_for_source(output_root, source)),
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
                )
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "error": recursive.format_error(exc)})
            if not continue_on_error:
                break
    return {
        "status": "error" if errors else "ok",
        "source_count": len(sources),
        "written_count": sum(1 for item in results if item.get("status") == "written"),
        "skipped_count": sum(1 for item in results if item.get("status") == "skipped_existing"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


def parse_source_families(values: list[str], *, all_families: bool = False) -> set[str] | None:
    if all_families:
        return None
    families = {item.strip() for value in values for item in value.split(",") if item.strip()}
    return families or {"reading"}
