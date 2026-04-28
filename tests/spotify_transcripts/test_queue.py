from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spotify_transcripts.constants import STATUS_DOWNLOADED, STATUS_NO_TRANSCRIPT, STATUS_UNKNOWN_FAILURE
from spotify_transcripts.discovery import load_show_sources
from spotify_transcripts.models import AcquisitionResult
from spotify_transcripts.service import build_show_queue, run_show_queue
from spotify_transcripts.store import TranscriptStore


class QueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(self.temp_dir.name)
        self.show_root = self.repo_root / "shows" / "demo-show"
        self.show_root.mkdir(parents=True, exist_ok=True)
        (self.show_root / "episode_inventory.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "demo",
                    "episodes": [
                        {"episode_key": "ep-a", "title": "Episode A"},
                        {"episode_key": "ep-b", "title": "Episode B"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.show_root / "spotify_map.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "subject_slug": "demo",
                    "by_episode_key": {
                        "ep-a": "https://open.spotify.com/episode/aaaaaaaaaaaaaaaa",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.sources = load_show_sources(repo_root=self.repo_root, show_slug="demo-show")
        self.store = TranscriptStore(self.show_root)

    def test_build_show_queue_marks_mapped_and_unmapped_entries(self) -> None:
        payload = build_show_queue(sources=self.sources, store=self.store)
        self.assertEqual(payload["summary"]["pending"], 1)
        self.assertEqual(payload["summary"]["blocked_missing_mapping"], 1)

    def test_run_show_queue_updates_download_and_failure_statuses(self) -> None:
        responses = iter(
            [
                AcquisitionResult(
                    status=STATUS_DOWNLOADED,
                    payload={
                        "episodeName": "Episode A",
                        "section": [
                            {
                                "startMs": 0,
                                "text": {"sentence": {"text": "Hello"}},
                            }
                        ],
                    },
                ),
            ]
        )

        def downloader(**_: object) -> AcquisitionResult:
            return next(responses)

        payload = run_show_queue(
            sources=self.sources,
            store=self.store,
            downloader=downloader,
            limit=1,
        )
        self.assertEqual(payload["attempted"], 1)
        self.assertEqual(payload["downloaded"], 1)
        queue = self.store.load_queue()
        entries = {entry["episode_key"]: entry for entry in queue["entries"]}
        self.assertEqual(entries["ep-a"]["queue_status"], "done_downloaded")
        self.assertEqual(entries["ep-b"]["queue_status"], "blocked_missing_mapping")

    def test_run_show_queue_marks_failed_pending_entries(self) -> None:
        def failing_downloader(**_: object) -> AcquisitionResult:
            return AcquisitionResult(status=STATUS_NO_TRANSCRIPT, payload=None, error="no transcript")

        payload = run_show_queue(
            sources=self.sources,
            store=self.store,
            downloader=failing_downloader,
            limit=1,
        )
        self.assertEqual(payload["attempted"], 1)
        queue = self.store.load_queue()
        entries = {entry["episode_key"]: entry for entry in queue["entries"]}
        self.assertEqual(entries["ep-a"]["queue_status"], "failed")

    def test_run_show_queue_catches_downloader_exceptions(self) -> None:
        def crashing_downloader(**_: object) -> AcquisitionResult:
            raise RuntimeError("browser vanished")

        payload = run_show_queue(
            sources=self.sources,
            store=self.store,
            downloader=crashing_downloader,
            limit=1,
        )
        self.assertEqual(payload["attempted"], 1)
        self.assertEqual(payload["failed"], 1)
        manifest = self.store.load_manifest()
        entries = {entry["episode_key"]: entry for entry in manifest["episodes"]}
        self.assertEqual(entries["ep-a"]["status"], STATUS_UNKNOWN_FAILURE)
        self.assertEqual(entries["ep-a"]["last_attempt_status"], STATUS_UNKNOWN_FAILURE)
        self.assertIn("browser vanished", entries["ep-a"]["last_error"])

    def test_run_show_queue_retries_retryable_failures(self) -> None:
        calls = {"count": 0}

        def flaky_downloader(**_: object) -> AcquisitionResult:
            calls["count"] += 1
            if calls["count"] == 1:
                return AcquisitionResult(status=STATUS_UNKNOWN_FAILURE, payload=None, error="transient")
            return AcquisitionResult(
                status=STATUS_DOWNLOADED,
                payload={
                    "episodeName": "Episode A",
                    "section": [
                        {
                            "startMs": 0,
                            "text": {"sentence": {"text": "Hello"}},
                        }
                    ],
                },
            )

        payload = run_show_queue(
            sources=self.sources,
            store=self.store,
            downloader=flaky_downloader,
            limit=1,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        self.assertEqual(payload["downloaded"], 1)
        self.assertEqual(calls["count"], 2)
        manifest = self.store.load_manifest()
        entries = {entry["episode_key"]: entry for entry in manifest["episodes"]}
        self.assertEqual(entries["ep-a"]["attempt_count"], 2)
        self.assertEqual(entries["ep-a"]["consecutive_failure_count"], 0)
