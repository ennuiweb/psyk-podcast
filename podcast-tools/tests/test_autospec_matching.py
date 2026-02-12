import importlib.util
import re
import unittest
from pathlib import Path


def _load_feed_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "gdrive_podcast_feed.py"
    spec = importlib.util.spec_from_file_location("gdrive_podcast_feed", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoSpecMatchingTests(unittest.TestCase):
    def test_week_only_token_does_not_match_lecture_token(self):
        mod = _load_feed_module()
        self.assertFalse(mod.AutoSpec._matches(["w6"], ["w6l1"]))
        self.assertFalse(mod.AutoSpec._matches(["week 6"], ["week 6l1"]))
        self.assertFalse(mod.AutoSpec._matches(["6"], ["w6l1"]))

    def test_lecture_token_prefers_specific_rule(self):
        mod = _load_feed_module()
        spec = {
            "year": 2026,
            "week_reference_year": 2026,
            "timezone": "Europe/Copenhagen",
            "default_release": {"weekday": 1, "time": "08:00"},
            "increment_minutes": 5,
            "rules": [
                {
                    # ISO week 6 starts on 2026-02-02, but this rule is course week 1.
                    "iso_week": 6,
                    "course_week": 1,
                    "aliases": ["w01l1", "week 01l1", "w1l1"],
                    "topic": "Week 1 topic",
                },
                {
                    # ISO week 11 starts on 2026-03-09, this is course week 6.
                    "iso_week": 11,
                    "course_week": 6,
                    "aliases": ["w06l1", "week 06l1", "w6l1"],
                    "topic": "Week 6 topic",
                },
            ],
        }
        autospec = mod.AutoSpec(spec)

        file_entry = {"id": "file1", "name": "W06L1 - Something [EN].mp3"}
        meta = autospec.metadata_for(file_entry, ["W06L1"])
        self.assertIsNotNone(meta)
        self.assertEqual(meta.get("course_week"), 6)

    def test_canonicalize_episode_stem_strips_duplicate_week_tokens(self):
        mod = _load_feed_module()
        value = "W01L2 - W1L2 Phan et al..... (2024) [EN].png"
        # Canonical form keeps a single padded week token and collapses repeated dots.
        self.assertEqual(mod._canonicalize_episode_stem(value), "w01l2 - phan et al. (2024) [en]")

    def test_strip_week_prefix_removes_unpadded_and_repeated_tokens(self):
        mod = _load_feed_module()
        cases = {
            "W03L1 - Foo": "Foo",
            "W3L1 Foo": "Foo",
            "W6L1 X Spinelli (2005)": "X Spinelli (2005)",
            "W01 - Alle kilder": "Alle kilder",
            "W01L1 - W1L1 Lewis (1999)": "Lewis (1999)",
        }
        for value, expected in cases.items():
            self.assertEqual(mod.strip_week_prefix(value), expected)
        self.assertEqual(mod.strip_week_prefix("Reading W3L1 methods"), "Reading W3L1 methods")

    def test_strip_language_tags_removes_en(self):
        mod = _load_feed_module()
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [EN]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo (EN)"), "W01L1 Foo")
        self.assertEqual(
            mod._strip_language_tags(
                "W01L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
            ),
            "W01L1 Foo",
        )
        self.assertEqual(
            mod._strip_language_tags("Reading: Foo [EN] · Emne: Bar [EN]"),
            "Reading: Foo · Emne: Bar",
        )

    def test_feed_title_strips_language_tag(self):
        mod = _load_feed_module()
        feed = mod.build_feed_document(
            episodes=[],
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
            },
            last_build=mod.parse_datetime("2026-02-10T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        xml = ET.tostring(feed, encoding="unicode")
        self.assertIn("<title>Personlighedspsykologi</title>", xml)
        self.assertNotIn("(EN)", xml)
        self.assertNotIn("[EN]", xml)

    def test_semester_week_label_uses_calendar_week_range(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W06L1 - Something [EN].mp3",
            "createdTime": "2026-03-09T08:00:00+00:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
            "semester_week_start_date": "2026-02-02",
            "semester_week_label": "Semesteruge",
            "semester_week_description_label": "Semesteruge",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W06L1"],
        )
        self.assertIn("Semesteruge 6", episode["title"])
        self.assertIn("(Uge 11 09/03 - 15/03)", episode["title"])
        self.assertIn("Semesteruge 6", episode["description"])

    def test_generated_entry_strips_unpadded_week_token_from_subject(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W3L1 Zettler et al... (2025) [EN].mp3",
            "createdTime": "2026-02-16T08:00:00+00:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
            "semester_week_start_date": "2026-02-02",
            "semester_week_label": "Semesteruge",
            "semester_week_description_label": "Semesteruge",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026, "topic": "Culture and personality"},
            folder_names=["W03L1"],
        )
        self.assertIn("Zettler et al... (2025)", episode["title"])
        self.assertNotRegex(episode["title"], re.compile(r"\bW\d{1,2}L\d+\b"))
        self.assertNotRegex(episode["description"], re.compile(r"\bW\d{1,2}L\d+\b"))

    def test_manual_title_and_description_keep_week_tokens(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W3L1 Manual [EN].mp3",
            "createdTime": "2026-02-16T08:00:00+00:00",
        }
        overrides = {
            "by_name": {
                "W3L1 Manual [EN].mp3": {
                    "title": "W3L1 Manual Title [EN]",
                    "description": "W3L1 Manual Description [EN]",
                }
            }
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides=overrides,
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["title"], "W3L1 Manual Title")
        self.assertEqual(episode["description"], "W3L1 Manual Description")

    def test_manual_metadata_fallback_matches_cfg_tagged_name(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W3L1 Manual [EN] {type=audio lang=en format=deep-dive length=default hash=deadbeef}.mp3",
            "createdTime": "2026-02-16T08:00:00+00:00",
        }
        overrides = {
            "by_name": {
                "W3L1 Manual [EN].mp3": {
                    "title": "W3L1 Manual Title [EN]",
                    "description": "W3L1 Manual Description [EN]",
                }
            }
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides=overrides,
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["title"], "W3L1 Manual Title")
        self.assertEqual(episode["description"], "W3L1 Manual Description")

    def test_manual_metadata_fallback_matches_tagged_name_with_profile_suffix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "W3L1 Manual [EN] "
                "{type=audio lang=en format=deep-dive length=default hash=deadbeef} [default].mp3"
            ),
            "createdTime": "2026-02-16T08:00:00+00:00",
        }
        overrides = {
            "by_name": {
                "W3L1 Manual [EN].mp3": {
                    "title": "W3L1 Manual Title [EN]",
                    "description": "W3L1 Manual Description [EN]",
                }
            }
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides=overrides,
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["title"], "W3L1 Manual Title")
        self.assertEqual(episode["description"], "W3L1 Manual Description")

    def test_quiz_link_uses_configured_base_url(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "http://64.226.79.109/quizzes/personlighedspsykologi/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "W01L1/W01L1 - Foo [EN].html",
                        "format": "html",
                    }
                }
            },
        )
        self.assertTrue(
            episode["link"].startswith("http://64.226.79.109/quizzes/personlighedspsykologi/")
        )

    def test_quiz_link_fallback_matches_untagged_key_for_tagged_audio_name(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN] {type=audio lang=en format=deep-dive length=default hash=deadbeef}.mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "http://64.226.79.109/quizzes/personlighedspsykologi/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "W01L1/W01L1 - Foo [EN].html",
                        "format": "html",
                    }
                }
            },
        )
        self.assertTrue(
            episode["link"].startswith("http://64.226.79.109/quizzes/personlighedspsykologi/")
        )


if __name__ == "__main__":
    unittest.main()
