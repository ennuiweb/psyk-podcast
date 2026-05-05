import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_concept_graph.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_concept_graph",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_concept_graph_generates_nodes_edges_and_distinctions(tmp_path):
    mod = _load_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    glossary_path = repo_root / "course_glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "terms": [
                    {
                        "term_id": "term-a",
                        "label": "Term A",
                        "importance": 3,
                        "salience_score": 80,
                        "lecture_keys": ["W01L1"],
                        "linked_terms": ["term-b"],
                        "linked_theories": ["theory-a"],
                        "core_source_ids": ["source-1"],
                    },
                    {
                        "term_id": "term-b",
                        "label": "Term B",
                        "importance": 2,
                        "salience_score": 60,
                        "lecture_keys": ["W01L1"],
                        "linked_terms": [],
                        "linked_theories": ["theory-a"],
                        "core_source_ids": ["source-2"],
                    },
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
                        "label": "Theory A",
                        "importance": 2,
                        "salience_score": 70,
                        "lecture_keys": ["W01L1"],
                        "core_term_ids": ["term-a", "term-b"],
                    }
                ],
                "relations": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    weighting_path = repo_root / "source_weighting.json"
    weighting_path.write_text(
        json.dumps(
            {
                "sources": [
                    {"source_id": "source-1", "weight_score": 90, "evidence_origin": "textbook_framing"},
                    {"source_id": "source-2", "weight_score": 70, "evidence_origin": "lecture_framed"},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    seed_path = repo_root / "source_intelligence_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "distinctions": [
                    {
                        "distinction_id": "dist-a",
                        "label": "A vs B",
                        "importance": 2,
                        "lecture_keys": ["W01L1"],
                        "term_ids": ["term-a", "term-b"],
                        "summary": "A test distinction.",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    output_path = repo_root / "course_concept_graph.json"
    staleness_path = repo_root / "source_intelligence_staleness.json"
    payload = mod.build_concept_graph(
        repo_root=repo_root,
        glossary_path=glossary_path,
        theory_map_path=theory_map_path,
        weighting_path=weighting_path,
        seed_path=seed_path,
        output_path=output_path,
        staleness_path=staleness_path,
    )

    assert payload["stats"]["node_count"] == 3
    assert payload["stats"]["distinction_count"] == 1
    edge_types = {edge["edge_type"] for edge in payload["edges"]}
    assert "term_link" in edge_types
    assert "term_to_theory" in edge_types
    assert "lecture_co_occurrence" in edge_types
    distinction = payload["distinctions"][0]
    assert distinction["distinction_id"] == "dist-a"
    assert distinction["supporting_source_ids"] == ["source-1", "source-2"]
    assert distinction["supporting_evidence_origins"] == ["textbook_framing", "lecture_framed"]

    staleness = json.loads(staleness_path.read_text(encoding="utf-8"))
    assert staleness["artifacts"]["course_concept_graph"]["path"] == "course_concept_graph.json"
