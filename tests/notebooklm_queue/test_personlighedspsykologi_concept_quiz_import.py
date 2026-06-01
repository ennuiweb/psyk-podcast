from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import import_personlighedspsykologi_concept_quizzes as importer


def test_import_concept_quizzes_copies_json_and_updates_manifests(tmp_path: Path, monkeypatch) -> None:
    lab_manifest = tmp_path / "lab" / "manifest.json"
    output_root = tmp_path / "output"
    quiz_files_root = tmp_path / "freudd" / "quiz_files" / "personlighedspsykologi"
    concept_manifest = tmp_path / "show" / "concept_quiz_manifest.json"
    quiz_links = tmp_path / "show" / "quiz_links.json"
    source = output_root / "W90L1" / "W90L1 - Videnskabsteori {type=quiz quantity=more difficulty=medium download=json hash=abc}.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "title": "Videnskabsteori",
                "questions": [
                    {
                        "question": "Hvad handler ontologi om?",
                        "answerOptions": [
                            {"text": "Hvad noget er", "isCorrect": True},
                            {"text": "Hvor mange respondenter man har", "isCorrect": False},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    lab_manifest.parent.mkdir(parents=True)
    lab_manifest.write_text(
        json.dumps(
            {
                "packs": [
                    {
                        "lecture_key": "W90L1",
                        "slug": "videnskabsteori-orienteringspunkter",
                        "title": "Videnskabsteori og orienteringspunkter",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    quiz_links.parent.mkdir(parents=True)
    quiz_links.write_text(
        json.dumps(
            {
                "by_name": {
                    "Eksisterende quiz": {
                        "relative_path": "existing.html",
                        "difficulty": "medium",
                        "subject_slug": "personlighedspsykologi",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(importer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(importer, "LAB_MANIFEST_PATH", lab_manifest)
    monkeypatch.setattr(importer, "QUIZ_FILES_ROOT", quiz_files_root)
    monkeypatch.setattr(importer, "CONCEPT_MANIFEST_PATH", concept_manifest)
    monkeypatch.setattr(importer, "QUIZ_LINKS_PATH", quiz_links)

    result = importer.import_quizzes(output_root=output_root)

    assert result["imported"] == 1
    quiz_id = result["quiz_ids"][0]
    assert (quiz_files_root / f"{quiz_id}.json").exists()

    concept_payload = json.loads(concept_manifest.read_text(encoding="utf-8"))
    assert concept_payload["entries"][0]["quiz_id"] == quiz_id
    assert concept_payload["entries"][0]["question_count"] == 1
    assert concept_payload["entries"][0]["difficulty_label"] == "Normal"

    links_payload = json.loads(quiz_links.read_text(encoding="utf-8"))
    assert links_payload["by_name"]["Eksisterende quiz"]["relative_path"] == "existing.html"
    link = links_payload["by_name"]["Videnskabsteori og orienteringspunkter"]
    assert link["relative_path"] == f"{quiz_id}.html"
    assert link["subject_slug"] == "personlighedspsykologi"


def test_import_concept_quizzes_accepts_external_output_root(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    external_output = tmp_path / "external-output"
    lab_manifest = repo_root / "lab" / "manifest.json"
    quiz_files_root = repo_root / "freudd" / "quiz_files" / "personlighedspsykologi"
    concept_manifest = repo_root / "show" / "concept_quiz_manifest.json"
    quiz_links = repo_root / "show" / "quiz_links.json"
    source = external_output / "W90L1" / "manual-videnskabsteori-quiz.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"quiz": [{"question": "Q?", "answer": "A"}]}), encoding="utf-8")
    lab_manifest.parent.mkdir(parents=True)
    lab_manifest.write_text(
        json.dumps(
            {
                "packs": [
                    {
                        "lecture_key": "W90L1",
                        "slug": "videnskabsteori-orienteringspunkter",
                        "title": "Videnskabsteori og orienteringspunkter",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(importer, "REPO_ROOT", repo_root)
    monkeypatch.setattr(importer, "LAB_MANIFEST_PATH", lab_manifest)
    monkeypatch.setattr(importer, "QUIZ_FILES_ROOT", quiz_files_root)
    monkeypatch.setattr(importer, "CONCEPT_MANIFEST_PATH", concept_manifest)
    monkeypatch.setattr(importer, "QUIZ_LINKS_PATH", quiz_links)

    result = importer.import_quizzes(output_root=external_output)

    assert result["imported"] == 1
    concept_payload = json.loads(concept_manifest.read_text(encoding="utf-8"))
    assert concept_payload["entries"][0]["source_output_path"] == source.resolve().as_posix()


def test_import_concept_quizzes_rejects_empty_quiz_payload(tmp_path: Path, monkeypatch) -> None:
    lab_manifest = tmp_path / "lab" / "manifest.json"
    output_root = tmp_path / "output"
    source = output_root / "W90L1" / "empty {type=quiz difficulty=medium}.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"questions": []}), encoding="utf-8")
    lab_manifest.parent.mkdir(parents=True)
    lab_manifest.write_text(
        json.dumps(
            {
                "packs": [
                    {
                        "lecture_key": "W90L1",
                        "slug": "videnskabsteori-orienteringspunkter",
                        "title": "Videnskabsteori og orienteringspunkter",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(importer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(importer, "LAB_MANIFEST_PATH", lab_manifest)
    monkeypatch.setattr(importer, "QUIZ_FILES_ROOT", tmp_path / "quiz-files")
    monkeypatch.setattr(importer, "CONCEPT_MANIFEST_PATH", tmp_path / "concept_quiz_manifest.json")
    monkeypatch.setattr(importer, "QUIZ_LINKS_PATH", tmp_path / "quiz_links.json")

    with pytest.raises(SystemExit, match="Missing generated quiz JSON"):
        importer.import_quizzes(output_root=output_root)
