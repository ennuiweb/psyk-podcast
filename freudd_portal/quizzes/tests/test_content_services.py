from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from quizzes.content_services import build_subject_content_manifest, clear_content_service_caches
from quizzes.subject_services import clear_subject_service_caches


class SubjectContentManifestTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.primary_reading_file = root / "reading-primary.md"
        self.fallback_reading_file = root / "reading-fallback.md"
        self.quiz_links_file = root / "quiz_links.json"
        self.rss_file = root / "rss.xml"
        self.spotify_map_file = root / "spotify_map.json"
        self.manifest_file = root / "content_manifest.json"

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

        self.override = override_settings(
            FREUDD_READING_MASTER_KEY_PATH=self.primary_reading_file,
            FREUDD_READING_MASTER_KEY_FALLBACK_PATH=self.fallback_reading_file,
            QUIZ_LINKS_JSON_PATH=self.quiz_links_file,
            FREUDD_SUBJECT_FEED_RSS_PATH=self.rss_file,
            FREUDD_SUBJECT_SPOTIFY_MAP_PATH=self.spotify_map_file,
            FREUDD_SUBJECT_CONTENT_MANIFEST_PATH=self.manifest_file,
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

        reading = lecture["readings"][0]
        self.assertEqual(reading["reading_title"], "Lewis (1999)")
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
        self.assertFalse(manifest["warnings"])

    def test_build_manifest_hides_unmapped_spotify_podcasts_and_adds_warning(self) -> None:
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
        warnings = lecture.get("warnings") or []
        self.assertTrue(any("Spotify mapping missing for RSS item" in warning for warning in warnings))

    def test_build_manifest_reports_invalid_spotify_map_without_crash(self) -> None:
        self.spotify_map_file.write_text("{not-json", encoding="utf-8")
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(len(manifest["lectures"]), 2)
        self.assertTrue(any("Spotify map source could not be parsed" in warning for warning in manifest["warnings"]))
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 0)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 0)

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
        self.assertEqual(manifest["source_meta"]["reading_error"], "Reading-nøglen kunne ikke indlæses.")
