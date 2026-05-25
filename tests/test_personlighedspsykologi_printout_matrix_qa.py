import json
import subprocess
import sys
from pathlib import Path

from notebooklm_queue import personlighedspsykologi_printout_matrix_qa as matrix_qa


def _orientation_points():
    return {
        "essence_context": {
            "placement": "indre og kontekstuel",
            "summary": "Teorien balancerer essens og kontekst.",
        },
        "determination": {
            "placement": "moderat determination",
            "summary": "Mennesket er bestemt af sociale og psykiske vilkaar.",
        },
        "agency": {
            "placement": "situeret agency",
            "summary": "Agency viser hvordan personen handler aktivt.",
        },
        "historicity": {
            "placement": "ontogenetisk historicitet",
            "summary": "Historien og livsforloebet former personligheden.",
        },
    }


def _row(theory_id="narrative_theory", lecture_keys=None, **overrides):
    row = {
        "theory_id": theory_id,
        "label": "Narrativ teori",
        "aliases": ["narrativ psykologi"],
        "lecture_keys": lecture_keys or ["W11L2"],
        "course_role": "Exam-relevant narrative tradition.",
        "course_summary": "Narrative accounts explain identity through stories.",
        "main_thinkers": ["Bruner"],
        "central_concepts": ["selvfortaelling", "narrativ identitet"],
        "orientation_points": _orientation_points(),
        "comparison_targets": [
            {
                "target_theory_id": "psychoanalysis",
                "rationale": "Kontrast mellem fortaelling og ubevidst konflikt.",
            }
        ],
        "likely_misunderstandings": [
            "At narrativ teori bare er fri fantasi uden social kontekst.",
        ],
        "source_grounding": {
            "concept_node_ids": ["narrative_identity"],
        },
    }
    row.update(overrides)
    return row


def _matrix(rows=None):
    return {
        "artifact_type": "exam_theory_matrix",
        "schema_version": 1,
        "subject_slug": "personlighedspsykologi",
        "rows": rows or [_row()],
    }


def _artifact(text, lecture_key="W11L2", source_id="source-1"):
    return {
        "artifact_type": "reading_printouts",
        "schema_version": 3,
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": "Test source",
        },
        "printouts": {
            "reading_guide": {
                "why_this_matters": text,
                "route": [{"task": text}],
            },
            "exam_bridge": {
                "use_this_text_for": [text],
                "course_connections": [text],
                "exam_moves": [text],
                "comparison_targets": [text],
                "misunderstanding_traps": [text],
                "mini_exam_prompt_question": "Redegoer for narrativ teori og diskuter agency.",
                "mini_exam_answer_plan_slots": [text],
            },
        },
    }


def test_w12_relevant_rows_include_comparison_targets():
    matrix = _matrix(
        rows=[
            _row("comparison_overview", ["W12L1"], comparison_targets=[{"target_theory_id": "psychoanalysis"}]),
            _row("psychoanalysis", ["W04L1"], label="Psykoanalyse", comparison_targets=[]),
        ]
    )

    row_ids = {row["theory_id"] for row in matrix_qa.relevant_matrix_rows(matrix, "W12L1")}

    assert row_ids == {"comparison_overview", "psychoanalysis"}


def test_evaluate_printout_artifact_returns_pass_report(tmp_path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text("{}", encoding="utf-8")
    text = (
        "Narrativ teori hos Bruner forklarer narrativ identitet og selvfortaelling. "
        "Essens og kontekst balanceres, determination er moderat, agency er situeret, "
        "og historicitet viser livsforloeb. Til eksamen kan den sammenlignes med "
        "psykoanalyse og ubevidst konflikt. En faldgrube er at tro, at narrativ teori "
        "bare er fri fantasi uden social kontekst."
    )

    report = matrix_qa.evaluate_printout_artifact(
        artifact=_artifact(text),
        artifact_path=tmp_path / "reading-printouts.json",
        matrix=_matrix(),
        matrix_path=matrix_path,
        repo_root=tmp_path,
        generated_at="2026-05-25T00:00:00Z",
    )

    assert report["artifact_type"] == "printout_matrix_qa_report"
    assert report["status"] == "pass"
    assert report["dimensions"]["source_grounding_discipline"]["score"] == 100
    assert report["matrix"]["row_ids"] == ["narrative_theory"]


def test_source_grounding_dimension_fails_on_student_synthesis_leak(tmp_path):
    report = matrix_qa.evaluate_printout_artifact(
        artifact=_artifact("Denne opgave bygger paa Anes tabel og student_synthesis."),
        artifact_path=tmp_path / "reading-printouts.json",
        matrix=_matrix(),
        repo_root=tmp_path,
    )

    dimension = report["dimensions"]["source_grounding_discipline"]
    assert dimension["status"] == "fail"
    assert dimension["score"] == 0


def test_summary_report_lists_lowest_scoring_sources():
    reports = [
        {
            "source": {"source_id": "high", "lecture_key": "W11L2"},
            "overall_score": 90,
            "status": "pass",
        },
        {
            "source": {"source_id": "low", "lecture_key": "W01L1"},
            "overall_score": 45,
            "status": "fail",
        },
    ]

    summary = matrix_qa.build_summary_report(reports, generated_at="2026-05-25T00:00:00Z")

    assert summary["status"] == "failed"
    assert summary["average_score"] == 68
    assert summary["lowest_scoring_sources"][0]["source_id"] == "low"


def test_write_report_bundle_writes_json_and_markdown(tmp_path):
    report = matrix_qa.evaluate_printout_artifact(
        artifact=_artifact("Narrativ teori Bruner agency historicitet determination essens kontekst eksamen."),
        artifact_path=tmp_path / "reading-printouts.json",
        matrix=_matrix(),
        repo_root=tmp_path,
    )

    summary = matrix_qa.write_report_bundle(tmp_path / "reports", [report], repo_root=tmp_path)

    assert summary["source_count"] == 1
    assert (tmp_path / "reports" / "source-1.json").exists()
    assert (tmp_path / "reports" / "source-1.md").exists()
    assert (tmp_path / "reports" / "summary.json").exists()


def test_cli_fail_below_exits_nonzero_for_low_score(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    matrix_path = tmp_path / "matrix.json"
    output_root = tmp_path / "output"
    artifact_path = output_root / "printout-json" / "source-1" / "reading-printouts.json"
    matrix_path.write_text(json.dumps(_matrix()), encoding="utf-8")
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(json.dumps(_artifact("Narrativ teori.", source_id="source-1")), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "evaluate_personlighedspsykologi_printout_matrix_qa.py"),
            "--repo-root",
            str(tmp_path),
            "--matrix",
            str(matrix_path),
            "--output-root",
            str(output_root),
            "--all-canonical",
            "--dry-run",
            "--fail-below",
            "95",
        ],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["source_count"] == 1
    assert payload["lowest_scoring_sources"][0]["source_id"] == "source-1"
