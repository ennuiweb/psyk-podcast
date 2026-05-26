from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue import personlighedspsykologi_notebooklm_gap_repair as gap_repair
from notebooklm_queue import personlighedspsykologi_student_synthesis as synthesis


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _orientation_points() -> dict[str, dict[str, str]]:
    return {
        point_id: {
            "placement": f"{point_id} placement",
            "summary": f"{point_id} summary",
        }
        for point_id in synthesis.ORIENTATION_POINT_IDS
    }


def _row(theory_id: str, label: str, *, target: str | None = None) -> dict:
    return {
        "theory_id": theory_id,
        "label": label,
        "aliases": [label],
        "lecture_keys": ["W01L1"],
        "course_role": f"{label} gives the course a theory frame.",
        "course_summary": f"{label} explains personality through a compact frame.",
        "student_note_labels": ["Theory sheet"],
        "model_of_person": f"{label} has a specific model of the person.",
        "personality_or_subjectivity_model": f"{label} has a specific model of subjectivity.",
        "method_evidence_style": f"{label} uses a recognizable method and evidence style.",
        "main_thinkers": ["Thinker"],
        "central_concepts": ["agency", "subjectivity", "context"],
        "orientation_points": _orientation_points(),
        "strengths": ["Makes one thing visible."],
        "limitations": ["Hides one thing."],
        "comparison_targets": [
            {
                "target_theory_id": target,
                "relation": "contrasts_with",
                "rationale": "It makes a useful exam contrast.",
            }
        ]
        if target
        else [],
        "likely_misunderstandings": ["Reducing the theory to a slogan."],
        "student_synthesis_notes": "Use this row as a compact exam comparison frame.",
        "source_note_basis": [
            {
                "note_id": "note_1",
                "basis_status": "primary_student_note",
                "summary": "The source note supports the row's comparison frame.",
            }
        ],
        "source_grounding": {
            "course_theory_map_ids": [theory_id],
            "concept_node_ids": [f"{theory_id}_concept"],
            "distinction_ids": [],
            "representative_source_ids": ["source-1"],
            "representative_evidence_origins": ["reading_grounded"],
        },
        "validation_status": "validated",
        "warnings": [],
    }


def _matrix() -> dict:
    rows = [
        _row("critical_personalism", "Critical personalism", target="critical_psychology"),
        _row("critical_psychology", "Kritisk psykologi", target="critical_personalism"),
    ]
    return {
        "artifact_type": "exam_theory_matrix",
        "schema_version": synthesis.STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "authority": "student_exam_synthesis",
        "build": {
            "builder": "scripts/build_personlighedspsykologi_exam_theory_matrix.py",
            "model": "deterministic-curated-student-synthesis",
            "prompt_version": "test",
        },
        "provenance": {
            "input_source_ids": ["note_1"],
            "source_notes_signature": "abc",
            "dependency_hashes": {"seed": "123"},
        },
        "orientation_points": [
            {"orientation_point_id": point_id, "label": point_id, "question": "Question?"}
            for point_id in synthesis.ORIENTATION_POINT_IDS
        ],
        "rows": rows,
        "stats": {"row_count": len(rows)},
        "warnings": [],
    }


def _coverage_report() -> dict:
    return {
        "artifact_type": "personlighedspsykologi_flashcard_coverage_report",
        "subject_slug": "personlighedspsykologi",
        "rows": [
            {
                "theory_id": "critical_personalism",
                "units": [
                    {
                        "unit_id": "critical_personalism:comparison_targets:critical_psychology",
                        "status": "missing",
                        "priority": "high",
                        "confidence": "none",
                    },
                    {
                        "unit_id": "critical_personalism:likely_misunderstandings:1",
                        "status": "weak",
                        "priority": "high",
                        "confidence": "low",
                    },
                    {
                        "unit_id": "critical_personalism:orientation_points:agency",
                        "status": "missing",
                        "priority": "high",
                        "confidence": "none",
                    },
                    {
                        "unit_id": "critical_personalism:method_evidence_style",
                        "status": "weak",
                        "priority": "high",
                        "confidence": "low",
                    },
                    {
                        "unit_id": "critical_personalism:source_note_basis:note_1",
                        "status": "weak",
                        "priority": "high",
                        "confidence": "low",
                    },
                    {
                        "unit_id": "critical_personalism:course_summary",
                        "status": "missing",
                        "priority": "normal",
                        "confidence": "none",
                    },
                ],
            }
        ],
    }


def _notes(label: str = "Ane source sheet") -> dict:
    return {
        "subject_slug": "personlighedspsykologi",
        "notes": [
            {
                "note_id": "note_1",
                "label": label,
                "matrix_policy": "primary_basis",
            }
        ],
    }


def test_build_gap_repair_plan_splits_high_priority_gaps_without_card_sources() -> None:
    plan = gap_repair.build_gap_repair_plan(
        matrix=_matrix(),
        coverage_report=_coverage_report(),
        notes_index=_notes(),
        notes_registry=_notes(),
        run_id="test-gap-run",
        generated_at="2026-05-26T00:00:00Z",
    )

    notebooks = {notebook["slug"]: notebook for notebook in plan["notebooks"]}
    assert plan["artifact_type"] == gap_repair.GAP_REPAIR_ARTIFACT_TYPE
    assert plan["gap_summary"]["gap_count"] == 5
    assert plan["source_policy"]["existing_freudd_cards_uploaded"] is False
    assert plan["source_policy"]["raw_student_notes_uploaded"] is False
    assert notebooks["gap-repair-comparisons-traps"]["gap_count"] == 2
    assert notebooks["gap-repair-orientation-method"]["gap_count"] == 2
    assert notebooks["gap-repair-source-basis"]["gap_count"] == 1


def test_export_gap_repair_run_writes_processed_packs_without_student_note_metadata(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.json"
    coverage_path = tmp_path / "coverage.json"
    notes_index_path = tmp_path / "notes-index.json"
    notes_registry_path = tmp_path / "notes-registry.json"
    _write_json(matrix_path, _matrix())
    _write_json(coverage_path, _coverage_report())
    _write_json(notes_index_path, _notes())
    _write_json(notes_registry_path, _notes())

    manifest = gap_repair.export_gap_repair_run(
        run_id="test-gap-run",
        lab_root=tmp_path / "lab",
        matrix_path=matrix_path,
        coverage_report_path=coverage_path,
        source_notes_index_path=notes_index_path,
        source_notes_registry_path=notes_registry_path,
        repo_root=tmp_path,
        generated_at="2026-05-26T00:00:00Z",
    )

    assert {notebook["slug"] for notebook in manifest["notebooks"]} == {
        "gap-repair-comparisons-traps",
        "gap-repair-orientation-method",
        "gap-repair-source-basis",
    }
    run_root = tmp_path / "lab" / "runs" / "test-gap-run"
    assert (run_root / "manifest.json").exists()
    assert (run_root / "gap_repair_plan.json").exists()
    source_notebook = next(
        notebook for notebook in manifest["notebooks"] if notebook["slug"] == "gap-repair-source-basis"
    )
    pack_dir = tmp_path / source_notebook["pack_dir"]
    uploaded_text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(pack_dir.glob("*.md")))
    assert source_notebook["source_count"] == 5
    assert "Ane" not in uploaded_text
    assert "note_1" not in uploaded_text
    assert "Matrix policy" not in uploaded_text
    assert "existing Freudd cards" in uploaded_text


def test_render_gap_repair_plan_markdown_records_notebook_split() -> None:
    plan = gap_repair.build_gap_repair_plan(
        matrix=_matrix(),
        coverage_report=_coverage_report(),
        notes_index=_notes(),
        notes_registry=_notes(),
        run_id="test-gap-run",
        generated_at="2026-05-26T00:00:00Z",
    )

    markdown = gap_repair.render_gap_repair_plan_markdown(plan)

    assert "gap-repair-comparisons-traps" in markdown
    assert "Existing Freudd card text is not uploaded" in markdown
