import importlib.util
import json
import sys
from pathlib import Path

from pypdf import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_source_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_source_catalog",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_reading_sync_module():
    script_path = ROOT / "scripts" / "sync_personlighedspsykologi_readings_to_droplet.py"
    spec = importlib.util.spec_from_file_location(
        "sync_personlighedspsykologi_readings_to_droplet",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def test_build_source_catalog_tracks_readings_slides_and_sidecars(tmp_path):
    mod = _load_module()
    helper = _load_reading_sync_module()

    repo_root = ROOT
    subject_root = tmp_path / "Personlighedspsykologi"
    week_dir = subject_root / "Readings" / "W01L1 Intro"
    reading_pdf = week_dir / "Grundbog kapitel 1 - Introduktion til personlighed.pdf"
    slide_pdf = subject_root / "Forelæsningsrækken" / "Slides 1.pdf"
    _write_pdf(reading_pdf, pages=2)
    _write_pdf(slide_pdf, pages=5)

    (reading_pdf.parent / "Grundbog kapitel 1 - Introduktion til personlighed.analysis.md").write_text(
        "reading analysis",
        encoding="utf-8",
    )
    (week_dir / "week.analysis.md").write_text("week analysis", encoding="utf-8")
    (slide_pdf.parent / "Slides 1.analysis.md").write_text("slide analysis", encoding="utf-8")

    reading_key_path = tmp_path / "reading-file-key.md"
    reading_key_path.write_text(
        "\n".join(
            [
                "**W01L1 Intro**",
                "- Grundbog kapitel 1 - Introduktion til personlighed → Grundbog kapitel 1 - Introduktion til personlighed.pdf",
            ]
        ),
        encoding="utf-8",
    )
    reading_entries = helper.parse_reading_key(reading_key_path)
    reading_key = reading_entries[0].reading_key

    content_manifest_path = tmp_path / "content_manifest.json"
    content_manifest_path.write_text(
        json.dumps(
            {
                "version": 3,
                "subject_slug": "personlighedspsykologi",
                "source_meta": {},
                "warnings": [],
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "lecture_title": "Intro",
                        "sequence_index": 1,
                        "summary": {
                            "summary_lines": ["manual lecture summary"],
                            "key_points": ["point"],
                        },
                        "lecture_assets": {},
                        "warnings": [],
                        "readings": [
                            {
                                "reading_key": reading_key,
                                "reading_title": "Grundbog kapitel 1 - Introduktion til personlighed",
                                "sequence_index": 1,
                                "source_filename": "Grundbog kapitel 1 - Introduktion til personlighed.pdf",
                                "is_missing": False,
                                "summary": {
                                    "summary_lines": ["manual reading summary"],
                                    "key_points": ["point"],
                                },
                                "assets": {"podcasts": [], "quizzes": []},
                            },
                            {
                                "reading_key": "w01l1-missing-reading-12345678",
                                "reading_title": "Missing reading",
                                "sequence_index": 2,
                                "source_filename": None,
                                "is_missing": True,
                                "summary": {},
                                "assets": {"podcasts": [], "quizzes": []},
                            },
                        ],
                        "slides": [
                            {
                                "slide_key": "w01l1-lecture-slide-1",
                                "subcategory": "lecture",
                                "title": "Slides 1",
                                "source_filename": "Slides 1.pdf",
                                "relative_path": "W01L1/lecture/Slides 1.pdf",
                                "assets": {"podcasts": [], "quizzes": []},
                            }
                        ],
                    }
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    slides_catalog_path = tmp_path / "slides_catalog.json"
    slides_catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "subject_slug": "personlighedspsykologi",
                "generated_at": "2026-05-04T00:00:00Z",
                "slides": [
                    {
                        "slide_key": "w01l1-lecture-slide-1",
                        "lecture_key": "W01L1",
                        "subcategory": "lecture",
                        "title": "Slides 1",
                        "source_filename": "Slides 1.pdf",
                        "relative_path": "W01L1/lecture/Slides 1.pdf",
                        "matched_by": "manual",
                        "local_relative_path": "Forelæsningsrækken/Slides 1.pdf",
                    }
                ],
                "unresolved": [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prompt_config_path = tmp_path / "prompt_config.json"
    prompt_config_path.write_text(json.dumps({"meta_prompting": {"enabled": True}}, indent=2), encoding="utf-8")

    catalog = mod.build_source_catalog(
        repo_root=repo_root,
        subject_root=subject_root,
        output_path=tmp_path / "source_catalog.json",
        content_manifest_path=content_manifest_path,
        slides_catalog_path=slides_catalog_path,
        reading_key_path=reading_key_path,
        prompt_config_path=prompt_config_path,
    )

    assert catalog["stats"]["lecture_count"] == 1
    assert catalog["stats"]["source_count"] == 3
    assert catalog["stats"]["reading_count"] == 2
    assert catalog["stats"]["slide_count"] == 1
    assert catalog["stats"]["missing_source_count"] == 1
    assert catalog["stats"]["manual_source_summary_count"] == 1
    assert catalog["stats"]["lecture_week_prompt_analysis_count"] == 1

    lecture = catalog["lectures"][0]
    assert lecture["week_prompt_analysis_present"] is True
    assert lecture["week_prompt_analysis_sidecars"] == ["Readings/W01L1 Intro/week.analysis.md"]

    by_id = {item["source_id"]: item for item in catalog["sources"]}

    resolved = by_id[reading_key]
    assert resolved["source_exists"] is True
    assert resolved["subject_relative_path"] == (
        "Readings/W01L1 Intro/Grundbog kapitel 1 - Introduktion til personlighed.pdf"
    )
    assert resolved["priority_signals"]["has_manual_summary"] is True
    assert resolved["priority_signals"]["has_prompt_analysis_sidecar"] is True
    assert resolved["evidence_origin"] == "textbook_framing"
    assert resolved["prompt_analysis_sidecars"] == [
        "Readings/W01L1 Intro/Grundbog kapitel 1 - Introduktion til personlighed.analysis.md"
    ]
    assert resolved["file"]["page_count"] == 2
    assert resolved["file"]["sha256"]
    assert resolved["file"]["text_extraction_status"] == "metadata_only_no_local_text_extraction"

    missing = by_id["w01l1-missing-reading-12345678"]
    assert missing["source_exists"] is False
    assert missing["missing_reason"] == "manifest_marked_missing"
    assert missing["file"]["text_extraction_status"] == "missing_source"

    slide = by_id["w01l1-lecture-slide-1"]
    assert slide["source_exists"] is True
    assert slide["source_kind"] == "slide"
    assert slide["slide_subcategory"] == "lecture"
    assert slide["evidence_origin"] == "lecture_framed"
    assert slide["subject_relative_path"] == "Forelæsningsrækken/Slides 1.pdf"
    assert slide["prompt_analysis_sidecars"] == ["Forelæsningsrækken/Slides 1.analysis.md"]
