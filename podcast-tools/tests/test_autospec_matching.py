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

    def test_week_only_token_requires_week_context(self):
        mod = _load_feed_module()
        self.assertFalse(mod.AutoSpec._matches(["12"], ["Grundbog kapitel 12"]))
        self.assertTrue(mod.AutoSpec._matches(["12"], ["week 12"]))
        self.assertTrue(mod.AutoSpec._matches(["12"], ["12"]))

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

    def test_strip_language_tags_removes_en_tts_and_optionally_brief(self):
        mod = _load_feed_module()
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [EN]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo (EN)"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [TTS]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo (tts)"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [Brief]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [ brief ]"), "W01L1 Foo")
        self.assertEqual(
            mod._strip_language_tags("W01L1 Foo [Brief]", strip_brief=False),
            "W01L1 Foo [Brief]",
        )
        self.assertEqual(
            mod._strip_language_tags(
                "W01L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
            ),
            "W01L1 Foo",
        )
        self.assertEqual(
            mod._strip_language_tags(
                "W01L1 Foo [TTS] {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}"
            ),
            "W01L1 Foo",
        )
        self.assertEqual(
            mod._strip_language_tags("Reading: Foo [EN] · Emne: Bar [EN]"),
            "Foo · Emne: Bar",
        )
        self.assertEqual(
            mod._strip_language_tags(
                "Reading: Lewis (1999) {type=audio lang=en format=deep-dive length=long hash=fa9adbcf} · Emne: Intro"
            ),
            "Lewis (1999) · Emne: Intro",
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

    def test_build_feed_document_defaults_to_published_at_desc_sort(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            episode_kind: str,
            is_tts: bool,
            sort_week: int,
            sort_lecture: int,
        ):
            published_dt = mod.parse_datetime(published_at)
            return {
                "guid": guid,
                "title": title,
                "description": title,
                "link": "https://example.com",
                "published_at": published_dt,
                "pubDate": mod.format_rfc2822(published_dt),
                "mimeType": "audio/mpeg",
                "size": 123,
                "duration": None,
                "explicit": "false",
                "image": None,
                "episode_kind": episode_kind,
                "is_tts": is_tts,
                "sort_week": sort_week,
                "sort_lecture": sort_lecture,
                "audio_url": f"https://example.com/{guid}.mp3",
            }

        episodes = [
            make_episode(
                guid="reading-latest",
                title="Reading latest",
                published_at="2026-02-02T10:00:00+00:00",
                episode_kind="reading",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="brief-earlier",
                title="Brief earlier",
                published_at="2026-02-02T09:00:00+00:00",
                episode_kind="brief",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
        ]
        feed = mod.build_feed_document(
            episodes=episodes,
            feed_config={
                "title": "Personlighedspsykologi",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
            },
            last_build=mod.parse_datetime("2026-02-10T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(titles, ["Reading latest", "Brief earlier"])

    def test_build_feed_document_wxlx_sort_brief_then_alle_then_tts_then_reading(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            episode_kind: str,
            is_tts: bool,
            sort_week: int,
            sort_lecture: int,
        ):
            published_dt = mod.parse_datetime(published_at)
            return {
                "guid": guid,
                "title": title,
                "description": title,
                "link": "https://example.com",
                "published_at": published_dt,
                "pubDate": mod.format_rfc2822(published_dt),
                "mimeType": "audio/mpeg",
                "size": 123,
                "duration": None,
                "explicit": "false",
                "image": None,
                "episode_kind": episode_kind,
                "is_tts": is_tts,
                "sort_week": sort_week,
                "sort_lecture": sort_lecture,
                "audio_url": f"https://example.com/{guid}.mp3",
            }

        episodes = [
            make_episode(
                guid="reading-latest",
                title="Reading latest",
                published_at="2026-02-02T14:00:00+00:00",
                episode_kind="reading",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="tts",
                title="TTS",
                published_at="2026-02-02T13:00:00+00:00",
                episode_kind="reading",
                is_tts=True,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="brief",
                title="Brief",
                published_at="2026-02-02T12:00:00+00:00",
                episode_kind="brief",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="alle",
                title="Alle kilder",
                published_at="2026-02-02T11:00:00+00:00",
                episode_kind="weekly_overview",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
        ]
        feed = mod.build_feed_document(
            episodes=episodes,
            feed_config={
                "title": "Personlighedspsykologi",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "sort_mode": "wxlx_kind_priority",
            },
            last_build=mod.parse_datetime("2026-02-10T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(titles, ["Brief", "Alle kilder", "TTS", "Reading latest"])

    def test_build_feed_document_wxlx_sort_uses_group_recency(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            episode_kind: str,
            is_tts: bool,
            sort_week: int,
            sort_lecture: int,
        ):
            published_dt = mod.parse_datetime(published_at)
            return {
                "guid": guid,
                "title": title,
                "description": title,
                "link": "https://example.com",
                "published_at": published_dt,
                "pubDate": mod.format_rfc2822(published_dt),
                "mimeType": "audio/mpeg",
                "size": 123,
                "duration": None,
                "explicit": "false",
                "image": None,
                "episode_kind": episode_kind,
                "is_tts": is_tts,
                "sort_week": sort_week,
                "sort_lecture": sort_lecture,
                "audio_url": f"https://example.com/{guid}.mp3",
            }

        episodes = [
            make_episode(
                guid="w1-brief",
                title="W1 brief",
                published_at="2026-02-01T10:00:00+00:00",
                episode_kind="brief",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="w1-alle",
                title="W1 alle",
                published_at="2026-02-01T09:00:00+00:00",
                episode_kind="weekly_overview",
                is_tts=False,
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="w2-reading",
                title="W2 reading",
                published_at="2026-02-02T08:00:00+00:00",
                episode_kind="reading",
                is_tts=False,
                sort_week=2,
                sort_lecture=1,
            ),
            make_episode(
                guid="w2-alle",
                title="W2 alle",
                published_at="2026-02-02T07:00:00+00:00",
                episode_kind="weekly_overview",
                is_tts=False,
                sort_week=2,
                sort_lecture=1,
            ),
        ]
        feed = mod.build_feed_document(
            episodes=episodes,
            feed_config={
                "title": "Personlighedspsykologi",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "sort_mode": "wxlx_kind_priority",
            },
            last_build=mod.parse_datetime("2026-02-10T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(titles, ["W2 alle", "W2 reading", "W1 brief", "W1 alle"])

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
        self.assertNotIn("Semesteruge 6", episode["description"])
        self.assertNotRegex(
            episode["description"],
            re.compile(r"Forelæsning\s+\d+\s*·\s*Semesteruge\s+\d+", re.IGNORECASE),
        )

    def test_build_episode_entry_rewrites_pubdate_year_when_configured(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+01:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
            "pubdate_year_rewrite": {
                "from": 2026,
                "to": 2025,
            },
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertIn(" 2025 ", episode["pubDate"])
        self.assertNotIn(" 2026 ", episode["pubDate"])
        self.assertEqual(episode["published_at"].year, 2026)

    def test_build_feed_document_does_not_rewrite_last_build_date(self):
        mod = _load_feed_module()
        published_dt = mod.parse_datetime("2026-02-02T08:00:00+00:00")
        episode = {
            "guid": "episode-1",
            "title": "Episode",
            "description": "Episode",
            "link": "https://example.com",
            "published_at": published_dt,
            "pubDate": "Mon, 02 Feb 2025 08:00:00 +0000",
            "mimeType": "audio/mpeg",
            "size": 123,
            "duration": None,
            "explicit": "false",
            "image": None,
            "episode_kind": "reading",
            "is_tts": False,
            "sort_week": 1,
            "sort_lecture": 1,
            "audio_url": "https://example.com/episode-1.mp3",
        }
        feed = mod.build_feed_document(
            episodes=[episode],
            feed_config={
                "title": "Personlighedspsykologi",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "pubdate_year_rewrite": {"from": 2026, "to": 2025},
            },
            last_build=published_dt,
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        self.assertEqual(
            root.findtext("./channel/lastBuildDate"),
            mod.format_rfc2822(published_dt),
        )
        self.assertEqual(
            root.findtext("./channel/item/pubDate"),
            "Mon, 02 Feb 2025 08:00:00 +0000",
        )

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

    def test_generated_entry_maps_tts_tag_to_lydbog_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "[TTS] W1L1 - Grundbog kapitel 01 - Introduktion til personlighedspsykologi "
                "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
            ),
            "createdTime": "2026-02-02T08:00:00+00:00",
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
            folder_names=["W01L1"],
        )
        self.assertIn("[Lydbog]", episode["title"])
        self.assertIn("Grundbog kapitel 01", episode["title"])
        self.assertNotIn("[TTS]", episode["title"])
        self.assertNotIn("Oplæst", episode["description"])
        self.assertNotRegex(episode["title"], re.compile(r"\bW\d{1,2}L\d+\b"))
        self.assertNotRegex(episode["description"], re.compile(r"\bW\d{1,2}L\d+\b"))

    def test_extract_sequence_number_prefers_chapter_and_ignores_cfg_digits(self):
        mod = _load_feed_module()
        chapter_file = (
            "[TTS] Grundbog kapitel 13 - Positiv psykologi "
            "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
        )
        forord_file = (
            "[TTS] Grundbog forord og resumé "
            "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
        )
        self.assertEqual(mod.AutoSpec._extract_sequence_number(chapter_file), 13)
        self.assertIsNone(mod.AutoSpec._extract_sequence_number(forord_file))

    def test_unassigned_sequence_items_stay_before_first_course_week(self):
        mod = _load_feed_module()
        spec = {
            "year": 2026,
            "week_reference_year": 2026,
            "timezone": "Europe/Copenhagen",
            "default_release": {"weekday": 1, "time": "08:00"},
            "increment_minutes": 120,
            "rules": [
                {
                    "iso_week": 6,
                    "course_week": 1,
                    "aliases": ["w01l1"],
                    "topic": "Week 1 topic",
                }
            ],
        }
        autospec = mod.AutoSpec(spec)

        chapter_02_meta = autospec.metadata_for(
            {
                "id": "u2",
                "name": (
                    "[TTS] Grundbog kapitel 02 - Trækpsykologi "
                    "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
                ),
            },
            ["grundbog-tts"],
        )
        chapter_13_meta = autospec.metadata_for(
            {
                "id": "u13",
                "name": (
                    "[TTS] Grundbog kapitel 13 - Positiv psykologi "
                    "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
                ),
            },
            ["grundbog-tts"],
        )

        self.assertIsNotNone(chapter_02_meta)
        self.assertIsNotNone(chapter_13_meta)

        chapter_02_date = mod.parse_datetime(chapter_02_meta["published_at"])
        chapter_13_date = mod.parse_datetime(chapter_13_meta["published_at"])

        self.assertLess(chapter_02_date, autospec._earliest_rule_datetime)
        self.assertLess(chapter_13_date, autospec._earliest_rule_datetime)
        self.assertGreater(chapter_02_date, chapter_13_date)

    def test_unassigned_chapter_number_does_not_match_iso_week_rule(self):
        mod = _load_feed_module()
        spec = {
            "year": 2026,
            "week_reference_year": 2026,
            "timezone": "Europe/Copenhagen",
            "default_release": {"weekday": 1, "time": "08:00"},
            "increment_minutes": 120,
            "rules": [
                {
                    "iso_week": 12,
                    "course_week": 7,
                    "aliases": ["w07l1"],
                    "topic": "Week 7 topic",
                }
            ],
        }
        autospec = mod.AutoSpec(spec)
        meta = autospec.metadata_for(
            {
                "id": "u12",
                "name": (
                    "[TTS] Grundbog kapitel 12 - Evolutionspsykologi "
                    "{type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav"
                ),
            },
            ["grundbog-tts"],
        )
        self.assertIsNotNone(meta)
        self.assertNotIn("course_week", meta)
        self.assertNotIn("topic", meta)
        self.assertLess(mod.parse_datetime(meta["published_at"]), autospec._earliest_rule_datetime)

    def test_generated_entry_maps_brief_to_kort_podcast_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[ brief ] W1L1 - Grundbog kapitel 01 [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
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
            folder_names=["W01L1"],
        )
        self.assertIn("[Kort podcast]", episode["title"])
        self.assertIn("Grundbog kapitel 01", episode["title"])
        self.assertNotIn("[Brief]", episode["title"])
        self.assertNotIn("[ brief ]", episode["title"])
        self.assertNotRegex(episode["title"], re.compile(r"\bW\d{1,2}L\d+\b"))
        self.assertIn("Kapitel i grundbogen", episode["description"])

    def test_generated_entry_maps_deep_dive_to_podcast_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "W1L1 - Lewis (1999) [EN] "
                "{type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            ),
            "createdTime": "2026-02-02T08:00:00+00:00",
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
            folder_names=["W01L1"],
        )
        self.assertIn("[Podcast]", episode["title"])
        self.assertNotIn("[deep-dive]", episode["title"])
        self.assertNotIn("{type=", episode["title"])
        self.assertNotRegex(episode["title"], re.compile(r"\bW\d{1,2}L\d+\b"))

    def test_audio_category_prefix_position_after_first_block_for_all_audio_kinds(self):
        mod = _load_feed_module()
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
            "semester_week_start_date": "2026-02-02",
            "semester_week_label": "Semesteruge",
            "semester_week_description_label": "Semesteruge",
            "audio_category_prefix_position": "after_first_block",
        }
        cases = [
            (
                "W1L1 - Lewis (1999) [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3",
                "[Podcast]",
                "Lewis (1999)",
            ),
            (
                "W1L1 - Alle kilder [EN].mp3",
                "[Podcast]",
                "Alle kilder",
            ),
            (
                "[Brief] W1L1 - Grundbog kapitel 01 [EN].mp3",
                "[Kort podcast]",
                "Grundbog kapitel 01",
            ),
            (
                "[TTS] W1L1 - Grundbog kapitel 01 [EN].mp3",
                "[Lydbog]",
                "Grundbog kapitel 01",
            ),
        ]
        for file_name, expected_prefix, expected_subject in cases:
            with self.subTest(file_name=file_name):
                episode = mod.build_episode_entry(
                    file_entry={
                        "id": "file1",
                        "name": file_name,
                        "createdTime": "2026-02-02T08:00:00+00:00",
                    },
                    feed_config=feed_config,
                    overrides={},
                    public_link_template="https://example.com/{file_id}",
                    auto_meta={"week_reference_year": 2026},
                    folder_names=["W01L1"],
                )
                self.assertIn(
                    f"Semesteruge 1, Forelæsning 1 · {expected_prefix} · ",
                    episode["title"],
                )
                self.assertIn(expected_subject, episode["title"])
                self.assertFalse(episode["title"].startswith(expected_prefix))

    def test_audio_category_prefix_after_first_block_falls_back_to_leading_with_single_title_block(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "title_blocks": ["subject"],
                "audio_category_prefix_position": "after_first_block",
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["title"], "[Podcast] Foo")

    def test_generated_entry_strips_cfg_tag_from_subject(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "W1L1 - Lewis (1999) [EN] "
                "{type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            ),
            "createdTime": "2026-02-02T08:00:00+00:00",
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
            auto_meta={"topic": "Introforelæsning og nøglebegreber i personlighedspsykologien"},
            folder_names=["W01L1"],
            quiz_cfg={"base_url": "http://64.226.79.109/quizzes/personlighedspsykologi/"},
            quiz_links={
                "by_name": {
                    "W1L1 - Lewis (1999) [EN].mp3": {
                        "relative_path": "W01L1/W01L1 - W1L1 Lewis (1999) [EN].html",
                        "format": "html",
                    }
                }
            },
        )
        self.assertNotIn("{type=", episode["title"])
        self.assertNotIn("{type=", episode["description"])

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
        self.assertEqual(episode["title"], "[Podcast] W3L1 Manual Title")
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
        self.assertEqual(episode["title"], "[Podcast] W3L1 Manual Title")
        self.assertEqual(episode["description"], "W3L1 Manual Description")

    def test_non_audio_episode_does_not_get_category_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W3L1 Manual [EN].pdf",
            "mimeType": "application/pdf",
            "createdTime": "2026-02-16T08:00:00+00:00",
        }
        overrides = {
            "by_name": {
                "W3L1 Manual [EN].pdf": {
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
        self.assertEqual(episode["title"], "[Podcast] W3L1 Manual Title")
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

    def test_description_blocks_by_kind_can_produce_topic_only_reading(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - W1L1 Lewis (1999) [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        feed_config = {
            "title": "Personlighedspsykologi (EN)",
            "link": "https://example.com",
            "description": "Test feed",
            "language": "en",
            "description_blocks_by_kind": {
                "reading": ["topic"],
            },
        }
        topic = "Introforelæsning og nøglebegreber i personlighedspsykologien"
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026, "topic": topic},
            folder_names=["W01L1"],
            quiz_cfg={"base_url": "http://64.226.79.109/quizzes/personlighedspsykologi/"},
            quiz_links={
                "by_name": {
                    "W01L1 - W1L1 Lewis (1999) [EN].mp3": {
                        "relative_path": "W01L1/W01L1 - W1L1 Lewis (1999) [EN].html",
                        "format": "html",
                    }
                }
            },
        )

        self.assertEqual(episode["description"], f"Emne: {topic}")
        self.assertTrue(
            episode["link"].startswith("http://64.226.79.109/quizzes/personlighedspsykologi/")
        )

    def test_description_quiz_block_preserves_newline_format(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        quiz_url = "http://64.226.79.109/quizzes/personlighedspsykologi/W01L1/W01L1%20-%20Foo%20%5BEN%5D.html"
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
            },
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
        self.assertIn("\n\nQuiz:\n", episode["description"])
        self.assertIn(quiz_url, episode["description"])

    def test_description_quiz_url_block_renders_inline(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks": ["descriptor_subject", "quiz_url"],
            },
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
        self.assertIn(" · http://64.226.79.109/quizzes/personlighedspsykologi/", episode["description"])
        self.assertNotIn("\n\nQuiz:\n", episode["description"])

    def test_per_kind_block_overrides_global_blocks(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "title_blocks": ["type_label"],
                "title_blocks_by_kind": {"reading": ["subject"]},
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["title"], "[Podcast] Foo")

    def test_missing_topic_with_topic_only_block_falls_back_to_descriptor_subject(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {"reading": ["topic"]},
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["description"], "Foo")

    def test_title_and_description_strip_lecture_semester_pair(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "semester_week_start_date": "2026-02-02",
                "semester_week_label": "Semesteruge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["lecture", "semester_week", "subject"],
                "description_blocks": ["lecture", "semester_week", "subject"],
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            folder_names=["W01L1"],
        )
        self.assertEqual(episode["title"], "[Podcast] Foo")
        self.assertEqual(episode["description"], "Foo")

    def test_reading_summary_and_key_points_render_for_reading(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "reading": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Summary line 1", "Summary line 2"],
                        "key_points": ["Point A", "Point B", "Point C"],
                    }
                }
            },
        )
        self.assertIn("Summary line 1\nSummary line 2", episode["description"])
        self.assertIn("\n\nKey points:\n- Point A\n- Point B\n- Point C", episode["description"])

    def test_reading_summary_and_key_points_render_for_brief(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[Brief] W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "brief": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "[Brief] W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Brief summary 1", "Brief summary 2"],
                        "key_points": ["Brief A", "Brief B", "Brief C"],
                    }
                }
            },
        )
        self.assertIn("Brief summary 1\nBrief summary 2", episode["description"])
        self.assertIn("\n\nKey points:\n- Brief A\n- Brief B\n- Brief C", episode["description"])

    def test_tts_reading_uses_lydbog_title_prefix_with_summary_blocks(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[TTS] W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "reading": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "[TTS] W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["TTS summary 1", "TTS summary 2"],
                        "key_points": ["TTS A", "TTS B", "TTS C"],
                    }
                }
            },
        )
        self.assertFalse(episode["description"].startswith("Oplæst"))
        self.assertIn("[Lydbog]", episode["title"])
        self.assertIn("\n\nKey points:\n- TTS A\n- TTS B\n- TTS C", episode["description"])

    def test_weekly_overview_ignores_reading_summary_blocks(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Alle kilder [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "weekly_overview": ["reading_summary", "descriptor_subject"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Alle kilder [EN].mp3": {
                        "summary_lines": ["Injected summary that must be ignored"],
                        "key_points": ["Injected point"],
                    }
                }
            },
        )
        self.assertNotIn("Injected summary that must be ignored", episode["description"])

    def test_missing_reading_summary_falls_back_to_descriptor_subject(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "reading": ["reading_summary"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={"by_name": {}},
        )
        self.assertEqual(episode["description"], "Foo")

    def test_reading_summary_lookup_matches_cfg_tagged_audio_name(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "W01L1 - Foo [EN] "
                "{type=audio lang=en format=deep-dive length=default hash=deadbeef}.mp3"
            ),
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "reading": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Cfg fallback summary"],
                        "key_points": ["Cfg fallback point"],
                    }
                }
            },
        )
        self.assertIn("Cfg fallback summary", episode["description"])
        self.assertIn("Cfg fallback point", episode["description"])

    def test_manual_description_override_wins_over_reading_summaries(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "description_blocks_by_kind": {
                    "reading": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "description": "Manual description [EN]",
                    }
                }
            },
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Summary that should not render"],
                        "key_points": ["Point that should not render"],
                    }
                }
            },
        )
        self.assertEqual(episode["description"], "Manual description")

    def test_validate_feed_block_config_accepts_reading_summary_blocks(self):
        mod = _load_feed_module()
        mod.validate_feed_block_config(
            {
                "description_blocks": ["reading_summary", "reading_key_points"],
            }
        )

    def test_validate_feed_block_config_rejects_unknown_sort_mode(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.sort_mode has unknown mode 'not_a_mode'"
        ):
            mod.validate_feed_block_config({"sort_mode": "not_a_mode"})

    def test_validate_feed_block_config_rejects_unknown_audio_prefix_position(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.audio_category_prefix_position has unknown value 'middle'",
        ):
            mod.validate_feed_block_config({"audio_category_prefix_position": "middle"})

    def test_validate_feed_block_config_rejects_invalid_pubdate_year_rewrite(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.pubdate_year_rewrite",
        ):
            mod.validate_feed_block_config(
                {"pubdate_year_rewrite": {"from": "abc", "to": 2025}}
            )

    def test_validate_feed_block_config_rejects_unknown_description_block(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.description_blocks\[0\].*unknown block 'does_not_exist'"
        ):
            mod.validate_feed_block_config({"description_blocks": ["does_not_exist"]})

    def test_validate_feed_block_config_rejects_unknown_kind(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.title_blocks_by_kind has unknown kind 'unknown_kind'"
        ):
            mod.validate_feed_block_config(
                {"title_blocks_by_kind": {"unknown_kind": ["subject"]}}
            )

    def test_validate_feed_block_config_rejects_deprecated_reading_description_mode(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(ValueError, r"feed\.reading_description_mode is deprecated"):
            mod.validate_feed_block_config({"reading_description_mode": "topic_only"})

    def test_validate_feed_block_config_rejects_empty_block_list(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(ValueError, r"feed\.title_blocks must be a non-empty list"):
            mod.validate_feed_block_config({"title_blocks": []})


if __name__ == "__main__":
    unittest.main()
