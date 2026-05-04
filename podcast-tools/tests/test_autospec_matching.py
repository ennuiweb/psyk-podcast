import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr
from email.utils import parsedate_to_datetime
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

    def test_strip_language_tags_removes_en_tts_and_optionally_short(self):
        mod = _load_feed_module()
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [EN]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo (EN)"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [TTS]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo (tts)"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [Short]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [Brief]"), "W01L1 Foo")
        self.assertEqual(mod._strip_language_tags("W01L1 Foo [ brief ]"), "W01L1 Foo")
        self.assertEqual(
            mod._strip_language_tags("W01L1 Foo [Short]", strip_brief=False),
            "W01L1 Foo [Short]",
        )
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

    def test_build_episode_entry_prefers_stable_guid_and_storage_key_url(self):
        mod = _load_feed_module()
        episode = mod.build_episode_entry(
            {
                "id": "r2-key",
                "name": "W01L1 - Intro [EN].mp3",
                "mimeType": "audio/mpeg",
                "size": 123,
                "createdTime": "2026-02-02T10:00:00+00:00",
                "source_storage_provider": "r2",
                "source_storage_key": "shows/personal/W01L1 - Intro [EN].mp3",
                "source_path": "W01L1 - Intro [EN].mp3",
                "stable_guid": "legacy-drive-guid",
            },
            {
                "title": "Test feed",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
            },
            overrides={},
            public_link_template="https://audio.example.com/{file_path}",
        )

        self.assertEqual(episode["guid"], "legacy-drive-guid")
        self.assertEqual(episode["episode_key"], "legacy-drive-guid")
        self.assertEqual(
            episode["audio_url"],
            "https://audio.example.com/shows/personal/W01L1%20-%20Intro%20%5BEN%5D.mp3",
        )
        self.assertEqual(episode["source_storage_provider"], "r2")
        self.assertEqual(episode["source_storage_key"], "shows/personal/W01L1 - Intro [EN].mp3")

    def test_resolve_public_link_template_prefers_storage_base_for_r2(self):
        mod = _load_feed_module()
        template = mod.resolve_public_link_template(
            {
                "public_link_template": "https://drive.google.com/uc?export=download&id={file_id}",
                "storage": {
                    "provider": "r2",
                    "public_base_url": "https://audio.example.com",
                },
            }
        )
        self.assertEqual(template, "https://audio.example.com/{file_path}")

    def test_resolve_public_link_template_prefers_storage_template_for_r2(self):
        mod = _load_feed_module()
        template = mod.resolve_public_link_template(
            {
                "public_link_template": "https://drive.google.com/uc?export=download&id={file_id}",
                "storage": {
                    "provider": "r2",
                    "public_base_url": "https://audio.example.com",
                    "public_link_template": "https://cdn.example.com/media/{file_path}?dl=1",
                },
            }
        )
        self.assertEqual(template, "https://cdn.example.com/media/{file_path}?dl=1")

    def test_load_existing_inventory_identity_map_falls_back_to_existing_feed(self):
        mod = _load_feed_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            feed_path = tmp / "feeds" / "rss.xml"
            feed_path.parent.mkdir(parents=True, exist_ok=True)
            feed_path.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>W01L1 - Intro [EN].mp3</title>
      <guid>legacy-guid-1</guid>
      <enclosure url="https://drive.google.com/uc?export=download&amp;id=drive-file-1" />
    </item>
  </channel>
</rss>
""",
                encoding="utf-8",
            )
            config = {"output_feed": str(feed_path)}
            identity_map = mod._load_existing_inventory_identity_map(config)
            self.assertEqual(identity_map["drive-file-1"], "legacy-guid-1")
            self.assertEqual(identity_map["W01L1 - Intro [EN].mp3"], "legacy-guid-1")

    def test_apply_existing_identity_uses_source_drive_file_id(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "shows/example/intro.mp3",
            "name": "W01L1 - Intro [EN].mp3",
            "source_drive_file_id": "drive-file-1",
        }
        mod._apply_existing_identity(file_entry, {"drive-file-1": "legacy-guid-1"})
        self.assertEqual(file_entry["stable_guid"], "legacy-guid-1")

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

    def test_build_feed_document_wxlx_source_pair_priority_pairs_short_and_full_sources(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            episode_kind: str,
            podcast_kind: str,
            sort_source_kind: str,
            sort_subject_key: str,
            sort_tail: bool = False,
            sort_tail_index: int | None = None,
        ):
            published_dt = mod.parse_datetime(published_at)
            payload = {
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
                "podcast_kind": podcast_kind,
                "is_tts": podcast_kind == "lydbog",
                "sort_week": None if sort_tail else 12,
                "sort_lecture": None if sort_tail else 1,
                "sort_tail": sort_tail,
                "sort_source_kind": sort_source_kind,
                "sort_subject_key": sort_subject_key,
                "audio_url": f"https://example.com/{guid}.mp3",
            }
            if sort_tail_index is not None:
                payload["sort_tail_index"] = sort_tail_index
            return payload

        episodes = [
            make_episode(
                guid="grund-full",
                title="U12F1 · Grundbog 8: Historicitet",
                published_at="2026-04-15T10:00:00+00:00",
                episode_kind="reading",
                podcast_kind="podcast",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 8: Historicitet",
            ),
            make_episode(
                guid="grund14-full",
                title="U12F1 · Grundbog 14: Perspektiver",
                published_at="2026-04-15T14:00:00+00:00",
                episode_kind="reading",
                podcast_kind="podcast",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 14: Perspektiver",
            ),
            make_episode(
                guid="slides-full",
                title="U12F1 · Forelæsningsslides · Personlighed og historicitet",
                published_at="2026-04-15T08:00:00+00:00",
                episode_kind="slide",
                podcast_kind="podcast",
                sort_source_kind="slide",
                sort_subject_key="Personlighed og historicitet",
            ),
            make_episode(
                guid="elias-brief",
                title="U12F1 · [Kort] · Elias (2000)",
                published_at="2026-04-15T12:00:00+00:00",
                episode_kind="brief",
                podcast_kind="kort_podcast",
                sort_source_kind="reading",
                sort_subject_key="Elias (2000)",
            ),
            make_episode(
                guid="weekly",
                title="U12F1 · ALLE KILDER",
                published_at="2026-04-15T07:00:00+00:00",
                episode_kind="weekly_overview",
                podcast_kind="podcast",
                sort_source_kind="weekly_overview",
                sort_subject_key="ALLE KILDER",
            ),
            make_episode(
                guid="tail-grund",
                title="U12F1 · [Lydbog] · Grundbog 8: Historicitet",
                published_at="2026-04-16T08:00:00+00:00",
                episode_kind="reading",
                podcast_kind="lydbog",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 8: Historicitet",
                sort_tail=True,
                sort_tail_index=8,
            ),
            make_episode(
                guid="tail-grund14",
                title="U12F1 · [Lydbog] · Grundbog 14: Perspektiver",
                published_at="2026-04-16T09:00:00+00:00",
                episode_kind="reading",
                podcast_kind="lydbog",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 14: Perspektiver",
                sort_tail=True,
                sort_tail_index=14,
            ),
            make_episode(
                guid="slides-brief",
                title="U12F1 · [Kort] · Forelæsningsslides · Personlighed og historicitet",
                published_at="2026-04-15T09:00:00+00:00",
                episode_kind="brief",
                podcast_kind="kort_podcast",
                sort_source_kind="slide",
                sort_subject_key="Personlighed og historicitet",
            ),
            make_episode(
                guid="elias-full",
                title="U12F1 · Elias (2000)",
                published_at="2026-04-15T11:00:00+00:00",
                episode_kind="reading",
                podcast_kind="podcast",
                sort_source_kind="reading",
                sort_subject_key="Elias (2000)",
            ),
            make_episode(
                guid="grund14-brief",
                title="U12F1 · [Kort] · Grundbog 14: Perspektiver",
                published_at="2026-04-15T14:30:00+00:00",
                episode_kind="brief",
                podcast_kind="kort_podcast",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 14: Perspektiver",
            ),
            make_episode(
                guid="grund-brief",
                title="U12F1 · [Kort] · Grundbog 8: Historicitet",
                published_at="2026-04-15T10:30:00+00:00",
                episode_kind="brief",
                podcast_kind="kort_podcast",
                sort_source_kind="reading",
                sort_subject_key="Grundbog 8: Historicitet",
            ),
        ]
        feed = mod.build_feed_document(
            episodes=episodes,
            feed_config={
                "title": "Personlighedspsykologi",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "sort_mode": "wxlx_source_pair_priority",
            },
            last_build=mod.parse_datetime("2026-04-16T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(
            titles,
            [
                "U12F1 · ALLE KILDER",
                "U12F1 · [Kort] · Elias (2000)",
                "U12F1 · Elias (2000)",
                "U12F1 · [Kort] · Grundbog 8: Historicitet",
                "U12F1 · Grundbog 8: Historicitet",
                "U12F1 · [Kort] · Grundbog 14: Perspektiver",
                "U12F1 · Grundbog 14: Perspektiver",
                "U12F1 · [Kort] · Forelæsningsslides · Personlighed og historicitet",
                "U12F1 · Forelæsningsslides · Personlighed og historicitet",
                "U12F1 · [Lydbog] · Grundbog 8: Historicitet",
                "U12F1 · [Lydbog] · Grundbog 14: Perspektiver",
            ],
        )

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

    def test_build_feed_document_wxlx_sort_resequences_pubdates_for_oldest_clients(self):
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
                guid="alle",
                title="Alle kilder",
                published_at="2026-02-02T10:00:00+00:00",
                episode_kind="weekly_overview",
                is_tts=False,
                sort_week=2,
                sort_lecture=1,
            ),
            make_episode(
                guid="reading-newer",
                title="Reading newer",
                published_at="2026-02-02T12:00:00+00:00",
                episode_kind="reading",
                is_tts=False,
                sort_week=2,
                sort_lecture=1,
            ),
            make_episode(
                guid="reading-older",
                title="Reading older",
                published_at="2026-02-02T08:00:00+00:00",
                episode_kind="reading",
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
        items = root.findall("./channel/item")
        by_oldest = sorted(
            (
                (
                    parsedate_to_datetime(item.findtext("pubDate", "")),
                    item.findtext("title", ""),
                )
                for item in items
            ),
            key=lambda pair: pair[0],
        )
        oldest_titles = [title for _, title in by_oldest]
        self.assertEqual(oldest_titles, ["Alle kilder", "Reading older", "Reading newer"])

    def test_build_feed_document_wxlx_tail_items_always_sort_last(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            episode_kind: str,
            sort_week: int | None = None,
            sort_lecture: int | None = None,
            sort_tail: bool = False,
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
                "is_tts": False,
                "sort_week": sort_week,
                "sort_lecture": sort_lecture,
                "sort_tail": sort_tail,
                "audio_url": f"https://example.com/{guid}.mp3",
            }

        episodes = [
            make_episode(
                guid="w1-reading",
                title="W1 reading",
                published_at="2026-02-02T08:00:00+00:00",
                episode_kind="reading",
                sort_week=1,
                sort_lecture=1,
            ),
            make_episode(
                guid="tail-newer",
                title="Tail newer",
                published_at="2026-03-01T08:00:00+00:00",
                episode_kind="reading",
                sort_tail=True,
            ),
            make_episode(
                guid="w2-reading",
                title="W2 reading",
                published_at="2026-02-09T08:00:00+00:00",
                episode_kind="reading",
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
            last_build=mod.parse_datetime("2026-03-01T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(titles, ["W2 reading", "W1 reading", "Tail newer"])

    def test_build_feed_document_wxlx_tail_items_use_sort_tail_index(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            published_at: str,
            sort_tail: bool = False,
            sort_tail_index: int | None = None,
        ):
            published_dt = mod.parse_datetime(published_at)
            payload = {
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
                "episode_kind": "reading",
                "is_tts": True,
                "sort_week": None,
                "sort_lecture": None,
                "sort_tail": sort_tail,
                "audio_url": f"https://example.com/{guid}.mp3",
            }
            if sort_tail_index is not None:
                payload["sort_tail_index"] = sort_tail_index
            return payload

        episodes = [
            make_episode(
                guid="week-item",
                title="Week item",
                published_at="2026-03-01T08:00:00+00:00",
            ),
            make_episode(
                guid="tail-ch-2",
                title="Tail chapter 2",
                published_at="2026-03-15T08:00:00+00:00",
                sort_tail=True,
                sort_tail_index=2,
            ),
            make_episode(
                guid="tail-ch-1",
                title="Tail chapter 1",
                published_at="2026-03-10T08:00:00+00:00",
                sort_tail=True,
                sort_tail_index=1,
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
            last_build=mod.parse_datetime("2026-03-16T00:00:00+00:00"),
        )
        from xml.etree import ElementTree as ET

        root = ET.fromstring(ET.tostring(feed, encoding="unicode"))
        titles = [el.text for el in root.findall("./channel/item/title")]
        self.assertEqual(titles, ["Week item", "Tail chapter 1", "Tail chapter 2"])

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

    def test_generated_entry_unassigned_tail_omits_semester_week_and_range(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[TTS] Grundbog kapitel 13 - Positiv psykologi.wav",
            "createdTime": "2026-01-22T08:00:00+00:00",
        }
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
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config=feed_config,
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026, "unassigned_tail": True},
            folder_names=["grundbog-tts"],
        )
        self.assertTrue(episode.get("sort_tail"))
        self.assertEqual(episode["title"], "[Lydbog] · Grundbog kapitel 13 - Positiv psykologi")

    def test_extract_tail_grundbog_lydbog_key_detects_forord_and_chapters(self):
        mod = _load_feed_module()
        self.assertEqual(
            mod._extract_tail_grundbog_lydbog_key(
                {
                    "title": "[Lydbog] · Grundbog forord og resumé",
                    "description": "Grundbog forord og resumé",
                    "is_tts": True,
                }
            ),
            "forord",
        )
        self.assertEqual(
            mod._extract_tail_grundbog_lydbog_key(
                {
                    "title": "Semesteruge 4 · [Lydbog] · Grundbog kapitel 01 - Intro · (Uge 4 19/01 - 25/01)",
                    "description": "Grundbog kapitel 01 - Intro",
                    "is_tts": True,
                }
            ),
            "chapter:1",
        )
        self.assertEqual(
            mod._extract_tail_grundbog_lydbog_key(
                {
                    "title": "[Lydbog] · Grundbog kapitel 14 - Bonus",
                    "description": "Grundbog kapitel 14 - Bonus",
                    "is_tts": True,
                }
            ),
            "chapter:14",
        )
        self.assertIsNone(
            mod._extract_tail_grundbog_lydbog_key(
                {
                    "title": "[Podcast] · Kapitel 02 - Ikke grundbog",
                    "description": "Kapitel 02 - Ikke grundbog",
                    "is_tts": True,
                }
            )
        )
        self.assertIsNone(
            mod._extract_tail_grundbog_lydbog_key(
                {
                    "title": "[Lydbog] · Grundbog appendiks",
                    "description": "Grundbog appendiks",
                    "is_tts": True,
                }
            )
        )

    def test_synthesize_tail_grundbog_lydbog_block_produces_forord_plus_1_to_14(self):
        mod = _load_feed_module()

        def make_episode(
            *,
            guid: str,
            title: str,
            description: str,
            published_at: str,
            sort_tail: bool,
        ):
            published_dt = mod.parse_datetime(published_at)
            return {
                "guid": guid,
                "title": title,
                "description": description,
                "link": "https://example.com",
                "published_at": published_dt,
                "pubDate": mod.format_rfc2822(published_dt),
                "mimeType": "audio/x-wav",
                "size": 123,
                "duration": None,
                "explicit": "false",
                "image": None,
                "episode_kind": "reading",
                "is_tts": True,
                "sort_week": None if sort_tail else 1,
                "sort_lecture": None if sort_tail else 1,
                "sort_tail": sort_tail,
                "audio_url": f"https://example.com/{guid}.wav",
            }

        def chapter_subject(chapter: int) -> str:
            return f"Grundbog kapitel {chapter:02d} - Kapitel {chapter}"

        episodes = [
            make_episode(
                guid="tail-forord",
                title="[Lydbog] · Grundbog forord og resumé",
                description="Grundbog forord og resumé",
                published_at="2026-07-01T08:00:00+00:00",
                sort_tail=True,
            )
        ]

        for chapter in [2, 3, 5, 6, 7, 12, 13]:
            subject = chapter_subject(chapter)
            episodes.append(
                make_episode(
                    guid=f"tail-{chapter}",
                    title=f"[Lydbog] · {subject}",
                    description=subject,
                    published_at=f"2026-07-{chapter + 1:02d}T08:00:00+00:00",
                    sort_tail=True,
                )
            )

        for chapter in [1, 4, 8, 9, 10, 11, 14]:
            subject = chapter_subject(chapter)
            episodes.append(
                make_episode(
                    guid=f"week-{chapter}",
                    title=(
                        f"Semesteruge {chapter} · [Lydbog] · {subject} "
                        f"· (Uge {chapter} 01/01 - 07/01)"
                    ),
                    description=subject,
                    published_at=f"2026-02-{chapter + 1:02d}T08:00:00+00:00",
                    sort_tail=False,
                )
            )

        result = mod._synthesize_tail_grundbog_lydbog_block(
            episodes,
            {
                "tail_grundbog_lydbog": {
                    "enabled": True,
                    "include_forord": True,
                    "chapter_start": 1,
                    "chapter_end": 14,
                }
            },
        )

        tail_items = [item for item in result if item.get("sort_tail")]
        expected_keys = ["forord"] + [f"chapter:{chapter}" for chapter in range(1, 15)]
        self.assertEqual(
            [mod._extract_tail_grundbog_lydbog_key(item) for item in tail_items],
            expected_keys,
        )
        self.assertEqual(
            [item.get("sort_tail_index") for item in tail_items],
            list(range(15)),
        )
        for item in tail_items:
            self.assertTrue(item["title"].startswith("[Lydbog] · Grundbog"))
            self.assertNotIn("Semesteruge", item["title"])
            self.assertNotIn("(Uge ", item["title"])
            self.assertIn("#tail-grundbog-", item["guid"])

        guids = [item.get("guid") for item in result]
        self.assertEqual(len(guids), len(set(guids)))
        self.assertIn("week-1", guids)
        chapter_1_tail = next(
            item for item in tail_items if mod._extract_tail_grundbog_lydbog_key(item) == "chapter:1"
        )
        self.assertEqual(chapter_1_tail["guid"], "week-1#tail-grundbog-chapter-1")

    def test_synthesize_tail_grundbog_lydbog_can_drop_source_lydbog_items(self):
        mod = _load_feed_module()
        episodes = [
            dict(
                guid="chapter-1-short",
                title="Uge 1, Forelæsning 1 · Kort podcast · Grundbog kapitel 01 - Intro",
                description="Grundbog kapitel 01 - Intro",
                published_at="2026-02-02T08:00:00+00:00",
                sort_tail=False,
                is_tts=False,
                audio_url="https://example.test/audio/chapter-1-short.mp3",
            ),
            dict(
                guid="chapter-1-podcast",
                title="Uge 1, Forelæsning 1 · Podcast · Grundbog kapitel 01 - Intro",
                description="Grundbog kapitel 01 - Intro",
                published_at="2026-02-02T09:00:00+00:00",
                sort_tail=False,
                is_tts=False,
                audio_url="https://example.test/audio/chapter-1-podcast.mp3",
            ),
            dict(
                guid="chapter-1-lydbog",
                title="Uge 1, Forelæsning 1 · Lydbog · Grundbog kapitel 01 - Intro",
                description="Grundbog kapitel 01 - Intro",
                published_at="2026-02-02T10:00:00+00:00",
                sort_tail=False,
                is_tts=True,
                audio_url="https://example.test/audio/chapter-1-lydbog.mp3",
            ),
            dict(
                guid="chapter-2-short",
                title="Uge 1, Forelæsning 2 · Kort podcast · Grundbog kapitel 02 - Outro",
                description="Grundbog kapitel 02 - Outro",
                published_at="2026-02-03T08:00:00+00:00",
                sort_tail=False,
                is_tts=False,
                audio_url="https://example.test/audio/chapter-2-short.mp3",
            ),
            dict(
                guid="chapter-2-podcast",
                title="Uge 1, Forelæsning 2 · Podcast · Grundbog kapitel 02 - Outro",
                description="Grundbog kapitel 02 - Outro",
                published_at="2026-02-03T09:00:00+00:00",
                sort_tail=False,
                is_tts=False,
                audio_url="https://example.test/audio/chapter-2-podcast.mp3",
            ),
            dict(
                guid="chapter-2-lydbog",
                title="Uge 1, Forelæsning 2 · Lydbog · Grundbog kapitel 02 - Outro",
                description="Grundbog kapitel 02 - Outro",
                published_at="2026-02-03T10:00:00+00:00",
                sort_tail=False,
                is_tts=True,
                audio_url="https://example.test/audio/chapter-2-lydbog.mp3",
            ),
        ]

        result = mod._synthesize_tail_grundbog_lydbog_block(
            episodes,
            {
                "tail_grundbog_lydbog": {
                    "enabled": True,
                    "include_forord": False,
                    "chapter_start": 1,
                    "chapter_end": 1,
                    "drop_source_lydbog_items": True,
                }
            },
        )

        titles = [item["title"] for item in result]
        self.assertIn("Uge 1, Forelæsning 1 · Kort podcast · Grundbog kapitel 01 - Intro", titles)
        self.assertIn("Uge 1, Forelæsning 1 · Podcast · Grundbog kapitel 01 - Intro", titles)
        self.assertNotIn("Uge 1, Forelæsning 1 · Lydbog · Grundbog kapitel 01 - Intro", titles)
        self.assertIn("[Lydbog] · Grundbog kapitel 01 - Intro", titles)
        self.assertIn("Uge 1, Forelæsning 2 · Lydbog · Grundbog kapitel 02 - Outro", titles)

        tail_titles = [item["title"] for item in result if item.get("sort_tail")]
        self.assertEqual(tail_titles, ["[Lydbog] · Grundbog kapitel 01 - Intro"])
        chapter_1_audio = [
            item["audio_url"]
            for item in result
            if "Grundbog kapitel 01" in item["title"] and "Lydbog" in item["title"]
        ]
        self.assertEqual(chapter_1_audio, ["https://example.test/audio/chapter-1-lydbog.mp3"])

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

    def test_unassigned_sequence_items_stay_after_semester_weeks(self):
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

        self.assertGreater(chapter_02_date, autospec._earliest_rule_datetime)
        self.assertGreater(chapter_13_date, autospec._earliest_rule_datetime)
        self.assertGreater(chapter_02_date, chapter_13_date)
        self.assertIn(chapter_02_date.month, {7, 8})
        self.assertIn(chapter_13_date.month, {7, 8})

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
        derived = mod.parse_datetime(meta["published_at"])
        self.assertGreater(derived, autospec._earliest_rule_datetime)
        self.assertIn(derived.month, {7, 8})

    def test_generated_entry_maps_short_to_kort_podcast_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[ short ] W1L1 - Grundbog kapitel 01 [EN].mp3",
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
        self.assertNotIn("[Short]", episode["title"])
        self.assertNotIn("[Brief]", episode["title"])
        self.assertNotIn("[ brief ]", episode["title"])
        self.assertNotRegex(episode["title"], re.compile(r"\bW\d{1,2}L\d+\b"))
        self.assertEqual(episode["description"], "Kort podcast: Grundbog kapitel 01")

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
                "Alle kilder (undtagen slides)",
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

    def test_custom_title_blocks_render_compact_course_week_and_date_range(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "[Brief] W12L1 - Grundbog kapitel 14 - Perspektiver på personlighedspsykologi "
                "[EN].mp3"
            ),
            "createdTime": "2026-04-27T08:00:00+00:00",
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
                "title_blocks": ["course_week_lecture", "subject_or_type", "week_date_range"],
                "audio_category_prefix_position": "after_first_block",
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertEqual(
            episode["title"],
            (
                "U12F1 · [Kort podcast] · Grundbog kapitel 14 - Perspektiver på personlighedspsykologi "
                "· 27/04 - 03/05"
            ),
        )

    def test_custom_title_blocks_render_long_week_and_unbracketed_audio_category(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "[Brief] W12L1 - Grundbog kapitel 14 - Perspektiver på personlighedspsykologi "
                "[EN].mp3"
            ),
            "createdTime": "2026-04-27T08:00:00+00:00",
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
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["course_week_lecture_long", "subject"],
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "Lydbog",
                    "kort_podcast": "Kort podcast",
                    "podcast": "Podcast",
                },
                "description_prepend_semester_week_lecture": True,
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertEqual(
            episode["title"],
            "Uge 12, Forelæsning 1 · Kort podcast · Grundbog kapitel 14 - Perspektiver på personlighedspsykologi",
        )
        self.assertTrue(episode["description"].startswith("Semesteruge 13, Forelæsning 1\n\n"))

    def test_custom_title_blocks_render_compact_bracketed_short_variant_with_subject_alias(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "[Brief] W12L1 - Grundbog kapitel 8 - Personlighed, subjektivitet og historicitet "
                "[EN].mp3"
            ),
            "createdTime": "2026-04-27T08:00:00+00:00",
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
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["course_week_lecture", "subject"],
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "[Lydbog]",
                    "kort_podcast": "[Kort]",
                    "podcast": "",
                },
                "compact_grundbog_subjects": True,
                "title_subject_aliases": {
                    "Grundbog 8: Personlighed, subjektivitet og historicitet": "Grundbog 8: Historicitet",
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertEqual(episode["title"], "U12F1 · [Kort] · Grundbog 8: Historicitet")

    def test_custom_title_blocks_use_lecture_key_for_semester_week_when_configured(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": (
                "[Brief] W12L1 - Grundbog kapitel 14 - Perspektiver på personlighedspsykologi "
                "[EN].mp3"
            ),
            "createdTime": "2026-04-27T08:00:00+00:00",
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
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "semester_week_number_source": "lecture_key",
                "title_blocks": ["course_week_lecture_long", "subject"],
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "Lydbog",
                    "kort_podcast": "Kort podcast",
                    "podcast": "Podcast",
                },
                "description_prepend_semester_week_lecture": True,
                "enforce_week_label_consistency": True,
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertEqual(
            episode["title"],
            "Uge 12, Forelæsning 1 · Kort podcast · Grundbog kapitel 14 - Perspektiver på personlighedspsykologi",
        )
        self.assertTrue(episode["description"].startswith("Semesteruge 12, Forelæsning 1\n\n"))

    def test_enforce_week_label_consistency_raises_on_mismatch(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W12L1 - Elias (2000) [EN].mp3",
            "createdTime": "2026-04-27T08:00:00+00:00",
        }
        with self.assertRaisesRegex(ValueError, r"Week label mismatch"):
            mod.build_episode_entry(
                file_entry=file_entry,
                feed_config={
                    "title": "Personlighedspsykologi (EN)",
                    "link": "https://example.com",
                    "description": "Test feed",
                    "language": "en",
                    "semester_week_start_date": "2026-02-02",
                    "semester_week_label": "Semesteruge",
                    "semester_week_title_label": "Uge",
                    "semester_week_description_label": "Semesteruge",
                    "title_blocks": ["course_week_lecture_long", "subject"],
                    "description_prepend_semester_week_lecture": True,
                    "enforce_week_label_consistency": True,
                },
                overrides={},
                public_link_template="https://example.com/{file_id}",
                auto_meta={"week_reference_year": 2026},
                folder_names=["W12L1"],
            )

    def test_description_prepend_semester_week_lecture_prefixes_first_line(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W12L1 - Elias (2000) [EN].mp3",
            "createdTime": "2026-04-27T08:00:00+00:00",
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
                "description_prepend_semester_week_lecture": True,
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertTrue(episode["description"].startswith("Semesteruge 13, Forelæsning 1\n\n"))
        self.assertIn("Elias (2000)", episode["description"])

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

    def test_quiz_link_supports_short_flat_id_path(self):
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
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "http://64.226.79.109/q/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "1a2b3c4d.html",
                        "format": "html",
                    }
                }
            },
        )
        self.assertEqual(episode["link"], "http://64.226.79.109/q/1a2b3c4d.html")
        self.assertIn("http://64.226.79.109/q/1a2b3c4d.html", episode["description"])

    def test_description_quiz_block_renders_all_difficulties(self):
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
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "http://64.226.79.109/quizzes/personlighedspsykologi/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "W01L1/W01L1 - Foo-medium.html",
                        "format": "html",
                        "difficulty": "medium",
                        "links": [
                            {
                                "relative_path": "W01L1/W01L1 - Foo-easy.html",
                                "format": "html",
                                "difficulty": "easy",
                            },
                            {
                                "relative_path": "W01L1/W01L1 - Foo-medium.html",
                                "format": "html",
                                "difficulty": "medium",
                            },
                            {
                                "relative_path": "W01L1/W01L1 - Foo-hard.html",
                                "format": "html",
                                "difficulty": "hard",
                            },
                        ],
                    }
                }
            },
        )
        self.assertIn("\n\nQuizzes:\n", episode["description"])
        self.assertIn("- Easy: http://64.226.79.109/quizzes/personlighedspsykologi/", episode["description"])
        self.assertIn("- Medium: http://64.226.79.109/quizzes/personlighedspsykologi/", episode["description"])
        self.assertIn("- Hard: http://64.226.79.109/quizzes/personlighedspsykologi/", episode["description"])
        self.assertIn("Foo-easy.html", episode["description"])
        self.assertIn("Foo-medium.html", episode["description"])
        self.assertIn("Foo-hard.html", episode["description"])
        self.assertTrue(episode["link"].endswith("W01L1/W01L1%20-%20Foo-medium.html"))

    def test_description_quiz_block_and_summary_are_separated_by_blank_line(self):
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
                "description_prepend_semester_week_lecture": True,
                "description_blocks_by_kind": {
                    "reading": ["quiz", "reading_summary"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={
                "base_url": "http://64.226.79.109/q/",
                "labels": {
                    "multiple": "Quizzer",
                    "difficulty": {
                        "easy": "Let",
                        "medium": "Mellem",
                        "hard": "Svær",
                    },
                },
            },
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "a3b2075d.html",
                        "difficulty": "medium",
                        "links": [
                            {"relative_path": "70129442.html", "difficulty": "easy"},
                            {"relative_path": "a3b2075d.html", "difficulty": "medium"},
                            {"relative_path": "bfd24968.html", "difficulty": "hard"},
                        ],
                    }
                }
            },
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Bank introducerer narrative psykologier."],
                    }
                }
            },
            folder_names=["W01L1"],
        )
        self.assertIn("Semesteruge 1, Forelæsning 1\n\nQuizzer:", episode["description"])
        self.assertIn(
            "- Svær: http://64.226.79.109/q/bfd24968.html\n\nBank introducerer narrative psykologier.",
            episode["description"],
        )
        self.assertNotIn(" · Bank introducerer narrative psykologier.", episode["description"])

    def test_description_blank_line_marker_renders_visible_separator(self):
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
                "description_prepend_semester_week_lecture": True,
                "description_blank_line_marker": "·",
                "description_blocks_by_kind": {
                    "reading": ["quiz", "reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={
                "base_url": "http://64.226.79.109/q/",
                "labels": {
                    "multiple": "Quizzer",
                    "difficulty": {
                        "easy": "Let",
                        "medium": "Mellem",
                        "hard": "Svær",
                    },
                },
            },
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "a3b2075d.html",
                        "difficulty": "medium",
                        "links": [
                            {"relative_path": "70129442.html", "difficulty": "easy"},
                            {"relative_path": "a3b2075d.html", "difficulty": "medium"},
                            {"relative_path": "bfd24968.html", "difficulty": "hard"},
                        ],
                    }
                }
            },
            reading_summaries_cfg={"enabled_kinds": {"reading", "brief"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Bank introducerer narrative psykologier."],
                        "key_points": ["Point A", "Point B"],
                    }
                }
            },
            folder_names=["W01L1"],
        )
        self.assertIn("Semesteruge 1, Forelæsning 1\n·\nQuizzer:", episode["description"])
        self.assertIn(
            "- Svær: http://64.226.79.109/q/bfd24968.html\n·\nBank introducerer narrative psykologier.",
            episode["description"],
        )
        self.assertIn("Bank introducerer narrative psykologier.\n·\nKey points:", episode["description"])
        self.assertNotIn("\n\n", episode["description"])

    def test_description_text_link_block_renders_preview_url(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W09L1 - Foo [EN].mp3",
            "createdTime": "2026-03-30T08:00:00+00:00",
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
                "description_prepend_semester_week_lecture": True,
                "description_blank_line_marker": "·",
                "lecture_preview_link": {
                    "label": "Link til teksten",
                    "base_url": "https://freudd.dk/subjects/personlighedspsykologi",
                    "preview": True,
                },
                "description_blocks_by_kind": {
                    "reading": ["text_link", "quiz"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={
                "base_url": "http://64.226.79.109/q/",
                "labels": {
                    "multiple": "Quizzer",
                    "difficulty": {
                        "easy": "Let",
                        "medium": "Mellem",
                        "hard": "Svær",
                    },
                },
            },
            quiz_links={
                "by_name": {
                    "W09L1 - Foo [EN].mp3": {
                        "relative_path": "a3b2075d.html",
                        "difficulty": "medium",
                        "links": [
                            {"relative_path": "70129442.html", "difficulty": "easy"},
                            {"relative_path": "a3b2075d.html", "difficulty": "medium"},
                            {"relative_path": "bfd24968.html", "difficulty": "hard"},
                        ],
                    }
                }
            },
            folder_names=["W09L1"],
        )
        self.assertIn("Semesteruge 9, Forelæsning 1\n·\nLink til teksten:", episode["description"])
        self.assertIn(
            "https://freudd.dk/subjects/personlighedspsykologi?lecture=W09L1&preview=true",
            episode["description"],
        )
        self.assertIn("\n·\nQuizzer:", episode["description"])

    def test_description_footer_appends_to_episode_description(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Foo [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        footer = (
            "\n·\n·\n·\n"
            "Personlighedspsykologi: https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv\n"
            "Bioneuro: https://open.spotify.com/show/5QIHRkc1N6xuCqtnfmsPfN\n"
            "Socialpsykologi: https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP"
        )
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "description_footer": footer,
                "description_blocks": ["subject", "lecture"],
                "language": "en",
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(
            episode["description"],
            "Foo · Forelæsning 1" + footer,
        )

    def test_title_uses_quiz_link_key_when_file_name_lacks_week_lecture(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "Grundbog Kapitel 1.mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Bioneuro",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "audio_category_prefix_position": "after_first_block",
                "semester_week_number_source": "lecture_key",
                "title_blocks": ["course_week_lecture", "subject_or_type"],
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "https://freudd.dk/q/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Grundbog Kapitel 1 [EN] {type=audio lang=en format=deep-dive}.mp3": {
                        "relative_path": "abc12345.html",
                        "difficulty": "medium",
                    }
                }
            },
        )
        self.assertEqual(
            episode["title"],
            "U1F1 · [Podcast] · Grundbog Kapitel 1",
        )

    def test_title_uses_manual_source_folder_when_file_name_lacks_week_lecture(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "Grundbog Kapitel 1.mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Bioneuro",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "audio_category_prefix_position": "after_first_block",
                "semester_week_number_source": "lecture_key",
                "title_blocks": ["course_week_lecture", "subject_or_type"],
            },
            overrides={
                "by_name": {
                    "Grundbog Kapitel 1.mp3": {
                        "meta": {
                            "source_folder": "W01L1 Introduktion (2026-02-06)",
                        }
                    }
                }
            },
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(
            episode["title"],
            "U1F1 · [Podcast] · Grundbog Kapitel 1",
        )

    def test_by_id_override_can_supply_source_folder_and_quiz_link(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "drive-file-1",
            "name": "Unhelpful upload name.mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Bioneuro",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "audio_category_prefix_position": "after_first_block",
                "semester_week_number_source": "lecture_key",
                "title_blocks": ["course_week_lecture", "subject_or_type"],
            },
            overrides={
                "by_id": {
                    "drive-file-1": {
                        "link": "https://freudd.dk/q/f0657e64.html",
                        "meta": {
                            "source_folder": "W01L1 Introduktion (2026-02-06)",
                        },
                    }
                }
            },
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(
            episode["title"],
            "U1F1 · [Podcast] · Unhelpful upload name",
        )
        self.assertEqual(
            episode["link"],
            "https://freudd.dk/q/f0657e64.html",
        )

    def test_description_quiz_block_renders_all_difficulties_with_short_ids(self):
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
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            quiz_cfg={"base_url": "http://64.226.79.109/q/"},
            quiz_links={
                "by_name": {
                    "W01L1 - Foo [EN].mp3": {
                        "relative_path": "bbbb2222.html",
                        "format": "html",
                        "difficulty": "medium",
                        "links": [
                            {
                                "relative_path": "aaaa1111.html",
                                "format": "html",
                                "difficulty": "easy",
                            },
                            {
                                "relative_path": "bbbb2222.html",
                                "format": "html",
                                "difficulty": "medium",
                            },
                            {
                                "relative_path": "cccc3333.html",
                                "format": "html",
                                "difficulty": "hard",
                            },
                        ],
                    }
                }
            },
        )
        self.assertIn("\n\nQuizzes:\n", episode["description"])
        self.assertIn("- Easy: http://64.226.79.109/q/aaaa1111.html", episode["description"])
        self.assertIn("- Medium: http://64.226.79.109/q/bbbb2222.html", episode["description"])
        self.assertIn("- Hard: http://64.226.79.109/q/cccc3333.html", episode["description"])
        self.assertEqual(episode["link"], "http://64.226.79.109/q/bbbb2222.html")

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

    def test_build_episode_entry_marks_slide_descriptor_as_slide_kind(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Slide lecture: Forelæsning intro slides [EN].mp3",
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
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["episode_kind"], "slide")
        self.assertEqual(episode["title"], "[Podcast] Forelæsningsslides - Forelæsning intro slides")
        self.assertIn("Forelæsningsslides", episode["description"])
        self.assertIn("Forelæsning intro slides", episode["description"])

    def test_build_episode_entry_maps_slide_short_to_kort_podcast_forelaesningsslides(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[Short] W01L1 - Slide lecture: Forelæsning intro slides [EN].mp3",
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
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
        )
        self.assertEqual(episode["episode_kind"], "short")
        self.assertEqual(
            episode["title"],
            "[Kort podcast] Forelæsningsslides - Forelæsning intro slides",
        )
        self.assertIn("Kort podcast: Forelæsning intro slides", episode["description"])

    def test_build_episode_entry_rewrites_slide_title_to_forelaesningsslides_subject(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W10L2 - Slide lecture: 19. gang Sociokulturelle teorier [EN].mp3",
            "createdTime": "2026-04-07T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "semester_week_start_date": "2026-02-02",
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["course_week_lecture_long", "subject"],
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "Lydbog",
                    "kort_podcast": "Kort podcast",
                    "podcast": "Podcast",
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W10L2"],
        )
        self.assertEqual(
            episode["title"],
            "Uge 10, Forelæsning 2 · Podcast · Forelæsningsslides - Sociokulturelle teorier",
        )

    def test_build_episode_entry_renders_weekly_overview_with_custom_label_and_no_podcast_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W12L1 - Alle kilder (undtagen slides) [EN].mp3",
            "createdTime": "2026-04-27T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "semester_week_start_date": "2026-02-02",
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["course_week_lecture", "subject"],
                "title_blocks_by_kind": {"weekly_overview": ["course_week_lecture", "type_label"]},
                "weekly_overview_label": "Alle kilder",
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "[Lydbog]",
                    "kort_podcast": "[Kort]",
                    "podcast": "",
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W12L1"],
        )
        self.assertEqual(episode["title"], "U12F1 · Alle kilder")

    def test_build_episode_entry_renders_slide_title_with_custom_separator_and_no_podcast_prefix(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W10L2 - Slide lecture: 19. gang Sociokulturelle teorier [EN].mp3",
            "createdTime": "2026-04-07T08:00:00+00:00",
        }
        episode = mod.build_episode_entry(
            file_entry=file_entry,
            feed_config={
                "title": "Personlighedspsykologi (EN)",
                "link": "https://example.com",
                "description": "Test feed",
                "language": "en",
                "semester_week_start_date": "2026-02-02",
                "semester_week_title_label": "Uge",
                "semester_week_description_label": "Semesteruge",
                "title_blocks": ["course_week_lecture", "subject"],
                "audio_category_prefix_position": "after_first_block",
                "audio_category_prefixes": {
                    "lydbog": "[Lydbog]",
                    "kort_podcast": "[Kort]",
                    "podcast": "",
                },
                "slide_display_label": "Forelæsningsslides",
                "slide_subject_separator": " · ",
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            auto_meta={"week_reference_year": 2026},
            folder_names=["W10L2"],
        )
        self.assertEqual(
            episode["title"],
            "U10F2 · Forelæsningsslides · Sociokulturelle teorier",
        )

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

    def test_reading_summary_and_key_points_render_for_short(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "[Short] W01L1 - Foo [EN].mp3",
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
                    "short": ["reading_summary", "reading_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            reading_summaries_cfg={"enabled_kinds": {"reading", "short"}, "key_points_label": "Key points"},
            reading_summaries={
                "by_name": {
                    "[Short] W01L1 - Foo [EN].mp3": {
                        "summary_lines": ["Short summary 1", "Short summary 2"],
                        "key_points": ["Short A", "Short B", "Short C"],
                    }
                }
            },
        )
        self.assertIn("Short summary 1\nShort summary 2", episode["description"])
        self.assertIn("\n\nKey points:\n- Short A\n- Short B\n- Short C", episode["description"])

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

    def test_weekly_overview_summary_and_key_points_render_from_weekly_cache(self):
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
                    "weekly_overview": ["weekly_overview_summary", "weekly_overview_key_points"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            weekly_overview_summaries_cfg={"warn_on_incomplete_sources": True},
            weekly_overview_summaries={
                "by_name": {
                    "W01L1 - Alle kilder [EN].mp3": {
                        "summary_lines": ["Ugesamling linje 1", "Ugesamling linje 2"],
                        "key_points": ["Punkt A", "Punkt B", "Punkt C"],
                    }
                }
            },
        )
        self.assertIn("Ugesamling linje 1\nUgesamling linje 2", episode["description"])
        self.assertIn("\n\nKey points:\n- Punkt A\n- Punkt B\n- Punkt C", episode["description"])

    def test_weekly_overview_missing_summary_falls_back_to_descriptor_subject(self):
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
                    "weekly_overview": ["weekly_overview_summary"],
                },
            },
            overrides={},
            public_link_template="https://example.com/{file_id}",
            weekly_overview_summaries_cfg={"warn_on_incomplete_sources": True},
            weekly_overview_summaries={"by_name": {}},
        )
        self.assertTrue(episode["description"].startswith("Alle kilder"))

    def test_weekly_overview_warns_when_source_coverage_is_incomplete(self):
        mod = _load_feed_module()
        file_entry = {
            "id": "file1",
            "name": "W01L1 - Alle kilder [EN].mp3",
            "createdTime": "2026-02-02T08:00:00+00:00",
        }
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            mod.build_episode_entry(
                file_entry=file_entry,
                feed_config={
                    "title": "Personlighedspsykologi (EN)",
                    "link": "https://example.com",
                    "description": "Test feed",
                    "language": "en",
                    "description_blocks_by_kind": {
                        "weekly_overview": ["weekly_overview_summary"],
                    },
                },
                overrides={},
                public_link_template="https://example.com/{file_id}",
                weekly_overview_summaries_cfg={"warn_on_incomplete_sources": True},
                weekly_overview_summaries={
                    "by_name": {
                        "W01L1 - Alle kilder [EN].mp3": {
                            "summary_lines": ["Ugesamling linje"],
                            "meta": {
                                "source_count_expected": 5,
                                "source_count_covered": 3,
                            },
                        }
                    }
                },
            )
        self.assertIn("coverage gap", stderr.getvalue())

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
                "description_blocks": [
                    "text_link",
                    "reading_summary",
                    "reading_key_points",
                    "weekly_overview_summary",
                    "weekly_overview_key_points",
                ],
            }
        )

    def test_validate_feed_block_config_accepts_compact_week_title_blocks(self):
        mod = _load_feed_module()
        mod.validate_feed_block_config(
            {
                "title_blocks": ["course_week_lecture", "subject_or_type", "week_date_range"],
                "description_prepend_semester_week_lecture": True,
                "semester_week_number_source": "lecture_key",
                "enforce_week_label_consistency": True,
            }
        )

    def test_validate_feed_block_config_rejects_invalid_semester_week_number_source(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.semester_week_number_source has unknown source",
        ):
            mod.validate_feed_block_config({"semester_week_number_source": "calendar"})

    def test_validate_feed_block_config_rejects_non_bool_enforce_week_label_consistency(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.enforce_week_label_consistency must be a boolean",
        ):
            mod.validate_feed_block_config({"enforce_week_label_consistency": "yes"})

    def test_validate_feed_block_config_accepts_tail_grundbog_lydbog(self):
        mod = _load_feed_module()
        mod.validate_feed_block_config(
            {
                "tail_grundbog_lydbog": {
                    "enabled": True,
                    "include_forord": True,
                    "chapter_start": 1,
                    "chapter_end": 14,
                    "drop_source_lydbog_items": True,
                }
            }
        )

    def test_validate_feed_block_config_rejects_non_bool_drop_source_lydbog_items(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.tail_grundbog_lydbog\.drop_source_lydbog_items must be a boolean",
        ):
            mod.validate_feed_block_config(
                {
                    "tail_grundbog_lydbog": {
                        "enabled": True,
                        "drop_source_lydbog_items": "yes",
                    }
                }
            )

    def test_validate_feed_block_config_rejects_invalid_tail_grundbog_range(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.tail_grundbog_lydbog\.chapter_start must be less than or equal to chapter_end",
        ):
            mod.validate_feed_block_config(
                {
                    "tail_grundbog_lydbog": {
                        "enabled": True,
                        "chapter_start": 15,
                        "chapter_end": 14,
                    }
                }
            )

    def test_validate_feed_block_config_rejects_non_integer_tail_grundbog_chapter(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError,
            r"feed\.tail_grundbog_lydbog\.chapter_start must be an integer",
        ):
            mod.validate_feed_block_config(
                {
                    "tail_grundbog_lydbog": {
                        "enabled": True,
                        "chapter_start": "1",
                        "chapter_end": 14,
                    }
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

    def test_validate_feed_block_config_rejects_non_boolean_description_prepend(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.description_prepend_semester_week_lecture must be a boolean"
        ):
            mod.validate_feed_block_config({"description_prepend_semester_week_lecture": "yes"})

    def test_validate_feed_block_config_rejects_invalid_blank_line_marker(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.description_blank_line_marker must be a non-empty string"
        ):
            mod.validate_feed_block_config({"description_blank_line_marker": ""})

    def test_validate_feed_block_config_rejects_invalid_description_footer(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.description_footer must be a non-empty string"
        ):
            mod.validate_feed_block_config({"description_footer": ""})

    def test_validate_feed_block_config_rejects_invalid_audio_category_prefixes(self):
        mod = _load_feed_module()
        with self.assertRaisesRegex(
            ValueError, r"feed\.audio_category_prefixes has unknown key 'unknown'"
        ):
            mod.validate_feed_block_config(
                {"audio_category_prefixes": {"unknown": "Custom"}}
            )

    def test_validate_feed_block_config_accepts_empty_podcast_audio_category_prefix(self):
        mod = _load_feed_module()
        mod.validate_feed_block_config({"audio_category_prefixes": {"podcast": ""}})

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
