import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "publish_local_show_to_r2.py"
    spec = importlib.util.spec_from_file_location("publish_local_show_to_r2", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublishLocalShowToR2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_guess_source_mime_type_handles_common_audio_extensions(self):
        self.assertEqual(self.mod.guess_source_mime_type(Path("example.m4a")), "audio/mp4")
        self.assertEqual(self.mod.guess_source_mime_type(Path("example.wav")), "audio/x-wav")
        self.assertEqual(self.mod.guess_source_mime_type(Path("example.mp3")), "audio/mpeg")

    def test_iter_local_source_files_includes_transcode_source_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.mp3").write_bytes(b"a")
            (root / "b.wav").write_bytes(b"b")
            (root / "c.txt").write_text("c", encoding="utf-8")

            files = self.mod.iter_local_source_files(
                source_dir=root,
                allowed_mime_filters=["audio/"],
                transcode_cfg={
                    "source_mime_types": ["audio/x-wav"],
                    "target_extension": "mp3",
                    "target_mime_type": "audio/mpeg",
                },
            )

            self.assertEqual([path.name for path in files], ["a.mp3", "b.wav"])

    def test_resolve_stable_guid_prefers_existing_manifest_guid(self):
        guid = self.mod.resolve_stable_guid(
            object_key="shows/personal/example.mp3",
            source_path="example.mp3",
            source_name="example.mp3",
            guid_map={"example.mp3": "legacy-guid"},
            existing_manifest_item={"stable_guid": "manifest-guid"},
        )
        self.assertEqual(guid, "manifest-guid")

    def test_build_manifest_item_uses_storage_identity(self):
        item = self.mod.build_manifest_item(
            bucket="freudd",
            object_key="shows/personal/example.mp3",
            source_name="example.mp3",
            source_path="example.mp3",
            path_parts=[],
            mime_type="audio/mpeg",
            size=123,
            sha256="abc",
            published_at="2026-05-04T00:00:00+00:00",
            public_url="https://audio.example.com/shows/personal/example.mp3",
            stable_guid="legacy-guid",
        )

        self.assertEqual(item["source_storage_key"], "shows/personal/example.mp3")
        self.assertEqual(item["stable_guid"], "legacy-guid")
        self.assertEqual(item["artifact_type"], "audio")

    def test_load_guid_maps_uses_storage_identity_from_inventory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inventory = root / "episode_inventory.json"
            feed = root / "rss.xml"
            inventory.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "guid": "legacy-guid-a",
                                "source_storage_key": "shows/personal/example.mp3",
                                "source_path": "example.mp3",
                                "source_name": "example.mp3",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            feed.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<rss version="2.0"><channel /></rss>
""",
                encoding="utf-8",
            )

            guid_map = self.mod.load_guid_maps(inventory_path=inventory, feed_path=feed)

            self.assertEqual(guid_map["shows/personal/example.mp3"], "legacy-guid-a")
            self.assertEqual(guid_map["example.mp3"], "legacy-guid-a")


if __name__ == "__main__":
    unittest.main()
