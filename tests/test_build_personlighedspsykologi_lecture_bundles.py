import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_lecture_bundles.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_lecture_bundles",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_lecture_bundles_enriches_sources_and_indexes_outputs(tmp_path):
    mod = _load_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subject_root = tmp_path / "Personlighedspsykologi"
    week_dir = subject_root / "Readings" / "W01L1 Intro"
    week_dir.mkdir(parents=True)
    (week_dir / "Alpha.analysis.md").write_text("alpha analysis", encoding="utf-8")
    (week_dir / "week.analysis.md").write_text("week analysis", encoding="utf-8")

    source_catalog_path = repo_root / "source_catalog.json"
    source_catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "subject_slug": "personlighedspsykologi",
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "sequence_index": 1,
                        "lecture_title": "Intro",
                        "week_prompt_analysis_present": True,
                        "week_prompt_analysis_sidecars": ["Readings/W01L1 Intro/week.analysis.md"],
                    },
                    {
                        "lecture_key": "W02L1",
                        "sequence_index": 2,
                        "lecture_title": "Next lecture",
                        "week_prompt_analysis_present": False,
                        "week_prompt_analysis_sidecars": [],
                    },
                ],
                "sources": [
                    {
                        "source_id": "reading-alpha",
                        "title": "Alpha",
                        "source_kind": "reading",
                        "source_family": "reading",
                        "source_filename": "Alpha.pdf",
                        "subject_relative_path": "Readings/W01L1 Intro/Alpha.pdf",
                        "source_exists": True,
                        "missing_reason": None,
                        "lecture_key": "W01L1",
                        "lecture_keys": ["W01L1"],
                        "sequence_index": 1,
                        "language_guess": "da",
                        "length_band": "long",
                        "priority_signals": {
                            "is_grundbog": True,
                            "has_manual_summary": True,
                            "has_prompt_analysis_sidecar": True,
                            "lecture_has_week_analysis_sidecar": True,
                        },
                        "evidence_origin": "textbook_framing",
                        "file": {
                            "page_count": 10,
                            "estimated_token_count": 7200,
                            "estimated_word_count": 4800,
                            "text_char_count": 23000,
                            "text_extraction_status": "ok",
                            "sha256": "abc",
                            "size_bytes": 1000,
                        },
                        "prompt_analysis_sidecars": ["Readings/W01L1 Intro/Alpha.analysis.md"],
                    },
                    {
                        "source_id": "reading-missing",
                        "title": "Missing reading",
                        "source_kind": "reading",
                        "source_family": "reading",
                        "source_filename": None,
                        "subject_relative_path": None,
                        "source_exists": False,
                        "missing_reason": "manifest_marked_missing",
                        "lecture_key": "W01L1",
                        "lecture_keys": ["W01L1"],
                        "sequence_index": 2,
                        "language_guess": "unknown",
                        "length_band": "unknown",
                        "priority_signals": {
                            "is_grundbog": False,
                            "has_manual_summary": False,
                            "has_prompt_analysis_sidecar": False,
                            "lecture_has_week_analysis_sidecar": True,
                        },
                        "evidence_origin": "reading_grounded",
                        "file": {
                            "page_count": 0,
                            "estimated_token_count": 0,
                            "estimated_word_count": 0,
                            "text_char_count": 0,
                            "text_extraction_status": "missing_source",
                            "sha256": None,
                            "size_bytes": 0,
                        },
                        "prompt_analysis_sidecars": [],
                    },
                    {
                        "source_id": "slide-lecture-1",
                        "title": "Lecture slides",
                        "source_kind": "slide",
                        "source_family": "lecture_slide",
                        "source_filename": "Lecture slides.pdf",
                        "subject_relative_path": "Forelæsningsrækken/Lecture slides.pdf",
                        "source_exists": True,
                        "missing_reason": None,
                        "lecture_key": "W01L1",
                        "lecture_keys": ["W01L1"],
                        "sequence_index": 3,
                        "language_guess": "da",
                        "length_band": "medium",
                        "slide_subcategory": "lecture",
                        "priority_signals": {
                            "is_grundbog": False,
                            "has_manual_summary": False,
                            "has_prompt_analysis_sidecar": False,
                            "lecture_has_week_analysis_sidecar": False,
                        },
                        "evidence_origin": "lecture_framed",
                        "file": {
                            "page_count": 4,
                            "estimated_token_count": 1200,
                            "estimated_word_count": 800,
                            "text_char_count": 4000,
                            "text_extraction_status": "ok",
                            "sha256": "def",
                            "size_bytes": 500,
                        },
                        "prompt_analysis_sidecars": [],
                    },
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    content_manifest_path = repo_root / "content_manifest.json"
    content_manifest_path.write_text(
        json.dumps(
            {
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "lecture_title": "Intro",
                        "sequence_index": 1,
                        "summary": {
                            "summary_lines": ["lecture summary"],
                            "key_points": ["lecture point"],
                        },
                        "warnings": ["watch wording"],
                        "readings": [
                            {
                                "reading_key": "reading-alpha",
                                "summary": {
                                    "summary_lines": ["alpha summary"],
                                    "key_points": ["alpha point"],
                                },
                            },
                            {
                                "reading_key": "reading-missing",
                                "summary": {},
                            },
                        ],
                    },
                    {
                        "lecture_key": "W02L1",
                        "lecture_title": "Next lecture",
                        "sequence_index": 2,
                        "summary": {},
                        "warnings": [],
                        "readings": [],
                    },
                ]
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output_dir = repo_root / "lecture_bundles"
    index_payload = mod.build_lecture_bundles(
        repo_root=repo_root,
        subject_root=subject_root,
        source_catalog_path=source_catalog_path,
        content_manifest_path=content_manifest_path,
        output_dir=output_dir,
    )

    assert index_payload["stats"]["lecture_count"] == 2
    assert index_payload["stats"]["ready_bundle_count"] == 0
    assert index_payload["stats"]["partial_bundle_count"] == 2
    assert index_payload["stats"]["bundle_with_week_analysis_count"] == 1
    assert index_payload["stats"]["bundle_with_missing_sources_count"] == 1

    bundle = json.loads((output_dir / "W01L1.json").read_text(encoding="utf-8"))
    assert bundle["bundle_status"] == "partial"
    assert bundle["readiness_issues"] == [
        "missing_sources",
        "incomplete_reading_summary_coverage",
    ]
    assert bundle["course_position"]["next_lecture_key"] == "W02L1"
    assert bundle["lecture_summary"]["present"] is True
    assert bundle["source_counts"]["readings"] == 2
    assert bundle["source_counts"]["lecture_slides"] == 1
    assert bundle["source_counts"]["missing_sources"] == 1
    assert bundle["source_counts"]["manual_reading_summaries_present"] == 1
    assert bundle["source_counts"]["source_analyses_present"] == 1
    assert bundle["source_counts"]["total_estimated_tokens"] == 8400
    assert bundle["source_intelligence"]["dominant_language"] == "da"
    assert bundle["source_intelligence"]["week_analysis"]["present"] is True
    assert bundle["source_intelligence"]["week_analysis"]["sidecars"][0]["content"] == "week analysis"
    assert bundle["source_intelligence"]["likely_core_sources"] == ["reading-alpha"]
    assert bundle["source_intelligence"]["missing_sources"] == [
        {
            "source_id": "reading-missing",
            "title": "Missing reading",
            "source_kind": "reading",
            "missing_reason": "manifest_marked_missing",
        }
    ]
    assert bundle["manifest_warnings"] == ["watch wording"]

    reading = bundle["sources"]["readings"][0]
    assert reading["source_id"] == "reading-alpha"
    assert reading["priority_band"] == "core"
    assert "grundbog" in reading["priority_reasons"]
    assert reading["evidence_origin"] == "textbook_framing"
    assert reading["summary"]["summary_lines"] == ["alpha summary"]
    assert reading["analysis"]["present"] is True
    assert reading["analysis"]["sidecars"][0]["content"] == "alpha analysis"

    second_bundle = json.loads((output_dir / "W02L1.json").read_text(encoding="utf-8"))
    assert second_bundle["bundle_status"] == "partial"
    assert second_bundle["readiness_issues"] == [
        "missing_lecture_summary",
        "no_readings",
    ]
