import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "audit_personlighedspsykologi_slide_briefs.py"
    spec = importlib.util.spec_from_file_location("audit_personlighedspsykologi_slide_briefs", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_rss(path: Path, titles: list[str]) -> None:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    for title in titles:
        item = ET.SubElement(channel, "item")
        title_node = ET.SubElement(item, "title")
        title_node.text = title
    path.write_text(ET.tostring(rss, encoding="unicode"), encoding="utf-8")


class PersonlighedspsykologiSlideBriefAuditTests(unittest.TestCase):
    def test_build_expected_title_uses_course_week_long_form(self):
        mod = _load_module()

        self.assertEqual(
            mod.build_expected_title("W02L1", "Kort podcast", "PersPsy 3 260209"),
            "Uge 2, Forelæsning 1 · Kort podcast · Forelæsningsslides - PersPsy 3 260209",
        )

    def test_audit_detects_missing_lecture_slide_brief(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            slides_catalog = root / "slides_catalog.json"
            rss = root / "rss.xml"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "slides": [
                            {
                                "lecture_key": "W01L1",
                                "subcategory": "lecture",
                                "title": "1. gang Intro",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            _write_rss(
                rss,
                ["Uge 1, Forelæsning 1 · Podcast · Forelæsningsslides - Intro"],
            )

            titles = mod.rss_titles(rss)
            expectations = list(
                mod.iter_slide_expectations(
                    json.loads(slides_catalog.read_text(encoding="utf-8")),
                    feed_module=type("Feed", (), {"_normalize_slide_subject": staticmethod(lambda value: "Intro")}),
                )
            )

            self.assertEqual(expectations, [("W01L1", "lecture", "Intro")])
            self.assertNotIn(
                "Uge 1, Forelæsning 1 · Kort podcast · Forelæsningsslides - Intro",
                titles,
            )

    def test_audit_flags_nonlecture_slide_briefs(self):
        mod = _load_module()

        full_title = mod.build_expected_title("W02L1", "Podcast", "Trækteori")
        brief_title = mod.build_expected_title("W02L1", "Kort podcast", "Trækteori")

        self.assertEqual(
            full_title,
            "Uge 2, Forelæsning 1 · Podcast · Forelæsningsslides - Trækteori",
        )
        self.assertEqual(
            brief_title,
            "Uge 2, Forelæsning 1 · Kort podcast · Forelæsningsslides - Trækteori",
        )
