from __future__ import annotations

import unittest

from spotify_transcripts.normalizer import TranscriptSchemaError, normalize_transcript_payload


class NormalizerTests(unittest.TestCase):
    def test_normalize_transcript_payload_builds_segments_and_vtt(self) -> None:
        normalized = normalize_transcript_payload(
            episode_key="ep-a",
            title="Episode A",
            spotify_url="https://open.spotify.com/episode/abc123",
            raw_payload={
                "episodeName": "Episode A",
                "language": "de",
                "section": [
                    {
                        "startMs": 0,
                        "title": {"title": "Intro"},
                        "text": {"sentence": {"text": "Hello world"}},
                    },
                    {
                        "startMs": 2000,
                        "text": {"sentence": {"text": "Another segment"}},
                    },
                ],
            },
        )

        self.assertEqual(normalized.payload["segment_count"], 2)
        self.assertEqual(normalized.payload["segments"][0]["text"], "Hello world")
        self.assertIn("WEBVTT", normalized.vtt)
        self.assertIn("00:00:00.000 --> 00:00:02.000", normalized.vtt)

    def test_normalize_transcript_payload_raises_for_missing_sections(self) -> None:
        with self.assertRaises(TranscriptSchemaError):
            normalize_transcript_payload(
                episode_key="ep-a",
                title="Episode A",
                spotify_url="https://open.spotify.com/episode/abc123",
                raw_payload={},
            )
