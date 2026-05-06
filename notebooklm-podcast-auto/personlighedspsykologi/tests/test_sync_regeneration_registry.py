import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "sync_regeneration_registry.py"
    )
    spec = importlib.util.spec_from_file_location("sync_regeneration_registry", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncRegenerationRegistryTests(unittest.TestCase):
    def test_logical_episode_id_distinguishes_prompt_types(self):
        mod = _load_module()

        self.assertEqual(
            mod.logical_episode_id("W11L2 - Alle kilder (undtagen slides) [EN] {type=audio hash=abc}.mp3"),
            "weekly_readings_only__w11l2__alle_kilder_undtagen_slides_en",
        )
        self.assertEqual(
            mod.logical_episode_id("W10L2 - Slide lecture: 19. gang Sociokulturelle teorier [EN] {type=audio hash=abc}.mp3"),
            "single_slide__w10l2__19_gang_sociokulturelle_teorier_en",
        )
        self.assertEqual(
            mod.logical_episode_id("[Short] W11L2 - Grundbog kapitel 9 - Narrative teorier [EN] {type=audio hash=abc}.mp3"),
            "short__w11l2__grundbog_kapitel_9_narrative_teorier_en",
        )
        self.assertEqual(
            mod.logical_episode_id("[TTS] W11L2 - Grundbog kapitel 09 - Narrative teorier {type=tts date=2026-02-14}.mp3"),
            "tts__w11l2__grundbog_kapitel_09_narrative_teorier",
        )

    def test_parse_config_tags_reads_hash(self):
        mod = _load_module()

        parsed = mod.parse_config_tags(
            "W11L2 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
        )

        self.assertEqual(parsed["type"], "audio")
        self.assertEqual(parsed["lang"], "en")
        self.assertEqual(parsed["hash"], "fa9adbcf")

    def test_sync_registry_preserves_existing_b_variant_and_updates_a(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory_path = root / "episode_inventory.json"
            registry_path = root / "regeneration_registry.json"
            inventory_path.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "episode_key": "drive-a",
                                "title": "U11F2 · Grundbog",
                                "source_name": (
                                    "W11L2 - Grundbog kapitel 9 - Narrative teorier [EN] "
                                    "{type=audio lang=en format=deep-dive length=long hash=oldhash}.mp3"
                                ),
                                "published_at": "2026-04-01T10:00:00+02:00",
                                "audio_url": "https://example.com/a.mp3",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            registry_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "logical_episode_id": "single_reading__w11l2__grundbog_kapitel_9_narrative_teorier_en",
                                "prompt_type": "single_reading",
                                "lecture_key": "W11L2",
                                "active_variant": "B",
                                "rollout": {
                                    "campaign": "prompt-rollout-2026-04",
                                    "in_scope": True,
                                    "state": "b_reviewed",
                                    "notes": ["ready"],
                                },
                                "variants": {
                                    "A": {"status": "published", "config_hash": "stale"},
                                    "B": {
                                        "status": "judged",
                                        "config_hash": "newhash",
                                        "staging_drive_id": "drive-b",
                                    },
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = mod.sync_registry(inventory_path, registry_path, "prompt-rollout-2026-04")

        entry = payload["entries"][0]
        self.assertEqual(entry["active_variant"], "B")
        self.assertEqual(entry["rollout"]["state"], "b_reviewed")
        self.assertEqual(entry["variants"]["A"]["config_hash"], "oldhash")
        self.assertEqual(entry["variants"]["B"]["config_hash"], "newhash")
        self.assertEqual(entry["variants"]["B"]["staging_drive_id"], "drive-b")

    def test_sync_registry_auto_activates_new_media_manifest_item_for_requested_lecture(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory_path = root / "episode_inventory.json"
            registry_path = root / "regeneration_registry.json"
            media_manifest_path = root / "media_manifest.r2.json"
            inventory_path.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "episode_key": "drive-a",
                                "title": "U10F2 · Davies (1990)",
                                "source_name": (
                                    "W10L2 - Davies (1990) [EN] "
                                    "{type=audio lang=en format=deep-dive length=long hash=oldhash}.mp3"
                                ),
                                "published_at": "2026-04-14T10:00:00+02:00",
                                "audio_url": "https://example.com/a.mp3",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            media_manifest_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "object_key": (
                                    "shows/personlighedspsykologi-en/W10L2/"
                                    "W10L2 - Davies (1990) [EN] "
                                    "{type=audio lang=en format=deep-dive length=long hash=newhash}.mp3"
                                ),
                                "source_name": (
                                    "W10L2 - Davies (1990) [EN] "
                                    "{type=audio lang=en format=deep-dive length=long hash=newhash}.mp3"
                                ),
                                "artifact_type": "audio",
                                "published_at": "2026-05-06T12:00:00Z",
                                "public_url": "https://example.com/b.mp3",
                                "sha256": "abc123",
                                "size": 123,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = mod.sync_registry(
                inventory_path,
                registry_path,
                "prompt-rollout-2026-04",
                media_manifest_path=media_manifest_path,
                activate_lecture_keys=["W10L2"],
                activation_campaign="course-understanding-prompt-refresh-2026-05-06",
            )

        entry = payload["entries"][0]
        self.assertEqual(entry["active_variant"], "B")
        self.assertEqual(entry["rollout"]["state"], "b_active")
        self.assertEqual(entry["rollout"]["campaign"], "course-understanding-prompt-refresh-2026-05-06")
        self.assertEqual(entry["variants"]["A"]["config_hash"], "oldhash")
        self.assertEqual(entry["variants"]["B"]["config_hash"], "newhash")
        self.assertEqual(entry["variants"]["B"]["audio_url"], "https://example.com/b.mp3")
        self.assertEqual(entry["variants"]["B"]["review_outcome"], "queue_auto_activated")

    def test_sync_registry_marks_tts_out_of_scope(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory_path = root / "episode_inventory.json"
            registry_path = root / "regeneration_registry.json"
            inventory_path.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "episode_key": "tts-a",
                                "title": "TTS",
                                "source_name": (
                                    "[TTS] W12L1 - Grundbog kapitel 14 - Perspektiver på personlighedspsykologi "
                                    "{type=tts voice=da date=2026-02-14}.mp3"
                                ),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = mod.sync_registry(inventory_path, registry_path, "prompt-rollout-2026-04")

        entry = payload["entries"][0]
        self.assertEqual(entry["prompt_type"], "tts")
        self.assertFalse(entry["rollout"]["in_scope"])
        self.assertEqual(entry["rollout"]["state"], "out_of_scope")

    def test_sync_registry_prunes_stale_a_only_entries_without_progress(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory_path = root / "episode_inventory.json"
            registry_path = root / "regeneration_registry.json"
            inventory_path.write_text(json.dumps({"episodes": []}), encoding="utf-8")
            registry_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "logical_episode_id": "single_reading__w01l1__foo",
                                "active_variant": "A",
                                "rollout": {"state": "original_only", "in_scope": True},
                                "variants": {"B": {"status": "not_generated"}},
                            },
                            {
                                "logical_episode_id": "single_reading__w01l1__bar",
                                "active_variant": "A",
                                "rollout": {"state": "b_reviewed", "in_scope": True},
                                "variants": {"B": {"status": "judged"}},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = mod.sync_registry(inventory_path, registry_path, "prompt-rollout-2026-04")

        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][0]["logical_episode_id"], "single_reading__w01l1__bar")
        self.assertFalse(payload["entries"][0]["inventory_present"])


if __name__ == "__main__":
    unittest.main()
