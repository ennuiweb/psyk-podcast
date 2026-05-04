import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from botocore.exceptions import ClientError
from boto3.exceptions import S3UploadFailedError


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "migrate_drive_show_to_r2.py"
    spec = importlib.util.spec_from_file_location("migrate_drive_show_to_r2", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigrateDriveShowToR2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_extract_drive_file_id_supports_uc_url(self):
        file_id = self.mod.extract_drive_file_id("https://drive.google.com/uc?export=download&id=abc123")
        self.assertEqual(file_id, "abc123")

    def test_load_guid_maps_reads_rss_drive_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory = root / "episode_inventory.json"
            feed = root / "rss.xml"
            inventory.write_text("{}", encoding="utf-8")
            feed.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<rss version="2.0">
  <channel>
    <item>
      <title>Episode A</title>
      <guid isPermaLink="false">legacy-guid-a</guid>
      <enclosure url="https://drive.google.com/uc?export=download&amp;id=fileA" />
    </item>
  </channel>
</rss>
""",
                encoding="utf-8",
            )

            guid_map = self.mod.load_guid_maps(inventory_path=inventory, feed_path=feed)

            self.assertEqual(guid_map["fileA"], "legacy-guid-a")
            self.assertEqual(guid_map["Episode A"], "legacy-guid-a")

    def test_resolve_stable_guid_prefers_existing_map(self):
        guid = self.mod.resolve_stable_guid(
            {"id": "drive-id", "name": "Example.mp3"},
            {"drive-id": "legacy-guid"},
        )
        self.assertEqual(guid, "legacy-guid")

    def test_build_manifest_item_emits_expected_fields(self):
        item = self.mod.build_manifest_item(
            bucket="freudd",
            object_key="shows/personal/example.mp3",
            source_name="example.mp3",
            source_path="folder/example.mp3",
            path_parts=["folder"],
            mime_type="audio/mpeg",
            size=123,
            sha256="abc",
            published_at="2026-05-03T00:00:00+00:00",
            public_url="https://audio.example.com/shows/personal/example.mp3",
            stable_guid="legacy-guid",
        )

        self.assertEqual(item["stable_guid"], "legacy-guid")
        self.assertEqual(item["object_key"], "shows/personal/example.mp3")
        self.assertEqual(item["artifact_type"], "audio")

    def test_load_existing_manifest_index_reads_object_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "media_manifest.r2.json"
            manifest.write_text(
                json.dumps(
                    {
                        "items": [
                            {"object_key": "shows/personal/a.mp3", "sha256": "aaa"},
                            {"object_key": "shows/personal/b.mp3", "sha256": "bbb"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = self.mod.load_existing_manifest_index(manifest)

            self.assertEqual(result["shows/personal/a.mp3"]["sha256"], "aaa")
            self.assertEqual(result["shows/personal/b.mp3"]["sha256"], "bbb")

    def test_load_optional_transcode_config_returns_none_when_disabled(self):
        self.assertIsNone(self.mod.load_optional_transcode_config({}))
        self.assertIsNone(self.mod.load_optional_transcode_config({"transcode": {"enabled": False}}))

    def test_build_output_media_plan_transcodes_matching_mime_types(self):
        plan = self.mod.build_output_media_plan(
            source_name="folder-audio.wav",
            source_mime_type="audio/x-wav",
            folder_parts=[],
            prefix="shows/personal",
            transcode_cfg={
                "source_mime_types": ["audio/wav", "audio/x-wav"],
                "target_extension": "mp3",
                "target_mime_type": "audio/mpeg",
            },
        )

        self.assertTrue(plan["transcode_applied"])
        self.assertEqual(plan["published_name"], "folder-audio.mp3")
        self.assertEqual(plan["published_path"], "folder-audio.mp3")
        self.assertEqual(plan["object_key"], "shows/personal/folder-audio.mp3")
        self.assertEqual(plan["published_mime_type"], "audio/mpeg")

    def test_validate_manifest_items_rejects_blank_sha256(self):
        with self.assertRaises(SystemExit) as exc:
            self.mod.validate_manifest_items(
                [
                    {"object_key": "shows/personal/a.mp3", "sha256": "abc"},
                    {"object_key": "shows/personal/b.mp3", "sha256": ""},
                ]
            )

        self.assertIn("blank sha256", str(exc.exception))

    def test_load_inventory_allowlist_prefers_drive_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inventory = Path(tmpdir) / "episode_inventory.json"
            inventory.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "source_drive_file_id": "drive-a",
                                "source_name": "Episode A.mp3",
                            },
                            {
                                "source_storage_key": "drive-b",
                                "source_path": "folder/Episode B.mp3",
                            },
                            {
                                "source_name": "Episode C.mp3",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allowlist = self.mod.load_inventory_allowlist(inventory)

            self.assertEqual(allowlist["episode_count"], 3)
            self.assertEqual(allowlist["drive_ids"], {"drive-a", "drive-b"})
            self.assertEqual(allowlist["fallback_names"], {"Episode C.mp3"})

    def test_filter_files_to_inventory_restricts_to_current_inventory(self):
        allowlist = {
            "drive_ids": {"drive-a", "drive-b"},
            "fallback_names": {"Episode C.mp3"},
        }
        files = [
            {"id": "drive-a", "name": "Episode A.mp3"},
            {"id": "drive-b", "name": "Episode B.mp3"},
            {"id": "other", "name": "Episode C.mp3"},
            {"id": "extra", "name": "Episode D.mp3"},
        ]

        filtered, missing = self.mod.filter_files_to_inventory(files, allowlist)

        self.assertEqual([item["id"] for item in filtered], ["drive-a", "drive-b"])
        self.assertEqual(missing, ["Episode C.mp3"])

    def test_is_retryable_exception_handles_transient_network_errors(self):
        self.assertTrue(self.mod.is_retryable_exception(OSError(65, "No route to host")))
        self.assertTrue(self.mod.is_retryable_exception(TimeoutError("timed out")))
        self.assertTrue(
            self.mod.is_retryable_exception(
                S3UploadFailedError("Failed to upload foo: An error occurred (NoSuchUpload)")
            )
        )

        client_error = ClientError(
            {
                "Error": {"Code": "SlowDown", "Message": "slow down"},
                "ResponseMetadata": {"HTTPStatusCode": 503},
            },
            "HeadObject",
        )
        self.assertTrue(self.mod.is_retryable_exception(client_error))


if __name__ == "__main__":
    unittest.main()
