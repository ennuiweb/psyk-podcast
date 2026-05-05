import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_source_weighting.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_source_weighting",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_source_weighting_scores_core_sources_above_missing_ones(tmp_path):
    mod = _load_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    lecture_bundle_dir = repo_root / "lecture_bundles"
    lecture_bundle_dir.mkdir()
    (lecture_bundle_dir / "index.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {
                        "lecture_key": "W01L1",
                        "relative_path": "W01L1.json",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (lecture_bundle_dir / "W01L1.json").write_text(
        json.dumps(
            {
                "lecture_key": "W01L1",
                "lecture_title": "Intro",
                "source_intelligence": {
                    "likely_core_sources": ["source-1"],
                    "week_analysis": {"present": True},
                },
                "sources": {
                    "readings": [
                        {
                            "source_id": "source-1",
                            "title": "Core reading",
                            "source_family": "reading",
                            "evidence_origin": "textbook_framing",
                            "source_exists": True,
                            "priority_band": "core",
                            "length_band": "long",
                            "summary": {"present": True},
                            "analysis": {"present": True},
                            "file": {"estimated_token_count": 12000},
                        },
                        {
                            "source_id": "source-2",
                            "title": "Missing reading",
                            "source_family": "reading",
                            "evidence_origin": "reading_grounded",
                            "source_exists": False,
                            "priority_band": "missing",
                            "length_band": "unknown",
                            "summary": {"present": False},
                            "analysis": {"present": False},
                            "file": {"estimated_token_count": 0},
                        },
                    ],
                    "lecture_slides": [],
                    "seminar_slides": [],
                    "exercise_slides": [],
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    glossary_path = repo_root / "course_glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "terms": [
                    {
                        "term_id": "term-a",
                        "linked_theories": ["theory-a"],
                        "source_ids": ["source-1"],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    theory_map_path = repo_root / "course_theory_map.json"
    theory_map_path.write_text(
        json.dumps(
            {
                "theories": [
                    {
                        "theory_id": "theory-a",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    output_path = repo_root / "source_weighting.json"
    staleness_path = repo_root / "source_intelligence_staleness.json"
    payload = mod.build_source_weighting(
        repo_root=repo_root,
        lecture_bundle_dir=lecture_bundle_dir,
        glossary_path=glossary_path,
        theory_map_path=theory_map_path,
        output_path=output_path,
        staleness_path=staleness_path,
    )

    assert payload["stats"]["source_count"] == 2
    ranked = payload["lectures"][0]["ranked_sources"]
    assert ranked[0]["source_id"] == "source-1"
    assert ranked[0]["weight_band"] == "anchor"
    assert ranked[0]["breakdown"]["family_base"] == 40
    assert ranked[0]["breakdown"]["likely_core_source"] == 10
    assert ranked[0]["breakdown"]["evidence_origin"] == 4
    assert ranked[0]["breakdown"]["theory_coverage"] == 4
    assert ranked[0]["evidence_origin"] == "textbook_framing"
    assert ranked[1]["source_id"] == "source-2"
    assert ranked[1]["weight_score"] == 0
    assert ranked[1]["weight_band"] == "missing"

    staleness = json.loads(staleness_path.read_text(encoding="utf-8"))
    assert staleness["artifacts"]["source_weighting"]["path"] == "source_weighting.json"
