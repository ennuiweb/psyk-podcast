"""Matrix-based semantic QA for Personlighedspsykologi printouts.

This module evaluates generated reading printouts against the validated
student-synthesis exam theory matrix. It does not change generation prompts and
does not treat the matrix as source authority; it produces review signals about
exam usefulness, comparison coverage, orientation-point framing, and common
misunderstanding prevention.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MATRIX_QA_SCHEMA_VERSION = 1
SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_OUTPUT_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/output")
DEFAULT_REPORT_ROOT = Path(
    "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/rubric_reports/latest"
)
CANONICAL_PRINTOUT_JSON_NAME = "reading-printouts.json"
CANONICAL_PRINTOUT_JSON_DIRNAME = "printout-json"

DIMENSION_IDS = (
    "theory_fit",
    "orientation_coverage",
    "comparison_value",
    "misunderstanding_prevention",
    "source_grounding_discipline",
    "exam_transfer",
)

ORIENTATION_KEYWORDS = {
    "essence_context": ("essens", "essential", "kontekst", "context", "indre", "ydre"),
    "determination": ("determination", "determiner", "bestemt", "dispon", "biologisk", "psykisk", "social"),
    "agency": ("agency", "agens", "handle", "valg", "frihed", "styrende", "aktiv"),
    "historicity": ("historicitet", "histor", "fylogen", "ontogen", "sociogen", "livsforløb"),
}
COMPARISON_KEYWORDS = (
    "sammenlign",
    "sammenligne",
    "kontrast",
    "forskel",
    "lighed",
    "compare",
    "contrast",
    "over for",
    "versus",
)
SOURCE_BOUNDARY_FORBIDDEN_MARKERS = (
    "student_synthesis",
    "student synthesis",
    "student note",
    "student-note",
    "anes tabel",
    "jaque",
    "exam_theory_matrix",
    "exam theory matrix",
)


class MatrixQAError(ValueError):
    """Raised when matrix QA cannot evaluate an artifact safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MatrixQAError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _normalize(value: object) -> str:
    text = str(value or "").casefold()
    text = text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _keyword_variants(value: object) -> list[str]:
    raw = str(value or "").strip()
    normalized = _normalize(raw)
    variants = {normalized}
    for token in normalized.split():
        if len(token) >= 5:
            variants.add(token)
    variants.discard("")
    return sorted(variants, key=len, reverse=True)


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _walk_text(value: object, path: str = "$") -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if isinstance(value, str):
        text = value.strip()
        if text:
            entries.append({"path": path, "text": text, "normalized": _normalize(text)})
    elif isinstance(value, dict):
        for key, item in value.items():
            entries.extend(_walk_text(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            entries.extend(_walk_text(item, f"{path}[{index}]"))
    return entries


def _entries_for_prefix(entries: list[dict[str, str]], prefixes: Iterable[str]) -> list[dict[str, str]]:
    prefix_tuple = tuple(prefixes)
    return [entry for entry in entries if entry["path"].startswith(prefix_tuple)]


def _find_keyword_evidence(
    entries: list[dict[str, str]],
    keywords: Iterable[object],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    variants: list[tuple[str, str]] = []
    for keyword in keywords:
        label = str(keyword or "").strip()
        for variant in _keyword_variants(label):
            if len(variant) >= 4:
                variants.append((label, variant))
    for entry in entries:
        normalized = entry["normalized"]
        for label, variant in variants:
            if variant and variant in normalized:
                key = (entry["path"], label)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    {
                        "path": entry["path"],
                        "match": label,
                        "snippet": _snippet(entry["text"], label),
                    }
                )
                if len(evidence) >= limit:
                    return evidence
    return evidence


def _snippet(text: str, keyword: object, *, max_length: int = 220) -> str:
    normalized_text = _normalize(text)
    variants = _keyword_variants(keyword)
    start = 0
    for variant in variants:
        index = normalized_text.find(variant)
        if index >= 0:
            rough_ratio = index / max(1, len(normalized_text))
            start = max(0, int(len(text) * rough_ratio) - 60)
            break
    snippet = re.sub(r"\s+", " ", text[start : start + max_length]).strip()
    if start > 0:
        snippet = "..." + snippet
    if start + max_length < len(text):
        snippet += "..."
    return snippet


def _score_status(score: int) -> str:
    if score >= 75:
        return "pass"
    if score >= 50:
        return "warn"
    return "fail"


def _dimension(
    *,
    score: int,
    findings: list[str],
    evidence: list[dict[str, str]] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    score = max(0, min(100, int(round(score))))
    return {
        "score": score,
        "status": _score_status(score),
        "findings": findings,
        "evidence_paths": [item["path"] for item in evidence or []],
        "evidence": evidence or [],
        "recommendations": recommendations or [],
    }


def validate_matrix_payload(matrix: Mapping[str, Any]) -> None:
    if matrix.get("artifact_type") != "exam_theory_matrix":
        raise MatrixQAError("matrix artifact_type must be exam_theory_matrix")
    if matrix.get("subject_slug") != SUBJECT_SLUG:
        raise MatrixQAError(f"matrix subject_slug must be {SUBJECT_SLUG}")
    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        raise MatrixQAError("matrix rows must be a non-empty list")


def matrix_rows_by_id(matrix: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_matrix_payload(matrix)
    return {
        str(row.get("theory_id") or "").strip(): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and str(row.get("theory_id") or "").strip()
    }


def relevant_matrix_rows(matrix: Mapping[str, Any], lecture_key: str) -> list[dict[str, Any]]:
    rows_by_id = matrix_rows_by_id(matrix)
    normalized_lecture = str(lecture_key or "").strip().upper()
    direct_rows = [
        row
        for row in rows_by_id.values()
        if normalized_lecture in {str(key or "").strip().upper() for key in _as_list(row.get("lecture_keys"))}
    ]
    if normalized_lecture != "W12L1":
        return direct_rows
    selected = {str(row.get("theory_id") or ""): row for row in direct_rows}
    for row in direct_rows:
        for target in _as_list(row.get("comparison_targets")):
            if not isinstance(target, dict):
                continue
            target_id = str(target.get("target_theory_id") or "").strip()
            if target_id in rows_by_id:
                selected[target_id] = rows_by_id[target_id]
    return list(selected.values())


def _row_keywords(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = [
        str(row.get("label") or ""),
        str(row.get("theory_id") or "").replace("_", " "),
        *_as_str_list(row.get("aliases")),
        *_as_str_list(row.get("central_concepts")),
        *_as_str_list(row.get("main_thinkers")),
    ]
    grounding = row.get("source_grounding") if isinstance(row.get("source_grounding"), dict) else {}
    values.extend(_as_str_list(grounding.get("concept_node_ids")))
    return [value for value in values if value.strip()]


def _theory_fit_dimension(rows: list[dict[str, Any]], entries: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return _dimension(
            score=0,
            findings=["No matrix row matched this printout's lecture key."],
            recommendations=["Check source.lecture_key and the matrix lecture_keys."],
        )
    row_scores: list[int] = []
    all_evidence: list[dict[str, str]] = []
    findings: list[str] = []
    for row in rows:
        keywords = _row_keywords(row)
        evidence = _find_keyword_evidence(entries, keywords, limit=6)
        matched = {item["match"] for item in evidence}
        target = min(5, max(2, len(keywords)))
        score = min(100, int((len(matched) / target) * 100))
        if matched:
            score = max(score, 45)
        row_scores.append(score)
        all_evidence.extend(evidence[:3])
        findings.append(
            f"{row.get('theory_id')}: matched {len(matched)} matrix keyword(s)."
        )
    score = int(sum(row_scores) / len(row_scores)) if row_scores else 0
    return _dimension(
        score=score,
        findings=findings,
        evidence=all_evidence[:8],
        recommendations=[] if score >= 75 else ["Make the relevant theory tradition explicit in the printout, especially in reading_guide or exam_bridge."],
    )


def _orientation_dimension(row: Mapping[str, Any], entries: list[dict[str, str]]) -> dict[str, Any]:
    coverage: dict[str, list[dict[str, str]]] = {}
    for point_id, keywords in ORIENTATION_KEYWORDS.items():
        row_point = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
        point = row_point.get(point_id) if isinstance(row_point.get(point_id), dict) else {}
        dynamic_keywords = [*keywords, point.get("placement", ""), point.get("summary", "")]
        evidence = _find_keyword_evidence(entries, dynamic_keywords, limit=3)
        if evidence:
            coverage[point_id] = evidence
    score = min(100, len(coverage) * 25)
    findings = [
        f"Covered orientation point: {point_id}."
        for point_id in sorted(coverage)
    ] or ["No explicit orientation-point coverage found."]
    evidence = [item for values in coverage.values() for item in values][:8]
    return _dimension(
        score=score,
        findings=findings,
        evidence=evidence,
        recommendations=[] if score >= 75 else ["Add at least one explicit exam cue about essence/context, determination, agency, or historicity."],
    )


def _comparison_dimension(rows: list[dict[str, Any]], entries: list[dict[str, str]]) -> dict[str, Any]:
    comparison_entries = _entries_for_prefix(
        entries,
        (
            "$.printouts.exam_bridge.comparison_targets",
            "$.printouts.exam_bridge.course_connections",
            "$.printouts.exam_bridge.exam_moves",
            "$.printouts.reading_guide",
        ),
    )
    target_keywords: list[str] = [*COMPARISON_KEYWORDS]
    for row in rows:
        for target in _as_list(row.get("comparison_targets")):
            if not isinstance(target, dict):
                continue
            target_keywords.append(str(target.get("target_theory_id") or "").replace("_", " "))
            target_keywords.append(str(target.get("rationale") or ""))
    evidence = _find_keyword_evidence(comparison_entries or entries, target_keywords, limit=8)
    explicit_targets = len(
        _entries_for_prefix(entries, ("$.printouts.exam_bridge.comparison_targets",))
    )
    score = min(100, len(evidence) * 15 + min(explicit_targets, 3) * 15)
    findings = [f"Found {len(evidence)} comparison signal(s)."]
    if explicit_targets:
        findings.append(f"Exam bridge includes {explicit_targets} comparison target text field(s).")
    return _dimension(
        score=score,
        findings=findings,
        evidence=evidence,
        recommendations=[] if score >= 75 else ["Strengthen exam_bridge.comparison_targets with a direct contrast from the matrix row."],
    )


def _misunderstanding_dimension(rows: list[dict[str, Any]], entries: list[dict[str, str]]) -> dict[str, Any]:
    trap_entries = _entries_for_prefix(entries, ("$.printouts.exam_bridge.misunderstanding_traps",))
    trap_keywords: list[str] = []
    for row in rows:
        trap_keywords.extend(_as_str_list(row.get("likely_misunderstandings")))
    evidence = _find_keyword_evidence(trap_entries or entries, trap_keywords, limit=8)
    trap_text_count = len(trap_entries)
    score = min(100, len(evidence) * 20 + min(trap_text_count, 4) * 10)
    if trap_text_count and not evidence:
        score = max(score, 55)
    findings = [f"Found {trap_text_count} misunderstanding-trap text field(s)."]
    if evidence:
        findings.append(f"Matched {len(evidence)} matrix trap signal(s).")
    return _dimension(
        score=score,
        findings=findings,
        evidence=evidence,
        recommendations=[] if score >= 75 else ["Add or sharpen exam_bridge.misunderstanding_traps using the matrix row's likely misunderstandings."],
    )


def _source_grounding_dimension(entries: list[dict[str, str]]) -> dict[str, Any]:
    evidence = _find_keyword_evidence(entries, SOURCE_BOUNDARY_FORBIDDEN_MARKERS, limit=8)
    score = 100 if not evidence else 0
    findings = (
        ["No student-synthesis leakage markers found in learner-facing printout text."]
        if not evidence
        else ["Found text that appears to expose student-synthesis internals."]
    )
    return _dimension(
        score=score,
        findings=findings,
        evidence=evidence,
        recommendations=[] if score == 100 else ["Remove references to student notes, matrix artifacts, or internal synthesis provenance from learner-facing printouts."],
    )


def _exam_transfer_dimension(entries: list[dict[str, str]]) -> dict[str, Any]:
    exam_prefixes = (
        "$.printouts.exam_bridge.use_this_text_for",
        "$.printouts.exam_bridge.course_connections",
        "$.printouts.exam_bridge.exam_moves",
        "$.printouts.exam_bridge.mini_exam_prompt_question",
        "$.printouts.exam_bridge.mini_exam_answer_plan_slots",
    )
    exam_entries = _entries_for_prefix(entries, exam_prefixes)
    exam_keywords = (
        "eksamen",
        "mundtlig",
        "prøve",
        "exam",
        "svar",
        "answer",
        "argument",
        "diskuter",
        "redegør",
        "course",
        "kursus",
    )
    evidence = _find_keyword_evidence(exam_entries or entries, exam_keywords, limit=8)
    section_score = min(60, len(exam_entries) * 4)
    keyword_score = min(40, len(evidence) * 10)
    score = section_score + keyword_score
    findings = [f"Found {len(exam_entries)} exam-bridge transfer text field(s)."]
    if evidence:
        findings.append(f"Matched {len(evidence)} exam-transfer signal(s).")
    return _dimension(
        score=score,
        findings=findings,
        evidence=evidence,
        recommendations=[] if score >= 75 else ["Ensure exam_bridge gives concrete oral-exam uses, course connections, and answer-plan cues."],
    )


def evaluate_printout_artifact(
    *,
    artifact: Mapping[str, Any],
    artifact_path: Path | None,
    matrix: Mapping[str, Any],
    matrix_path: Path | None = None,
    repo_root: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_matrix_payload(matrix)
    if artifact.get("artifact_type") != "reading_printouts":
        raise MatrixQAError("printout artifact_type must be reading_printouts")
    if int(artifact.get("schema_version") or 0) < 3:
        raise MatrixQAError("matrix QA requires schema_version >= 3 printout artifacts")
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_id = str(source.get("source_id") or "").strip()
    lecture_key = str(source.get("lecture_key") or "").strip()
    if not source_id:
        raise MatrixQAError("printout source.source_id is missing")
    if not lecture_key:
        raise MatrixQAError("printout source.lecture_key is missing")
    rows = relevant_matrix_rows(matrix, lecture_key)
    entries = _walk_text({"printouts": artifact.get("printouts") or artifact.get("scaffolds") or {}})
    primary_row = rows[0] if rows else {}
    dimensions = {
        "theory_fit": _theory_fit_dimension(rows, entries),
        "orientation_coverage": _orientation_dimension(primary_row, entries) if rows else _dimension(score=0, findings=["No matrix row available."]),
        "comparison_value": _comparison_dimension(rows, entries),
        "misunderstanding_prevention": _misunderstanding_dimension(rows, entries),
        "source_grounding_discipline": _source_grounding_dimension(entries),
        "exam_transfer": _exam_transfer_dimension(entries),
    }
    overall_score = int(round(sum(dimensions[key]["score"] for key in DIMENSION_IDS) / len(DIMENSION_IDS)))
    root = repo_root or Path(".").resolve()
    return {
        "artifact_type": "printout_matrix_qa_report",
        "schema_version": MATRIX_QA_SCHEMA_VERSION,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": generated_at or utc_now_iso(),
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": str(source.get("title") or source.get("reading_title") or ""),
            "artifact_path": _display_path(artifact_path, root) if artifact_path else "",
        },
        "matrix": {
            "path": _display_path(matrix_path, root) if matrix_path else "",
            "sha256": sha256_file(matrix_path) if matrix_path and matrix_path.exists() else "",
            "row_ids": [str(row.get("theory_id") or "") for row in rows],
        },
        "overall_score": overall_score,
        "status": _score_status(overall_score),
        "dimensions": dimensions,
        "recommendation_priority": _recommendation_priority(dimensions),
    }


def _recommendation_priority(dimensions: Mapping[str, Any]) -> list[str]:
    items = []
    for dimension_id, dimension in dimensions.items():
        if not isinstance(dimension, dict):
            continue
        if str(dimension.get("status") or "") == "pass":
            continue
        for recommendation in _as_str_list(dimension.get("recommendations")):
            items.append(f"{dimension_id}: {recommendation}")
    return items


def render_report_markdown(report: Mapping[str, Any]) -> str:
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    matrix = report.get("matrix") if isinstance(report.get("matrix"), dict) else {}
    lines = [
        f"# Matrix QA: {source.get('source_id', '')}",
        "",
        f"- Lecture: `{source.get('lecture_key', '')}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Overall score: `{report.get('overall_score', 0)}`",
        f"- Matrix rows: {', '.join(f'`{row_id}`' for row_id in _as_str_list(matrix.get('row_ids'))) or 'none'}",
        "",
        "## Dimensions",
        "",
    ]
    dimensions = report.get("dimensions") if isinstance(report.get("dimensions"), dict) else {}
    for dimension_id in DIMENSION_IDS:
        dimension = dimensions.get(dimension_id) if isinstance(dimensions.get(dimension_id), dict) else {}
        lines.extend(
            [
                f"### {dimension_id}",
                "",
                f"- Status: `{dimension.get('status', '')}`",
                f"- Score: `{dimension.get('score', 0)}`",
                "",
                "Findings:",
            ]
        )
        for finding in _as_str_list(dimension.get("findings")):
            lines.append(f"- {finding}")
        recommendations = _as_str_list(dimension.get("recommendations"))
        if recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for recommendation in recommendations:
                lines.append(f"- {recommendation}")
        evidence = _as_list(dimension.get("evidence"))
        if evidence:
            lines.append("")
            lines.append("Evidence:")
            for item in evidence[:5]:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- `{item.get('path', '')}` matched `{item.get('match', '')}`: {item.get('snippet', '')}")
        lines.append("")
    priority = _as_str_list(report.get("recommendation_priority"))
    if priority:
        lines.extend(["## Priority Fixes", ""])
        for item in priority:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_summary_report(
    reports: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
    report_root: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    scores = [int(report.get("overall_score") or 0) for report in reports]
    status_counts = {
        status: sum(1 for report in reports if report.get("status") == status)
        for status in ("pass", "warn", "fail")
    }
    root = repo_root or Path(".").resolve()
    return {
        "artifact_type": "printout_matrix_qa_summary",
        "schema_version": MATRIX_QA_SCHEMA_VERSION,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": generated_at or utc_now_iso(),
        "report_root": _display_path(report_root, root) if report_root else "",
        "source_count": len(reports),
        "average_score": int(round(sum(scores) / len(scores))) if scores else 0,
        "status": "failed" if status_counts["fail"] else ("warn" if status_counts["warn"] else "pass"),
        "status_counts": status_counts,
        "lowest_scoring_sources": sorted(
            [
                {
                    "source_id": report.get("source", {}).get("source_id", ""),
                    "lecture_key": report.get("source", {}).get("lecture_key", ""),
                    "overall_score": report.get("overall_score", 0),
                    "status": report.get("status", ""),
                }
                for report in reports
            ],
            key=lambda item: (int(item["overall_score"]), str(item["source_id"])),
        )[:10],
    }


def render_summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Matrix QA Summary",
        "",
        f"- Status: `{summary.get('status', '')}`",
        f"- Source count: `{summary.get('source_count', 0)}`",
        f"- Average score: `{summary.get('average_score', 0)}`",
        "",
        "## Lowest Scoring Sources",
        "",
    ]
    for item in _as_list(summary.get("lowest_scoring_sources")):
        if isinstance(item, dict):
            lines.append(
                f"- `{item.get('source_id', '')}` ({item.get('lecture_key', '')}): "
                f"{item.get('overall_score', 0)} / {item.get('status', '')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def write_report_bundle(report_root: Path, reports: list[dict[str, Any]], *, repo_root: Path) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    for report in reports:
        source = report.get("source") if isinstance(report.get("source"), dict) else {}
        source_id = str(source.get("source_id") or "unknown")
        write_json(report_root / f"{source_id}.json", report)
        (report_root / f"{source_id}.md").write_text(render_report_markdown(report), encoding="utf-8")
    summary = build_summary_report(reports, report_root=report_root, repo_root=repo_root)
    write_json(report_root / "summary.json", summary)
    (report_root / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    return summary
