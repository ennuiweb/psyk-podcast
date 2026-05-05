import json
from pathlib import Path

import pytest

from notebooklm_queue import personlighedspsykologi_recursive as recursive


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fake_json_generator(*, system_instruction, user_prompt, source_paths, max_output_tokens):
    lowered = system_instruction.lower()
    if "structured source card" in lowered:
        assert source_paths
        return {
            "analysis": {
                "central_claims": [{"claim": "The source frames lived experience as central."}],
                "key_concepts": [{"term": "lived experience", "role": "anchor concept"}],
                "distinctions": [{"label": "experience vs explanation"}],
                "theory_role": "Phenomenological framing.",
                "source_role": "Anchor reading.",
                "relation_to_lecture": "Supports the lecture problem.",
                "likely_misunderstandings": ["Treating phenomenology as method-free introspection."],
                "quote_targets": [],
                "grounding_notes": ["Source-grounded reading card."],
                "warnings": [],
            }
        }
    if "lecture-level" in lowered:
        assert any(path.name == "source.pdf" for path in source_paths)
        return {
            "analysis": {
                "lecture_question": "How does phenomenology reframe personality?",
                "central_learning_problem": "The lecture asks how personality can be understood from lived experience.",
                "source_roles": [{"source_id": "source-1", "role": "anchor"}],
                "source_relations": [{"relation": "The reading grounds the slide framing."}],
                "core_concepts": [{"concept": "lived experience"}],
                "core_tensions": [{"tension": "description vs explanation"}],
                "likely_misunderstandings": ["Reducing the block to subjectivism."],
                "must_carry_ideas": ["Experience is structured, not merely private."],
                "missing_sources": [],
                "warnings": [],
            }
        }
    if "entire personality psychology course" in lowered:
        return {
            "analysis": {
                "course_arc": "The course moves from definitions to traditions and integrative critique.",
                "theory_tradition_map": [{"label": "phenomenology", "role": "experience tradition"}],
                "concept_map": [{"concept": "lived experience", "role": "connective concept"}],
                "distinction_map": [{"distinction": "description vs explanation"}],
                "sideways_relations": [{"from": "W01L1", "to": "W01L1", "relation": "self-link"}],
                "lecture_clusters": [{"label": "experience", "lecture_keys": ["W01L1"], "theme": "phenomenology"}],
                "top_down_priorities": [{"priority": "Keep the method question explicit.", "lecture_keys": ["W01L1"]}],
                "weak_spots": [],
                "podcast_generation_guidance": ["Keep substrate compact."],
            }
        }
    if "revising one lecture substrate" in lowered:
        return {
            "analysis": {
                "what_matters_more": ["Methodological stakes."],
                "de_emphasize": ["Biographical detail."],
                "strongest_sideways_connections": [{"target": "course method arc", "relation": "exemplifies"}],
                "top_down_course_relevance": "This lecture introduces experiential method stakes.",
                "revised_podcast_priorities": ["Explain the method stake before concepts."],
                "carry_forward": ["Description is not mere opinion."],
                "warnings": [],
            }
        }
    if "compact substrate" in lowered:
        return {
            "podcast": {
                "weekly": {
                    "angle": "Explain phenomenology as a disciplined change in viewpoint.",
                    "must_cover": ["Lived experience", "Description vs explanation"],
                    "avoid": ["Do not caricature it as vague introspection."],
                    "grounding": ["Anchor claims in source-1."],
                },
                "per_reading": [
                    {
                        "source_id": "source-1",
                        "angle": "Treat the reading as the conceptual anchor.",
                        "must_cover": ["Lived experience"],
                        "avoid": [],
                    }
                ],
                "per_slide": [],
                "short": {"angle": "One compact method-stakes episode.", "must_cover": ["Lived experience"], "avoid": []},
                "selected_concepts": [{"concept": "lived experience", "role": "anchor"}],
                "selected_tensions": [{"tension": "description vs explanation", "stakes": "method"}],
                "grounding_notes": ["Use substrate as prioritization, not replacement."],
                "source_selection": [{"source_id": "source-1", "priority": "anchor", "why": "central source"}],
            }
        }
    raise AssertionError(system_instruction)


def _minimal_course_fixture(tmp_path, *, lecture_keys=("W01L1",)):
    repo_root = tmp_path / "repo"
    subject_root = tmp_path / "subject"
    repo_root.mkdir()
    source_path = subject_root / "Readings" / "source.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"%PDF-1.4 source")

    source_catalog_path = repo_root / "source_catalog.json"
    policy_path = repo_root / "source_intelligence_policy.json"
    lecture_bundle_dir = repo_root / "lecture_bundles"
    recursive_dir = repo_root / "source_intelligence"
    source = {
        "source_id": "source-1",
        "lecture_key": "W01L1",
        "title": "Phenomenology source",
        "source_family": "reading",
        "evidence_origin": "reading_grounded",
        "source_exists": True,
        "subject_relative_path": "Readings/source.pdf",
        "length_band": "medium",
        "file": {
            "sha256": recursive.sha256_file(source_path),
            "page_count": 1,
            "estimated_token_count": 100,
            "text_extraction_status": "ok",
        },
    }
    _write_json(
        source_catalog_path,
        {
            "lectures": [
                {
                    "lecture_key": lecture_key,
                    "lecture_title": "Phenomenology" if lecture_key == "W01L1" else lecture_key,
                }
                for lecture_key in lecture_keys
            ],
            "sources": [source],
        },
    )
    _write_json(policy_path, {"version": 1})
    _write_json(
        lecture_bundle_dir / "W01L1.json",
        {
            "lecture_key": "W01L1",
            "lecture_title": "Phenomenology",
            "sequence_index": 1,
            "sources": {"readings": [source], "lecture_slides": [], "seminar_slides": [], "exercise_slides": []},
        },
    )
    return {
        "repo_root": repo_root,
        "subject_root": subject_root,
        "source_catalog_path": source_catalog_path,
        "policy_path": policy_path,
        "lecture_bundle_dir": lecture_bundle_dir,
        "recursive_dir": recursive_dir,
        "source_path": source_path,
        "source": source,
    }


def test_recursive_builders_create_valid_artifacts_and_index(tmp_path):
    fixture = _minimal_course_fixture(tmp_path)
    repo_root = fixture["repo_root"]
    subject_root = fixture["subject_root"]
    source_catalog_path = fixture["source_catalog_path"]
    policy_path = fixture["policy_path"]
    lecture_bundle_dir = fixture["lecture_bundle_dir"]
    recursive_dir = fixture["recursive_dir"]

    source_result = recursive.build_source_cards(
        repo_root=repo_root,
        subject_root=subject_root,
        source_catalog_path=source_catalog_path,
        policy_path=policy_path,
        source_card_dir=recursive_dir / "source_cards",
        lecture_keys=["W01L1"],
        json_generator=_fake_json_generator,
        skip_existing=True,
    )
    assert source_result["written_count"] == 1

    lecture_result = recursive.build_lecture_substrates(
        repo_root=repo_root,
        subject_root=subject_root,
        lecture_keys=["W01L1"],
        lecture_bundle_dir=lecture_bundle_dir,
        source_card_dir=recursive_dir / "source_cards",
        lecture_substrate_dir=recursive_dir / "lecture_substrates",
        source_catalog_path=source_catalog_path,
        json_generator=_fake_json_generator,
    )
    assert lecture_result["written_count"] == 1

    course_result = recursive.build_course_synthesis(
        repo_root=repo_root,
        lecture_keys=["W01L1"],
        lecture_substrate_dir=recursive_dir / "lecture_substrates",
        output_path=recursive_dir / "course_synthesis.json",
        source_catalog_path=source_catalog_path,
        json_generator=_fake_json_generator,
        partial_scope=False,
    )
    assert course_result["status"] == "written"

    revised_result = recursive.build_revised_lecture_substrates(
        lecture_keys=["W01L1"],
        lecture_substrate_dir=recursive_dir / "lecture_substrates",
        course_synthesis_path=recursive_dir / "course_synthesis.json",
        revised_lecture_substrate_dir=recursive_dir / "revised_lecture_substrates",
        json_generator=_fake_json_generator,
    )
    assert revised_result["written_count"] == 1

    podcast_result = recursive.build_podcast_substrates(
        lecture_keys=["W01L1"],
        source_card_dir=recursive_dir / "source_cards",
        lecture_bundle_dir=lecture_bundle_dir,
        revised_lecture_substrate_dir=recursive_dir / "revised_lecture_substrates",
        course_synthesis_path=recursive_dir / "course_synthesis.json",
        podcast_substrate_dir=recursive_dir / "podcast_substrates",
        source_weighting_path=repo_root / "source_weighting.json",
        json_generator=_fake_json_generator,
    )
    assert podcast_result["written_count"] == 1

    index = recursive.build_recursive_index(
        repo_root=repo_root,
        source_catalog_path=source_catalog_path,
        recursive_dir=recursive_dir,
        output_path=recursive_dir / "index.json",
    )
    assert index["complete"]["source_cards"]
    assert index["complete"]["lecture_substrates"]
    assert index["complete"]["course_synthesis"]
    assert index["complete"]["revised_lecture_substrates"]
    assert index["complete"]["podcast_substrates"]
    assert index["errors"] == []
    assert index["fresh"]["stale_artifacts"] == []

    stored_index = recursive.load_json(recursive_dir / "index.json")
    stored_index["generated_at"] = "2000-01-01T00:00:00Z"
    _write_json(recursive_dir / "index.json", stored_index)
    rebuilt_index = recursive.build_recursive_index(
        repo_root=repo_root,
        source_catalog_path=source_catalog_path,
        recursive_dir=recursive_dir,
        output_path=recursive_dir / "index.json",
    )
    assert rebuilt_index["generated_at"] == "2000-01-01T00:00:00Z"


def test_course_synthesis_requires_all_selected_lecture_substrates(tmp_path):
    fixture = _minimal_course_fixture(tmp_path, lecture_keys=("W01L1", "W02L1"))
    recursive.build_source_cards(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        source_catalog_path=fixture["source_catalog_path"],
        policy_path=fixture["policy_path"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_keys=["W01L1"],
        json_generator=_fake_json_generator,
        skip_existing=True,
    )
    recursive.build_lecture_substrates(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        lecture_keys=["W01L1"],
        lecture_bundle_dir=fixture["lecture_bundle_dir"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_substrate_dir=fixture["recursive_dir"] / "lecture_substrates",
        source_catalog_path=fixture["source_catalog_path"],
        json_generator=_fake_json_generator,
    )

    with pytest.raises(RuntimeError, match="missing lecture substrates.*W02L1"):
        recursive.build_course_synthesis(
            repo_root=fixture["repo_root"],
            lecture_keys=["W01L1", "W02L1"],
            lecture_substrate_dir=fixture["recursive_dir"] / "lecture_substrates",
            output_path=fixture["recursive_dir"] / "course_synthesis.json",
            source_catalog_path=fixture["source_catalog_path"],
            json_generator=_fake_json_generator,
            partial_scope=True,
        )


def test_source_cards_continue_on_error_records_missing_local_file(tmp_path):
    fixture = _minimal_course_fixture(tmp_path)
    catalog = recursive.load_json(fixture["source_catalog_path"])
    missing_source = dict(fixture["source"])
    missing_source["source_id"] = "missing-source"
    missing_source["subject_relative_path"] = "Readings/missing.pdf"
    catalog["sources"].append(missing_source)
    _write_json(fixture["source_catalog_path"], catalog)

    result = recursive.build_source_cards(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        source_catalog_path=fixture["source_catalog_path"],
        policy_path=fixture["policy_path"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_keys=["W01L1"],
        json_generator=_fake_json_generator,
        continue_on_error=True,
    )

    assert result["written_count"] == 1
    assert result["error_count"] == 1
    missing = [item for item in result["results"] if item["source_id"] == "missing-source"][0]
    assert missing["status"] == "missing_local_file"
    assert "missing.pdf" in missing["error"]


def test_lecture_substrates_continue_on_error_records_missing_bundle(tmp_path):
    fixture = _minimal_course_fixture(tmp_path)
    recursive.build_source_cards(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        source_catalog_path=fixture["source_catalog_path"],
        policy_path=fixture["policy_path"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_keys=["W01L1"],
        json_generator=_fake_json_generator,
    )

    result = recursive.build_lecture_substrates(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        lecture_keys=["W01L1", "W02L1"],
        lecture_bundle_dir=fixture["lecture_bundle_dir"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_substrate_dir=fixture["recursive_dir"] / "lecture_substrates",
        source_catalog_path=fixture["source_catalog_path"],
        json_generator=_fake_json_generator,
        continue_on_error=True,
    )

    assert result["written_count"] == 1
    assert result["error_count"] == 1
    missing = [item for item in result["results"] if item["lecture_key"] == "W02L1"][0]
    assert missing["status"] == "error"
    assert "lecture bundle not found" in missing["error"]


def test_recursive_index_reports_stale_policy_and_missing_bundle_without_crashing(tmp_path):
    fixture = _minimal_course_fixture(tmp_path)
    recursive.build_source_cards(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        source_catalog_path=fixture["source_catalog_path"],
        policy_path=fixture["policy_path"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_keys=["W01L1"],
        json_generator=_fake_json_generator,
        skip_existing=True,
    )
    recursive.build_lecture_substrates(
        repo_root=fixture["repo_root"],
        subject_root=fixture["subject_root"],
        lecture_keys=["W01L1"],
        lecture_bundle_dir=fixture["lecture_bundle_dir"],
        source_card_dir=fixture["recursive_dir"] / "source_cards",
        lecture_substrate_dir=fixture["recursive_dir"] / "lecture_substrates",
        source_catalog_path=fixture["source_catalog_path"],
        json_generator=_fake_json_generator,
    )
    _write_json(fixture["policy_path"], {"version": 2})
    (fixture["lecture_bundle_dir"] / "W01L1.json").unlink()

    index = recursive.build_recursive_index(
        repo_root=fixture["repo_root"],
        source_catalog_path=fixture["source_catalog_path"],
        recursive_dir=fixture["recursive_dir"],
        output_path=fixture["recursive_dir"] / "index.json",
    )
    stale = "\n".join(index["fresh"]["stale_artifacts"])
    assert "source_intelligence_policy" in stale
    assert "lecture_bundle_missing" in stale
