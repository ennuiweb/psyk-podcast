from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_exam_priority_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_exam_priority_plan",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _base_config() -> dict:
    return {
        "schema_version": 1,
        "exam_context": {
            "topic": "narrative psychology",
            "already_covered_lecture_keys": ["W11L2"],
            "available_reading_days": 12,
        },
        "score_weights": {
            "weight_band_bonus": {"anchor": 30, "major": 18, "supporting": 8, "contextual": 2},
            "theory_bonus": {
                "narrative_psychology": 48,
                "sociocultural_poststructural_approaches": 36,
                "critical_psychology": 30,
                "trait_and_assessment_psychology": 12,
            },
            "term_bonus": {
                "narrativity": 50,
                "subjectivation": 45,
                "personality_traits": 12,
            },
            "lecture_role_bonus": {"W10L2": 42, "W01L1": 16, "W11L2": 0},
            "distinction_bonus": {"essence_vs_subjectivation": 50, "trait_vs_state": 26},
            "lecture_distinction_context_multiplier": 4,
            "course_priority_bonus": 14,
            "sideways_relation_bonus": 8,
            "lecture_context_keyword_bonus": {
                "narrative psychology": 20,
                "subjectivation": 16,
                "historicity": 14,
                "agency": 10,
                "discourse": 10,
                "deconstruction": 10,
            },
            "lecture_context_bonus_cap": 52,
            "length_cost": {"long": 18, "medium": 8, "unknown": 6},
        },
        "bucket_rules": {
            "start_here_academic_threshold": 220,
            "read_after_academic_threshold": 150,
            "overview_academic_threshold": 120,
            "baseline_lecture_keys": ["W01L1"],
            "limits": {
                "start_here": 5,
                "read_after": 5,
                "expand_if_time": 5,
                "contrast_baseline": 5,
                "bridge_overview": 5,
                "already_covered": 5,
            },
            "max_per_lecture": {},
        },
        "outputs": {
            "plan_json": "plan.json",
            "markdown": "plan.md",
            "onepage_tex": "plan.tex",
            "onepage_pdf": "plan.pdf",
        },
    }


def test_plan_orders_visible_buckets_by_academic_priority(tmp_path: Path) -> None:
    mod = _load_module()
    repo_root = tmp_path / "repo"
    config_path = repo_root / "config.json"
    weighting_path = repo_root / "source_weighting.json"
    graph_path = repo_root / "course_concept_graph.json"
    synthesis_path = repo_root / "course_synthesis.json"
    substrates_dir = repo_root / "revised"

    _write_json(config_path, _base_config())
    _write_json(
        weighting_path,
        {
            "sources": [
                {
                    "source_id": "w10l2-foucault-test",
                    "lecture_key": "W10L2",
                    "lecture_title": "Poststructuralism",
                    "title": "Foucault",
                    "source_family": "reading",
                    "weight_score": 100,
                    "weight_band": "anchor",
                    "priority_band": "core",
                    "length_band": "long",
                    "term_ids": ["subjectivation"],
                    "theory_ids": ["sociocultural_poststructural_approaches", "critical_psychology"],
                },
                {
                    "source_id": "w01l1-baseline-test",
                    "lecture_key": "W01L1",
                    "lecture_title": "Intro",
                    "title": "Trait baseline",
                    "source_family": "reading",
                    "weight_score": 105,
                    "weight_band": "anchor",
                    "priority_band": "core",
                    "length_band": "medium",
                    "term_ids": ["personality_traits"],
                    "theory_ids": ["trait_and_assessment_psychology"],
                },
                {
                    "source_id": "w11l2-narrative-test",
                    "lecture_key": "W11L2",
                    "lecture_title": "Narrative",
                    "title": "Narrative anchor",
                    "source_family": "reading",
                    "weight_score": 110,
                    "weight_band": "anchor",
                    "priority_band": "core",
                    "length_band": "medium",
                    "term_ids": ["narrativity"],
                    "theory_ids": ["narrative_psychology"],
                },
            ]
        },
    )
    _write_json(
        graph_path,
        {
            "distinctions": [
                {
                    "distinction_id": "essence_vs_subjectivation",
                    "label": "inner essence vs subjectivation",
                    "importance": 3,
                    "lecture_keys": ["W10L2", "W11L2"],
                    "supporting_source_ids": ["w10l2-foucault-test", "w11l2-narrative-test"],
                },
                {
                    "distinction_id": "trait_vs_state",
                    "label": "trait vs state",
                    "importance": 3,
                    "lecture_keys": ["W01L1", "W11L2"],
                    "supporting_source_ids": ["w01l1-baseline-test", "w11l2-narrative-test"],
                },
            ]
        },
    )
    _write_json(
        synthesis_path,
        {
            "analysis": {
                "top_down_priorities": [{"lecture_keys": ["W10L2", "W01L1"]}],
                "sideways_relations": [{"from": "W10L2", "to": "W11L2"}],
            }
        },
    )
    _write_json(
        substrates_dir / "W10L2.json",
        {
            "analysis": {
                "top_down_course_relevance": (
                    "narrative psychology subjectivation historicity agency discourse deconstruction"
                )
            }
        },
    )
    plan = mod.build_exam_priority_plan(
        repo_root=repo_root,
        config_path=config_path,
        source_weighting_path=weighting_path,
        concept_graph_path=graph_path,
        course_synthesis_path=synthesis_path,
        lecture_substrates_dir=substrates_dir,
        generated_at="2026-05-12T00:00:00Z",
    )

    by_id = {record["source_id"]: record for record in plan["records"]}
    assert by_id["w10l2-foucault-test"]["academic_score"] > by_id["w01l1-baseline-test"]["academic_score"]
    assert by_id["w10l2-foucault-test"]["bucket"] == "start_here"
    assert by_id["w01l1-baseline-test"]["bucket"] == "contrast_baseline"
    assert by_id["w11l2-narrative-test"]["bucket"] == "already_covered"
    assert plan["start_here_source_ids"] == ["w10l2-foucault-test"]


def test_rendered_markdown_documents_the_two_score_boundary(tmp_path: Path) -> None:
    mod = _load_module()
    plan = {
        "exam_context": {"available_reading_days": 12},
        "config_path": "config.json",
        "inputs": {
            "source_weighting": "source_weighting.json",
            "course_concept_graph": "course_concept_graph.json",
            "course_synthesis": "course_synthesis.json",
            "revised_lecture_substrates_dir": "revised",
        },
        "bucket_records": {
            "start_here": [],
            "read_after": [],
            "expand_if_time": [],
            "contrast_baseline": [],
            "bridge_overview": [],
            "already_covered": [],
        },
        "start_here_source_ids": [],
    }

    markdown = mod.render_markdown(plan)

    assert "Den synlige plan bruger derfor faglig prioritet" in markdown
    assert "`academic_score`" in markdown
    assert "printout-status:" not in markdown


def test_compile_pdf_moves_rendered_pdf_to_configured_output_path(tmp_path: Path, monkeypatch) -> None:
    mod = _load_module()
    tex_path = tmp_path / "docs" / "plan.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(r"\documentclass{article}\begin{document}ok\end{document}", encoding="utf-8")
    pdf_path = tmp_path / "exports" / "final-plan.pdf"

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/xelatex" if name == "xelatex" else None)

    def fake_run(command, *, cwd, check, stdout, stderr, text):
        del command, check, stdout, stderr, text
        build_dir = Path(cwd)
        (build_dir / "plan.pdf").write_bytes(b"%PDF-1.4 new")
        (build_dir / "plan.aux").write_text("aux", encoding="utf-8")
        (build_dir / "plan.log").write_text("log", encoding="utf-8")
        (build_dir / "plan.out").write_text("out", encoding="utf-8")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    changed = mod.compile_pdf(tex_path, pdf_path)

    assert changed is True
    assert pdf_path.read_bytes() == b"%PDF-1.4 new"
    assert not tex_path.with_suffix(".pdf").exists()
    assert not tex_path.with_suffix(".aux").exists()
    assert not tex_path.with_suffix(".log").exists()
    assert not tex_path.with_suffix(".out").exists()


def test_main_uses_configured_pdf_output_path_and_reports_it(tmp_path: Path, monkeypatch, capsys) -> None:
    mod = _load_module()
    repo_root = tmp_path / "repo"
    config_path = repo_root / "config.json"
    weighting_path = repo_root / "source_weighting.json"
    graph_path = repo_root / "course_concept_graph.json"
    synthesis_path = repo_root / "course_synthesis.json"
    substrates_dir = repo_root / "revised"

    config = _base_config()
    config["outputs"] = {
        "plan_json": "generated/plan.json",
        "markdown": "generated/plan.md",
        "onepage_tex": "generated/tex/plan-source.tex",
        "onepage_pdf": "public/plan-final.pdf",
    }
    _write_json(config_path, config)
    _write_json(
        weighting_path,
        {
            "sources": [
                {
                    "source_id": "w10l2-foucault-test",
                    "lecture_key": "W10L2",
                    "lecture_title": "Poststructuralism",
                    "title": "Foucault",
                    "source_family": "reading",
                    "weight_score": 100,
                    "weight_band": "anchor",
                    "priority_band": "core",
                    "length_band": "long",
                    "term_ids": ["subjectivation"],
                    "theory_ids": ["sociocultural_poststructural_approaches"],
                }
            ]
        },
    )
    _write_json(graph_path, {"distinctions": []})
    _write_json(synthesis_path, {"analysis": {"top_down_priorities": [], "sideways_relations": []}})

    compile_calls: list[tuple[Path, Path]] = []

    def fake_compile(tex_path: Path, pdf_path: Path) -> bool:
        compile_calls.append((tex_path, pdf_path))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        return False

    monkeypatch.setattr(mod, "compile_pdf", fake_compile)
    monkeypatch.setattr(
        mod,
        "_parse_args",
        lambda: argparse.Namespace(
            repo_root=str(repo_root),
            config=str(config_path),
            source_weighting=str(weighting_path),
            concept_graph=str(graph_path),
            course_synthesis=str(synthesis_path),
            lecture_substrates_dir=str(substrates_dir),
            generated_at="2026-05-12T00:00:00Z",
            no_pdf=False,
        ),
    )

    exit_code = mod.main()
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert compile_calls == [
        (
            repo_root / "generated/tex/plan-source.tex",
            repo_root / "public/plan-final.pdf",
        )
    ]
    assert result["onepage_pdf"] == "public/plan-final.pdf"
    assert result["changed"]["onepage_pdf"] is False
