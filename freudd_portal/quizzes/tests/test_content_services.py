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
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["duration_label"], "")
        self.assertIsNone(lecture["lecture_assets"]["podcasts"][0]["duration_seconds"])

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
        self.assertEqual(reading["assets"]["podcasts"][0]["duration_label"], "")
        self.assertIsNone(reading["assets"]["podcasts"][0]["duration_seconds"])
        self.assertFalse(manifest["warnings"])

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

    def test_build_manifest_uses_spotify_search_fallback_when_mapping_missing(self) -> None:
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
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["platform"], "spotify_search")
        self.assertIn("https://open.spotify.com/search/", lecture["lecture_assets"]["podcasts"][0]["url"])
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 1)
        self.assertEqual(lecture["readings"][0]["assets"]["podcasts"][0]["platform"], "spotify")
        warnings = lecture.get("warnings") or []
        self.assertTrue(
            any("Spotify mapping missing for RSS item; using Spotify search fallback" in warning for warning in warnings)
        )

    def test_build_manifest_reports_invalid_spotify_map_without_crash(self) -> None:
        self.spotify_map_file.write_text("{not-json", encoding="utf-8")
        clear_content_service_caches()

        manifest = build_subject_content_manifest("personlighedspsykologi")
        self.assertEqual(len(manifest["lectures"]), 2)
        self.assertTrue(any("Spotify map source could not be parsed" in warning for warning in manifest["warnings"]))
        lecture = manifest["lectures"][0]
        self.assertEqual(len(lecture["lecture_assets"]["podcasts"]), 1)
        self.assertEqual(len(lecture["readings"][0]["assets"]["podcasts"]), 1)
        self.assertEqual(lecture["lecture_assets"]["podcasts"][0]["platform"], "spotify_search")
        self.assertEqual(lecture["readings"][0]["assets"]["podcasts"][0]["platform"], "spotify_search")

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
