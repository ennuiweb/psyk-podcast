import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_semantic_artifacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_semantic_artifacts",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_semantic_artifacts_generates_glossary_theory_map_and_staleness(tmp_path):
    mod = _load_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    source_catalog_path = repo_root / "source_catalog.json"
    source_catalog_path.write_text(
        json.dumps(
            {
                "subject_slug": "personlighedspsykologi",
                "lectures": [{"lecture_key": "W01L1"}],
                "sources": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

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
                "lecture_title": "Phenomenology lecture",
                "lecture_summary": {
                    "summary_lines": [
                        "Phenomenology treats personality through lived experience and meaning."
                    ],
                    "key_points": ["The first-person perspective matters."],
                },
                "source_intelligence": {
                    "likely_core_sources": ["source-1"],
                },
                "sources": {
                    "readings": [
                        {
                            "source_id": "source-1",
                            "title": "Phenomenology article",
                            "priority_band": "core",
                            "evidence_origin": "reading_grounded",
                            "summary": {
                                "summary_lines": ["Lived experience is central."],
                                "key_points": ["Meaning is practical."],
                            },
                        }
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

    seed_path = repo_root / "source_intelligence_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "terms": [
                    {
                        "term_id": "phenomenology",
                        "label": "phenomenology",
                        "category": "tradition",
                        "importance": 3,
                        "aliases": ["phenomenology", "first-person perspective"],
                        "lecture_keys": ["W01L1"],
                        "definition": "Phenomenology centres lived experience.",
                        "course_role": "Introduces first-person analysis.",
                        "linked_terms": [],
                        "linked_theories": ["phenomenological_psychology"],
                    }
                ],
                "theories": [
                    {
                        "theory_id": "phenomenological_psychology",
                        "label": "phenomenological psychology",
                        "importance": 2,
                        "aliases": ["phenomenology"],
                        "lecture_keys": ["W01L1"],
                        "summary": "Phenomenological psychology privileges experience.",
                        "course_role": "Starts the experiential block.",
                        "core_term_ids": ["phenomenology"],
                        "related_theories": [],
                    }
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    glossary_path = repo_root / "course_glossary.json"
    theory_map_path = repo_root / "course_theory_map.json"
    staleness_path = repo_root / "source_intelligence_staleness.json"

    outputs = mod.build_semantic_artifacts(
        repo_root=repo_root,
        source_catalog_path=source_catalog_path,
        lecture_bundle_dir=lecture_bundle_dir,
        seed_path=seed_path,
        glossary_path=glossary_path,
        theory_map_path=theory_map_path,
        staleness_path=staleness_path,
    )

    assert outputs["course_glossary"]["stats"]["term_count"] == 1
    term = outputs["course_glossary"]["terms"][0]
    assert term["term_id"] == "phenomenology"
    assert term["grounding_status"] == "grounded"
    assert term["matched_lecture_keys"] == ["W01L1"]
    assert term["core_source_ids"] == ["source-1"]
    assert term["source_evidence_origins"] == ["reading_grounded"]

    assert outputs["course_theory_map"]["stats"]["theory_count"] == 1
    theory = outputs["course_theory_map"]["theories"][0]
    assert theory["theory_id"] == "phenomenological_psychology"
    assert theory["grounding_status"] == "grounded"
    assert theory["core_terms"] == [{"term_id": "phenomenology", "label": "phenomenology"}]
    assert theory["representative_source_ids"] == ["source-1"]
    assert theory["representative_evidence_origins"] == ["reading_grounded"]

    staleness = json.loads(staleness_path.read_text(encoding="utf-8"))
    assert staleness["artifacts"]["course_glossary"]["path"] == "course_glossary.json"
    assert staleness["artifacts"]["course_theory_map"]["path"] == "course_theory_map.json"
    assert staleness["artifacts"]["lecture_bundles"]["count"] == 1
    assert staleness["derivations"][0]["artifact_path"] == "course_glossary.json"
