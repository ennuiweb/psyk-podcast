from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from quizzes.content_services import (
    build_subject_content_manifest,
    clear_content_service_caches,
    load_subject_content_manifest,
    write_subject_content_manifest,
)
from quizzes.subject_services import clear_subject_service_caches


class SubjectContentManifestTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.subjects_file = root / "subjects.json"
        self.primary_reading_file = root / "reading-primary.md"
        self.fallback_reading_file = root / "reading-fallback.md"
        self.quiz_links_file = root / "quiz_links.json"
        self.rss_file = root / "rss.xml"
        self.spotify_map_file = root / "spotify_map.json"
        self.manifest_file = root / "content_manifest.json"
        self.slides_catalog_file = root / "slides_catalog.json"

        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- Lewis (1999) \u2192 Lewis (1999).pdf",
                    "",
                    "**W01L2 Personality assessment (Forelaesning 2, 2026-02-03)**",
                    "- Mayer & Bryan (2024) \u2192 Mayer & Bryan (2024).pdf",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(self.primary_reading_file.read_text(encoding="utf-8"), encoding="utf-8")
        self.quiz_links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W01L1 - Lewis (1999) [EN].mp3": {
                            "relative_path": "aaaaaaaa.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                            "links": [
                                {
                                    "relative_path": "aaaaaaaa.html",
                                    "difficulty": "easy",
                                    "format": "html",
                                    "subject_slug": "personlighedspsykologi",
                                },
                                {
                                    "relative_path": "bbbbbbbb.html",
                                    "difficulty": "medium",
                                    "format": "html",
                                    "subject_slug": "personlighedspsykologi",
                                },
                            ],
                        },
                        "W01L1 - Alle kilder [EN].mp3": {
                            "relative_path": "cccccccc.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/lewis.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/all-sources.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.default_rss_payload = self.rss_file.read_text(encoding="utf-8")
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02": "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
                        "U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.subjects_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subjects": [
                        {
                            "slug": "personlighedspsykologi",
                            "title": "Personlighedspsykologi",
                            "description": "Personlighedspsykologi F26",
                            "active": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.slides_catalog_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "slides": [],
                    "unresolved": [],
                }
            ),
            encoding="utf-8",
        )

        self.override = override_settings(
            FREUDD_SUBJECTS_JSON_PATH=self.subjects_file,
            FREUDD_READING_MASTER_KEY_PATH=self.primary_reading_file,
            FREUDD_READING_MASTER_KEY_FALLBACK_PATH=self.fallback_reading_file,
            QUIZ_LINKS_JSON_PATH=self.quiz_links_file,
            FREUDD_SUBJECT_FEED_RSS_PATH=self.rss_file,
            FREUDD_SUBJECT_SPOTIFY_MAP_PATH=self.spotify_map_file,
            FREUDD_SUBJECT_CONTENT_MANIFEST_PATH=self.manifest_file,
            FREUDD_SUBJECT_SLIDES_CATALOG_PATH=self.slides_catalog_file,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        clear_subject_service_caches()
        self.addCleanup(clear_subject_service_caches)
        clear_content_service_caches()
        self.addCleanup(clear_content_service_caches)

    def test_build_manifest_maps_reading_and_lecture_assets(self) -> None:
        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(manifest["subject_slug"], "personlighedspsykologi")
        self.assertEqual(len(manifest["lectures"]), 2)

        lecture = manifest["lectures"][0]
        self.assertEqual(lecture["lecture_key"], "W01L1")
        self.assertEqual(len(lecture["lecture_assets"]["quizzes"]), 1)
        self.assertEqual(lecture["lecture_assets"]["quizzes"][0]["quiz_id"], "cccccccc")
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["platform"], "spotify")
        self.assertEqual(
            lecture["lecture_assets"]["podcasts"][0]["url"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(
            lecture["lecture_assets"]["podcasts"][0]["source_audio_url"],
            "https://example.test/audio/all-sources.mp3",
        )
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["duration_label"], "")
        self.assertIsNone(lecture["lecture_assets"]["podcasts"][0]["duration_seconds"])

        reading = lecture["readings"][0]
        self.assertEqual(reading["reading_title"], "Lewis (1999)")
        self.assertEqual(reading["source_filename"], "Lewis (1999).pdf")
        self.assertEqual(len(reading["assets"]["quizzes"]), 2)
        self.assertEqual({item["quiz_id"] for item in reading["assets"]["quizzes"]}, {"aaaaaaaa", "bbbbbbbb"})
        self.assertEqual(len(reading["assets"]["podcasts"]), 1)
        self.assertEqual(reading["assets"]["podcasts"][0]["platform"], "spotify")
        self.assertEqual(
            reading["assets"]["podcasts"][0]["url"],
            "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
        )
        self.assertEqual(
            reading["assets"]["podcasts"][0]["source_audio_url"],
            "https://example.test/audio/lewis.mp3",
        )
        self.assertEqual(reading["assets"]["podcasts"][0]["duration_label"], "")
        self.assertIsNone(reading["assets"]["podcasts"][0]["duration_seconds"])
        self.assertFalse(manifest["warnings"])

    def test_build_manifest_maps_slide_assets_from_explicit_slide_descriptor(self) -> None:
        self.slides_catalog_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "slides": [
                        {
                            "slide_key": "w01l1-lecture-intro-slides",
                            "lecture_key": "W01L1",
                            "subcategory": "lecture",
                            "title": "Forelæsning intro slides",
                            "source_filename": "Forelaesning intro slides.pdf",
                            "relative_path": "W01L1/lecture/Forelaesning intro slides.pdf",
                        }
                    ],
                    "unresolved": [],
                }
            ),
            encoding="utf-8",
        )
        self.quiz_links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W01L1 - Slide lecture: Forelæsning intro slides [EN].mp3": {
                            "relative_path": "dddddddd.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Slide lecture: Forelæsning intro slides · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 11:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/slide-intro.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "U1F1 · [Podcast] · Slide lecture: Forelæsning intro slides · 02/02 - 08/02": "https://open.spotify.com/episode/6m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["slides"]), 1)
        slide = lecture["slides"][0]
        self.assertEqual(slide["slide_key"], "w01l1-lecture-intro-slides")
        self.assertEqual(len(slide["assets"]["quizzes"]), 1)
        self.assertEqual(slide["assets"]["quizzes"][0]["quiz_id"], "dddddddd")
        self.assertEqual(len(slide["assets"]["podcasts"]), 1)
        self.assertEqual(
            slide["assets"]["podcasts"][0]["source_audio_url"],
            "https://example.test/audio/slide-intro.mp3",
        )

    def test_build_manifest_source_meta_is_stable_and_omits_generated_at(self) -> None:
        manifest = build_subject_content_manifest("personlighedspsykologi")

        source_meta = manifest["source_meta"]
        self.assertNotIn("generated_at", source_meta)
        self.assertEqual(source_meta["reading_master_path"], str(self.primary_reading_file))
        self.assertEqual(source_meta["reading_fallback_path"], str(self.fallback_reading_file))
        self.assertEqual(source_meta["reading_source_used"], str(self.primary_reading_file))
        self.assertEqual(source_meta["quiz_links_path"], str(self.quiz_links_file))
        self.assertEqual(source_meta["rss_path"], str(self.rss_file))
        self.assertEqual(source_meta["spotify_map_path"], str(self.spotify_map_file))
        self.assertEqual(source_meta["slides_catalog_path"], str(self.slides_catalog_file))

    def test_build_manifest_sets_source_filename_none_for_missing_readings(self) -> None:
        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- MISSING: Lewis (1999)",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(
            self.primary_reading_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        reading = manifest["lectures"][0]["readings"][0]
        self.assertTrue(reading["is_missing"])
        self.assertIsNone(reading["source_filename"])

    def test_build_manifest_sanitizes_source_filename_path_separators(self) -> None:
        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- Freud, S. (1984/1905) \u2192 W01L1 Freud, S. (1984/1905).pdf",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(
            self.primary_reading_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        reading = manifest["lectures"][0]["readings"][0]
        self.assertEqual(reading["source_filename"], "W01L1 Freud, S. (1984-1905).pdf")

    def test_build_manifest_shortens_ovelseshold_note_in_reading_title(self) -> None:
        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- Gammelgaard (2010) (tekst for Øvelseshold) \u2192 W01L1 Gammelgaard (2010).pdf",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(
            self.primary_reading_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        reading = manifest["lectures"][0]["readings"][0]
        self.assertEqual(reading["reading_title"], "Gammelgaard (2010) (Øvelseshold)")

    def test_build_manifest_maps_citation_descriptors_and_source_aliases(self) -> None:
        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- Foucault (1997) → Excerpt-foucault.pdf",
                    "- Andkjær Olsen & Køppe (1991a + 1991b) → Seminar-reading.pdf",
                    "- Zeuthen & Køppe (2014) → Grundbog kapitel 07 - Nyere psykoanalytiske teorier.pdf",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(
            self.primary_reading_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.quiz_links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W1L1 - Foucault, M. (1997). s. 281-301 [EN].mp3": {
                            "relative_path": "11111111.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        },
                        "W1L1 - Andkjær Olsen & Køppe (1991a og b) [EN].mp3": {
                            "relative_path": "22222222.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        },
                        "W1L1 - Grundbog kapitel 07 - Nyere psykoanalytiske teorier [EN].mp3": {
                            "relative_path": "33333333.html",
                            "difficulty": "medium",
                            "subject_slug": "personlighedspsykologi",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {},
                }
            ),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["quizzes"]), 0)
        quizzes_by_reading = {
            str(reading["reading_title"]): {str(asset["quiz_id"]) for asset in reading["assets"]["quizzes"]}
            for reading in lecture["readings"]
        }
        self.assertEqual(quizzes_by_reading["Foucault (1997)"], {"11111111"})
        self.assertEqual(quizzes_by_reading["Andkjær Olsen & Køppe (1991a + 1991b)"], {"22222222"})
        self.assertEqual(quizzes_by_reading["Zeuthen & Køppe (2014)"], {"33333333"})
        self.assertFalse(lecture["warnings"])

    def test_build_manifest_disambiguates_duplicate_reading_titles(self) -> None:
        self.primary_reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Intro (Forelaesning 1, 2026-02-02)**",
                    "- Exercise text \u2192 W01L1 X Alpha.pdf",
                    "- Exercise text \u2192 W01L1 X Beta.pdf",
                ]
            ),
            encoding="utf-8",
        )
        self.fallback_reading_file.write_text(
            self.primary_reading_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        readings = manifest["lectures"][0]["readings"]
        reading_keys = [str(item["reading_key"]) for item in readings]
        self.assertEqual(len(reading_keys), 2)
        self.assertEqual(len(set(reading_keys)), 2)
        self.assertFalse(reading_keys[0].endswith("-2"))
        self.assertTrue(reading_keys[1].endswith("-2"))

    def test_build_manifest_extracts_podcast_duration_when_present(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\" xmlns:itunes=\"http://www.itunes.com/dtds/podcast-1.0.dtd\">",
                    "<channel>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    "<itunes:duration>00:15:00</itunes:duration>",
                    '<enclosure url="https://example.test/audio/all-sources.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture_podcast = manifest["lectures"][0]["lecture_assets"]["podcasts"][0]
        self.assertEqual(lecture_podcast["duration_seconds"], 900)
        self.assertEqual(lecture_podcast["duration_label"], "15 min")

    def test_build_manifest_skips_podcast_when_spotify_episode_mapping_is_missing(self) -> None:
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02": "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 0)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 1)
        self.assertEqual(lecture["readings"][0]["assets"]["podcasts"][0]["platform"], "spotify")
        warnings = lecture.get("warnings") or []
        self.assertTrue(
            any("Spotify episode mapping missing for RSS item; skipping podcast asset" in warning for warning in warnings)
        )

    def test_build_manifest_rejects_non_episode_urls_in_spotify_map(self) -> None:
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02": (
                            "https://open.spotify.com/search/U1F1%20%C2%B7%20%5BPodcast%5D%20%C2%B7%20Lewis%20%281999%29%20%C2%B7%2002%2F02%20-%2008%2F02/episodes"
                        ),
                        "U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02": (
                            "https://open.spotify.com/search/U1F1%20%C2%B7%20%5BPodcast%5D%20%C2%B7%20Alle%20kilder%20%C2%B7%2002%2F02%20-%2008%2F02/episodes"
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 0)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 0)
        warnings = lecture.get("warnings") or []
        self.assertTrue(
            any("Spotify episode mapping missing for RSS item; skipping podcast asset" in warning for warning in warnings)
        )
        self.assertTrue(
            any("Spotify map URL must be an episode URL for title" in warning for warning in manifest["warnings"])
        )

    def test_build_manifest_reports_invalid_spotify_map_without_crash(self) -> None:
        self.spotify_map_file.write_text("{not-json", encoding="utf-8")
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(len(manifest["lectures"]), 2)
        self.assertTrue(any("Spotify map source could not be parsed" in warning for warning in manifest["warnings"]))
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 0)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 0)

    def test_build_manifest_parses_danish_lecture_hints_in_rss_titles(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>Uge 1, Forelæsning 1 · Podcast · Alle kilder</title>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/all-sources.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "Uge 1, Forelæsning 1 · Podcast · Alle kilder": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["platform"], "spotify")
        self.assertFalse(any("unknown lecture mapping" in warning for warning in manifest["warnings"]))

    def test_build_manifest_maps_reading_podcast_via_quiz_link_when_title_lacks_lecture_hint(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>[Podcast] · Lewis summary</title>",
                    "<link>https://freudd.dk/q/bbbbbbbb.html</link>",
                    "<pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/lewis-summary.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "[Podcast] · Lewis summary": "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 0)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 1)
        self.assertEqual(
            lecture["readings"][0]["assets"]["podcasts"][0]["source_audio_url"],
            "https://example.test/audio/lewis-summary.mp3",
        )
        self.assertFalse(any("unknown lecture mapping" in warning for warning in manifest["warnings"]))

    def test_build_manifest_maps_lecture_podcast_via_quiz_link_when_title_lacks_lecture_hint(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>[Podcast] · Alle kilder</title>",
                    "<link>https://freudd.dk/q/cccccccc.html</link>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/all-sources.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "[Podcast] · Alle kilder": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["platform"], "spotify")
        self.assertFalse(any("unknown lecture mapping" in warning for warning in manifest["warnings"]))

    def test_build_manifest_deduplicates_weekly_overview_title_variants(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>Uge 1, Forelæsning 1 · Podcast · Alle kilder</title>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/all-sources-older.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "<item>",
                    "<title>Uge 1, Forelæsning 1 · Podcast · Alle kilder (undtagen slides)</title>",
                    "<pubDate>Mon, 02 Feb 2026 09:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/all-sources-newer.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": {
                        "Uge 1, Forelæsning 1 · Podcast · Alle kilder": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                        "Uge 1, Forelæsning 1 · Podcast · Alle kilder (undtagen slides)": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    },
                }
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(
            lecture["lecture_assets"]["podcasts"][0]["source_audio_url"],
            "https://example.test/audio/all-sources-newer.mp3",
        )
        warnings = lecture.get("warnings") or []
        self.assertTrue(any("Duplicate podcast asset detected" in warning for warning in warnings))

    def test_build_manifest_deduplicates_duplicate_reading_podcasts_and_keeps_newest(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/lewis-older.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Lewis (1999) · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 11:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/audio/lewis-newer.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        lecture = manifest["lectures"][0]
        reading_podcasts = lecture["readings"][0]["assets"]["podcasts"]
        self.assertEqual(len(reading_podcasts), 1)
        self.assertEqual(reading_podcasts[0]["source_audio_url"], "https://example.test/audio/lewis-newer.mp3")
        warnings = lecture.get("warnings") or []
        self.assertTrue(any("Duplicate podcast asset detected" in warning for warning in warnings))

    def test_build_manifest_uses_fallback_when_primary_missing(self) -> None:
        self.primary_reading_file.unlink()
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(len(manifest["lectures"]), 2)
        self.assertTrue(manifest["source_meta"]["reading_fallback_used"])
        self.assertIsNone(manifest["source_meta"]["reading_error"])

    def test_build_manifest_reports_error_when_both_reading_sources_missing(self) -> None:
        self.primary_reading_file.unlink()
        self.fallback_reading_file.unlink()
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(manifest["lectures"], [])
        self.assertEqual(manifest["source_meta"]["reading_error"], "Tekst-nøglen kunne ikke indlæses.")

    def test_build_manifest_uses_subject_specific_paths_from_catalog(self) -> None:
        subject_root = Path(self.temp_dir.name) / "bioneuro"
        subject_root.mkdir(parents=True, exist_ok=True)
        reading_file = subject_root / "reading-file-key.md"
        fallback_file = subject_root / "reading-file-key-fallback.md"
        quiz_links_file = subject_root / "quiz_links.json"
        rss_file = subject_root / "rss.xml"
        spotify_map_file = subject_root / "spotify_map.json"
        manifest_file = subject_root / "content_manifest.json"

        reading_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Bioneuro intro**",
                    "- Neural foundations \u2192 Neural foundations.pdf",
                ]
            ),
            encoding="utf-8",
        )
        fallback_file.write_text(reading_file.read_text(encoding="utf-8"), encoding="utf-8")
        quiz_links_file.write_text(json.dumps({"version": 1, "subject_slug": "bioneuro", "by_name": {}}), encoding="utf-8")
        rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        spotify_map_file.write_text(
            json.dumps({"version": 1, "subject_slug": "bioneuro", "by_rss_title": {}}),
            encoding="utf-8",
        )
        self.subjects_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subjects": [
                        {
                            "slug": "personlighedspsykologi",
                            "title": "Personlighedspsykologi",
                            "description": "Personlighedspsykologi F26",
                            "active": True,
                        },
                        {
                            "slug": "bioneuro",
                            "title": "Bioneuro",
                            "description": "Bioneuro F26",
                            "active": True,
                            "paths": {
                                "reading_master_path": str(reading_file),
                                "reading_fallback_path": str(fallback_file),
                                "quiz_links_path": str(quiz_links_file),
                                "feed_rss_path": str(rss_file),
                                "spotify_map_path": str(spotify_map_file),
                                "content_manifest_path": str(manifest_file),
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        clear_subject_service_caches()
        clear_content_service_caches()

        manifest = build_subject_content_manifest("bioneuro")
        self.assertEqual(manifest["subject_slug"], "bioneuro")
        self.assertEqual(len(manifest["lectures"]), 1)
        self.assertEqual(manifest["lectures"][0]["readings"][0]["source_filename"], "Neural foundations.pdf")

        written_path = write_subject_content_manifest(manifest)
        self.assertEqual(written_path, manifest_file)
        self.assertTrue(manifest_file.exists())

    def test_load_manifest_rebuilds_when_rss_is_newer_than_manifest(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )
        stale_manifest = build_subject_content_manifest("personlighedspsykologi")
        stale_count = self._podcast_count(stale_manifest)
        self.assertEqual(stale_count, 0)
        write_subject_content_manifest(stale_manifest, path=self.manifest_file)

        clear_content_service_caches()
        time.sleep(0.02)
        self.rss_file.write_text(self.default_rss_payload, encoding="utf-8")

        refreshed = load_subject_content_manifest("personlighedspsykologi")
        refreshed_count = self._podcast_count(refreshed)
        self.assertGreater(refreshed_count, 0)
        persisted = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(self._podcast_count(persisted), refreshed_count)

    def test_load_manifest_keeps_existing_payload_when_stale_rebuild_raises(self) -> None:
        manifest = build_subject_content_manifest("personlighedspsykologi")
        expected_count = self._podcast_count(manifest)
        self.assertGreater(expected_count, 0)
        write_subject_content_manifest(manifest, path=self.manifest_file)

        clear_content_service_caches()
        time.sleep(0.02)
        self.rss_file.write_text(self.default_rss_payload, encoding="utf-8")
        with patch("quizzes.content_services.build_subject_content_manifest", side_effect=RuntimeError("boom")):
            loaded = load_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(self._podcast_count(loaded), expected_count)

    @staticmethod
    def _podcast_count(manifest: dict[str, object]) -> int:
        total = 0
        lectures = manifest.get("lectures")
        if not isinstance(lectures, list):
            return 0
        for lecture in lectures:
            if not isinstance(lecture, dict):
                continue
            lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
            total += len(lecture_assets.get("podcasts") or [])
            readings = lecture.get("readings")
            if not isinstance(readings, list):
                continue
            for reading in readings:
                if not isinstance(reading, dict):
                    continue
                assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
                total += len(assets.get("podcasts") or [])
        return total
