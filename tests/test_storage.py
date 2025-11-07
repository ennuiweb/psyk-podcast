import tempfile
import unittest
from pathlib import Path

from notebooklm_app import storage


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.show_root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_save_and_load_run(self) -> None:
        payload = {"foo": "bar"}
        slug = storage.timestamp_slug()
        storage.save_run(self.show_root, payload, slug=slug)
        loaded = storage.load_run(self.show_root, slug=slug)
        self.assertEqual(loaded, payload)
        runs = storage.list_runs(self.show_root)
        self.assertTrue(runs)

    def test_download_dir_created(self) -> None:
        download_dir = storage.ensure_download_dir(self.show_root)
        self.assertTrue(download_dir.exists())
        self.assertIn("downloads", str(download_dir))


if __name__ == "__main__":
    unittest.main()

