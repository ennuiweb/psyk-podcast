import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "storage_backends.py"
    spec = importlib.util.spec_from_file_location("storage_backends", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StorageBackendsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_r2_manifest_normalizes_prefix_and_public_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "media_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "object_key": "shows/personal/W01L1 - Intro [EN].mp3",
                                "stable_guid": "legacy-guid",
                                "published_at": "2026-02-02T10:00:00+00:00",
                                "mime_type": "audio/mpeg",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            backend = self.mod.R2StorageBackend(
                {
                    "__config_path__": str(manifest_path),
                    "storage": {
                        "provider": "r2",
                        "bucket": "freudd",
                        "prefix": "shows/personal",
                        "public_base_url": "https://audio.example.com",
                        "manifest_file": str(manifest_path),
                    },
                }
            )

            items = backend.list_media_files(mime_type_filters=["audio/"])

            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item["source_path"], "W01L1 - Intro [EN].mp3")
            self.assertEqual(item["source_storage_key"], "shows/personal/W01L1 - Intro [EN].mp3")
            self.assertEqual(item["stable_guid"], "legacy-guid")
            self.assertEqual(
                backend.build_public_url(item),
                "https://audio.example.com/shows/personal/W01L1%20-%20Intro%20%5BEN%5D.mp3",
            )


if __name__ == "__main__":
    unittest.main()
