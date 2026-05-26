"""Targeted NotebookLM source packs for high-priority flashcard coverage gaps."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_fingerprint, write_json_stably
from notebooklm_queue.personlighedspsykologi_flashcard_coverage import (
    DEFAULT_DECK_PATH,
    DEFAULT_MATRIX_PATH,
    DEFAULT_OUTPUT_JSON,
    DEFAULT_SOURCE_NOTES_INDEX_PATH,
    DEFAULT_SOURCE_NOTES_REGISTRY_PATH,
    FlashcardCoverageError,
    matrix_coverage_units,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_LAB_ROOT,
    FlashcardLabError,
    _as_list,
    _as_str_list,
    _source_entry,
    _text,
    load_matrix,
    render_output_contract,
    utc_now_iso,
    write_manifest_readme,
)

GAP_REPAIR_VERSION = 1
GAP_REPAIR_ARTIFACT_TYPE = "personlighedspsykologi_notebooklm_gap_repair_plan"
DEFAULT_GAP_REPAIR_RUN_ID = "gap-repair-20260526-high-priority"
DEFAULT_PLAN_JSON = Path("shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_notebook_plan.json")
DEFAULT_PLAN_MD = Path("shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_notebook_plan.md")


class GapRepairError(ValueError):
    """Raised when NotebookLM gap-repair packs cannot be built safely."""


@dataclass(frozen=True)
class GapRepairNotebookSpec:
    slug: str
    title: str
    purpose: str
    fields: tuple[str, ...]


GAP_REPAIR_SPECS: tuple[GapRepairNotebookSpec, ...] = (
    GapRepairNotebookSpec(
        slug="gap-repair-comparisons-traps",
        title="Freudd personlighedspsykologi gap repair - comparisons and exam traps",
        purpose="Generate cards only for missing comparison-target and likely-misunderstanding coverage units.",
        fields=("comparison_targets", "likely_misunderstandings"),
    ),
    GapRepairNotebookSpec(
        slug="gap-repair-orientation-method",
        title="Freudd personlighedspsykologi gap repair - orientation and method",
        purpose="Generate cards only for missing orientation-axis and method/evidence coverage units.",
        fields=("orientation_points", "method_evidence_style"),
    ),
    GapRepairNotebookSpec(
        slug="gap-repair-source-basis",
        title="Freudd personlighedspsykologi gap repair - source-basis repair",
        purpose="Generate cards only for weak source-note-basis coverage units using matrix source-basis summaries.",
        fields=("source_note_basis",),
    ),
)


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise GapRepairError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise GapRepairError(f"JSON root must be an object: {path}")
    return payload


def _rows_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("theory_id")): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }


def _coverage_units_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        for unit in matrix_coverage_units(row):
            unit = dict(unit)
            unit["theory_id"] = theory_id
            units[_text(unit.get("unit_id"))] = unit
    return units


def _high_priority_gaps(coverage_report: dict[str, Any], matrix: dict[str, Any]) -> list[dict[str, Any]]:
    units_by_id = _coverage_units_by_id(matrix)
    gaps: list[dict[str, Any]] = []
    for row_report in _as_list(coverage_report.get("rows")):
        if not isinstance(row_report, dict):
            continue
        theory_id = _text(row_report.get("theory_id"))
        for unit_report in _as_list(row_report.get("units")):
            if not isinstance(unit_report, dict):
                continue
            if unit_report.get("priority") != "high" or unit_report.get("status") not in {"missing", "weak"}:
                continue
            unit_id = _text(unit_report.get("unit_id"))
            unit = dict(units_by_id.get(unit_id) or {})
            if not unit:
                raise GapRepairError(f"Coverage report references unknown matrix coverage unit: {unit_id}")
            unit.update(
                {
                    "status": _text(unit_report.get("status")),
                    "confidence": _text(unit_report.get("confidence")),
                    "best_overlap": unit_report.get("best_overlap"),
                    "card_ids": _as_str_list(unit_report.get("card_ids")),
                    "theory_id": theory_id,
                }
            )
            gaps.append(unit)
    return gaps


def _split_specs(gaps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_slug = {spec.slug: [] for spec in GAP_REPAIR_SPECS}
    field_to_slug = {
        field: spec.slug
        for spec in GAP_REPAIR_SPECS
        for field in spec.fields
    }
    for gap in gaps:
        slug = field_to_slug.get(_text(gap.get("field")))
        if slug:
            by_slug[slug].append(gap)
    return by_slug


def _render_repair_brief(spec: GapRepairNotebookSpec, gaps: list[dict[str, Any]]) -> str:
    fields = ", ".join(spec.fields)
    return "\n".join(
        [
            "# Gap-repair card-authoring brief",
            "",
            f"Notebook: {spec.title}",
            f"Purpose: {spec.purpose}",
            f"Allowed coverage fields in this notebook: {fields}",
            f"Target gap count: {len(gaps)}",
            "",
            "You are generating Danish oral-exam flashcard candidates for Freudd.",
            "",
            "Hard rules:",
            "",
            "- Generate cards only for the listed coverage gaps.",
            "- Prefer one precise card per listed gap; use two only if one card would become overloaded.",
            "- Do not mention coverage unit IDs, source-note IDs, student names, local paths, or internal provenance in the card front/back.",
            "- Do not invent claims beyond the matrix row and source-basis summaries in this notebook.",
            "- Write compact Danish cards: front as one question, back as 1-4 sentences or 2-4 bullets.",
            "- Avoid broad restatements unless the gap itself is broad; make the retrieval cue exam-useful.",
            "- Do not assume existing Freudd cards are present. Duplicate checks happen after generation.",
            "",
            "If a gap cannot be turned into a safe flashcard, skip it rather than filling it with vague content.",
        ]
    ) + "\n"


def _display_gap_label(gap: dict[str, Any]) -> str:
    if _text(gap.get("field")) == "source_note_basis":
        theory_id = _text(gap.get("theory_id")).replace("_", " ")
        return f"Source-backed nuance for {theory_id}".strip()
    return _text(gap.get("label"))


def _render_gap_units(spec: GapRepairNotebookSpec, gaps: list[dict[str, Any]]) -> str:
    lines = ["# Target coverage gaps", ""]
    for index, gap in enumerate(gaps, start=1):
        lines.extend(
            [
                f"## Target {index}",
                "",
                f"Coverage field: `{_text(gap.get('field'))}`",
                f"Theory ID: `{_text(gap.get('theory_id'))}`",
                f"Status: `{_text(gap.get('status'))}`",
                f"Target theory ID: `{_text(gap.get('target_theory_id'))}`" if _text(gap.get("target_theory_id")) else "",
                "",
                f"Label: {_display_gap_label(gap)}",
                "",
                "Expected matrix/source point:",
                "",
                _text(gap.get("expected_text")),
                "",
                "Card instruction:",
                "",
                f"- Write a card that directly tests this {_text(gap.get('field')).replace('_', ' ')} gap.",
                "- Do not include the coverage unit ID or source-note ID in the learner-facing card.",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def _render_matrix_context(rows: dict[str, dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    theory_ids = sorted({_text(gap.get("theory_id")) for gap in gaps if _text(gap.get("theory_id"))})
    lines = ["# Matrix row context", ""]
    for theory_id in theory_ids:
        row = rows.get(theory_id)
        if not row:
            continue
        lines.extend(
            [
                f"## {_text(row.get('label')) or theory_id}",
                "",
                f"ID: `{theory_id}`",
                f"Course role: {_text(row.get('course_role'))}",
                "",
                f"Course summary: {_text(row.get('course_summary'))}",
                "",
                f"Model of person: {_text(row.get('model_of_person'))}",
                "",
                f"Personality/subjektivitet: {_text(row.get('personality_or_subjectivity_model'))}",
                "",
                f"Method/evidence: {_text(row.get('method_evidence_style'))}",
                "",
                "Central concepts: " + "; ".join(_as_str_list(row.get("central_concepts"))),
                "",
                "Orientation points:",
                "",
            ]
        )
        orientation = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
        for point_id, point in orientation.items():
            if isinstance(point, dict):
                lines.append(f"- `{point_id}`: {_text(point.get('placement'))} - {_text(point.get('summary'))}")
        lines.extend(["", "Strengths:", ""])
        lines.extend(f"- {item}" for item in _as_str_list(row.get("strengths")))
        lines.extend(["", "Limitations:", ""])
        lines.extend(f"- {item}" for item in _as_str_list(row.get("limitations")))
        lines.extend(["", "Likely misunderstandings:", ""])
        lines.extend(f"- {item}" for item in _as_str_list(row.get("likely_misunderstandings")))
        lines.extend(["", "Comparison targets:", ""])
        for target in _as_list(row.get("comparison_targets")):
            if isinstance(target, dict):
                lines.append(
                    f"- `{_text(target.get('target_theory_id'))}`: "
                    f"{_text(target.get('relation')).replace('_', ' ')} - {_text(target.get('rationale'))}"
                )
        lines.extend(["", "---", ""])
    return "\n".join(lines)


def _render_source_basis(rows: dict[str, dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    theory_ids = sorted({_text(gap.get("theory_id")) for gap in gaps if _text(gap.get("theory_id"))})
    lines = ["# Source-basis summaries", ""]
    for theory_id in theory_ids:
        row = rows.get(theory_id)
        if not row:
            continue
        source_basis = [basis for basis in _as_list(row.get("source_note_basis")) if isinstance(basis, dict)]
        if not source_basis:
            continue
        lines.extend([f"## {_text(row.get('label')) or theory_id}", ""])
        for index, basis in enumerate(source_basis, start=1):
            lines.extend(
                [
                    f"- Basis item {index}",
                    f"  - Summary: {_text(basis.get('summary'))}",
                ]
            )
        lines.extend(["", "---", ""])
    return "\n".join(lines)


def _render_gap_output_contract() -> str:
    return "\n".join(
        [
            render_output_contract().strip(),
            "",
            "Gap-repair additions:",
            "",
            "- Every generated card should correspond to one listed gap.",
            "- Do not print the gap/unit/source IDs inside the card text.",
            "- Good fronts should make the missing comparison, method, orientation point, exam trap, or source-backed nuance retrievable.",
            "- Good backs should be self-contained enough for oral-exam recall.",
        ]
    ) + "\n"


def build_gap_repair_plan(
    *,
    matrix: dict[str, Any],
    coverage_report: dict[str, Any],
    notes_index: dict[str, Any],
    notes_registry: dict[str, Any],
    run_id: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    gaps = _high_priority_gaps(coverage_report, matrix)
    if not gaps:
        raise GapRepairError("No high-priority missing/weak coverage gaps found")
    by_slug = _split_specs(gaps)
    notebooks = []
    for spec in GAP_REPAIR_SPECS:
        spec_gaps = by_slug[spec.slug]
        if not spec_gaps:
            continue
        notebooks.append(
            {
                "slug": spec.slug,
                "title": spec.title,
                "purpose": spec.purpose,
                "fields": list(spec.fields),
                "gap_count": len(spec_gaps),
                "status_counts": dict(sorted(Counter(_text(gap.get("status")) for gap in spec_gaps).items())),
                "theory_ids": sorted({_text(gap.get("theory_id")) for gap in spec_gaps if _text(gap.get("theory_id"))}),
                "gap_unit_ids": [_text(gap.get("unit_id")) for gap in spec_gaps],
            }
        )
    return {
        "version": GAP_REPAIR_VERSION,
        "artifact_type": GAP_REPAIR_ARTIFACT_TYPE,
        "subject_slug": "personlighedspsykologi",
        "run_id": run_id,
        "generated_at": generated_at or utc_now_iso(),
        "source_policy": {
            "processed_sources_only": True,
            "existing_freudd_cards_uploaded": False,
            "raw_student_notes_uploaded": False,
        },
        "gap_summary": {
            "gap_count": len(gaps),
            "field_counts": dict(sorted(Counter(_text(gap.get("field")) for gap in gaps).items())),
            "status_counts": dict(sorted(Counter(_text(gap.get("status")) for gap in gaps).items())),
            "theory_counts": dict(sorted(Counter(_text(gap.get("theory_id")) for gap in gaps).items())),
        },
        "notebooks": notebooks,
        "input_fingerprints": {
            "matrix": semantic_fingerprint(matrix),
            "coverage_report": semantic_fingerprint(coverage_report),
            "source_notes_index": semantic_fingerprint(notes_index),
            "source_notes_registry": semantic_fingerprint(notes_registry),
        },
    }


def export_gap_repair_run(
    *,
    run_id: str,
    lab_root: Path,
    matrix_path: Path,
    coverage_report_path: Path,
    source_notes_index_path: Path,
    source_notes_registry_path: Path,
    repo_root: Path,
    notebook_slugs: set[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    matrix = load_matrix(matrix_path)
    coverage_report = _load_json(coverage_report_path)
    notes_index = _load_json(source_notes_index_path)
    notes_registry = _load_json(source_notes_registry_path)
    plan = build_gap_repair_plan(
        matrix=matrix,
        coverage_report=coverage_report,
        notes_index=notes_index,
        notes_registry=notes_registry,
        run_id=run_id,
        generated_at=generated_at,
    )
    rows = _rows_by_id(matrix)
    gaps_by_id = {_text(gap.get("unit_id")): gap for gap in _high_priority_gaps(coverage_report, matrix)}
    run_root = lab_root / "runs" / run_id
    packs_root = run_root / "packs"
    manifest_notebooks = []
    selected_specs = [spec for spec in GAP_REPAIR_SPECS if notebook_slugs is None or spec.slug in notebook_slugs]
    selected_by_slug = {spec.slug: spec for spec in selected_specs}
    for notebook in plan["notebooks"]:
        slug = _text(notebook.get("slug"))
        spec = selected_by_slug.get(slug)
        if spec is None:
            continue
        gaps = [gaps_by_id[unit_id] for unit_id in _as_str_list(notebook.get("gap_unit_ids")) if unit_id in gaps_by_id]
        pack_dir = packs_root / slug
        pack_dir.mkdir(parents=True, exist_ok=True)
        for stale_markdown in pack_dir.glob("*.md"):
            stale_markdown.unlink()
        files = {
            "00-gap-repair-brief.md": _render_repair_brief(spec, gaps),
            "01-target-coverage-gaps.md": _render_gap_units(spec, gaps),
            "02-matrix-row-context.md": _render_matrix_context(rows, gaps),
            "03-source-basis-summaries.md": _render_source_basis(rows, gaps),
            "04-output-contract.md": _render_gap_output_contract(),
        }
        for filename, content in files.items():
            (pack_dir / filename).write_text(content, encoding="utf-8")
        source_entries = [_source_entry(pack_dir / filename, repo_root) for filename in sorted(files)]
        manifest_notebooks.append(
            {
                **notebook,
                "pack_dir": _repo_relative(pack_dir, repo_root),
                "sources": source_entries,
                "source_count": len(source_entries),
                "status": "pack_exported",
                "notebooklm_notebook_id": None,
                "flashcard_generation": {
                    "quantity": "more",
                    "difficulty": "hard",
                    "instructions": (
                        "Generate Danish oral-exam flashcard candidates only for the listed gap-repair targets. "
                        "Prioritize precise comparison, orientation, method, exam-trap, and source-backed nuance cards. "
                        "Do not include internal gap IDs, source IDs, student names, or file paths in card text."
                    ),
                },
            }
        )
    if not manifest_notebooks:
        raise GapRepairError("No gap-repair notebooks selected")
    manifest = {
        "version": GAP_REPAIR_VERSION,
        "artifact_type": "personlighedspsykologi_notebooklm_gap_repair_manifest",
        "subject_slug": "personlighedspsykologi",
        "run_id": run_id,
        "generated_at": generated_at or utc_now_iso(),
        "lab_root": _repo_relative(lab_root, repo_root),
        "plan_fingerprint": semantic_fingerprint(plan),
        "notebooks": manifest_notebooks,
    }
    write_json_stably(run_root / "manifest.json", manifest)
    write_json_stably(run_root / "gap_repair_plan.json", plan)
    write_manifest_readme(run_root, manifest)
    return manifest


def render_gap_repair_plan_markdown(plan: dict[str, Any]) -> str:
    summary = plan.get("gap_summary") if isinstance(plan.get("gap_summary"), dict) else {}
    lines = [
        "# NotebookLM Gap-Repair Plan",
        "",
        f"Run ID: `{plan.get('run_id')}`",
        "",
        "## Summary",
        "",
        f"- Gap count: {summary.get('gap_count')}",
        f"- Field counts: `{summary.get('field_counts')}`",
        f"- Status counts: `{summary.get('status_counts')}`",
        "",
        "## Notebook Packs",
        "",
        "| Notebook | Fields | Gaps | Theories |",
        "|---|---|---:|---|",
    ]
    for notebook in _as_list(plan.get("notebooks")):
        if not isinstance(notebook, dict):
            continue
        lines.append(
            f"| `{notebook.get('slug')}` | {', '.join(_as_str_list(notebook.get('fields')))} | "
            f"{notebook.get('gap_count')} | {', '.join(_as_str_list(notebook.get('theory_ids')))} |"
        )
    lines.extend(
        [
            "",
            "## Source Policy",
            "",
            "- NotebookLM sees processed matrix/source-basis summaries only.",
            "- Existing Freudd card text is not uploaded as NotebookLM source.",
            "- Raw student-note PDFs/DOCX files are not uploaded.",
            "",
        ]
    )
    return "\n".join(lines)
