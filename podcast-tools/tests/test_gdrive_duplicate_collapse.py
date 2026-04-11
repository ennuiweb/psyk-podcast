import importlib.util
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "gdrive_podcast_feed.py"
    spec = importlib.util.spec_from_file_location("gdrive_podcast_feed", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GDriveDuplicateCollapseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_collapse_prefers_nonzero_mpeg_repair_variant(self):
        files = [
            {
                "id": "broken",
                "name": "[TTS] W6L1 - Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav",
                "mimeType": "audio/x-wav",
                "size": "0",
                "modifiedTime": "2026-02-14T19:02:01.237Z",
                "parents": ["folder-a"],
            },
            {
                "id": "repaired",
                "name": "[TTS] W6L1 - Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14} {repair=20260310}.mp3",
                "mimeType": "audio/mpeg",
                "size": "86565645",
                "modifiedTime": "2026-03-10T15:20:00.000Z",
                "parents": ["folder-a"],
            },
        ]

        collapsed = self.mod._collapse_duplicate_drive_files(files)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["id"], "repaired")

    def test_collapse_keeps_same_stem_in_different_folders(self):
        files = [
            {
                "id": "folder-a",
                "name": "W6L2 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3",
                "mimeType": "audio/mpeg",
                "size": "83112707",
                "modifiedTime": "2026-03-10T15:20:00.000Z",
                "parents": ["folder-a"],
            },
            {
                "id": "folder-b",
                "name": "W6L2 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3",
                "mimeType": "audio/mpeg",
                "size": "83112707",
                "modifiedTime": "2026-03-10T15:20:00.000Z",
                "parents": ["folder-b"],
            },
        ]

        collapsed = self.mod._collapse_duplicate_drive_files(files)

        self.assertEqual(len(collapsed), 2)
        self.assertEqual([entry["id"] for entry in collapsed], ["folder-a", "folder-b"])

    def test_collapse_prefers_canonical_name_over_newer_copy_suffix(self):
        files = [
            {
                "id": "canonical",
                "name": "W6L1 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=3 hash=1b3d31bc}.mp3",
                "mimeType": "audio/mpeg",
                "size": "66384964",
                "modifiedTime": "2026-03-02T16:34:33.880Z",
                "parents": ["folder-a"],
            },
            {
                "id": "finder-copy",
                "name": "W6L1 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=3 hash=1b3d31bc} 2.mp3",
                "mimeType": "audio/mpeg",
                "size": "66384964",
                "modifiedTime": "2026-04-10T21:09:43.766Z",
                "parents": ["folder-a"],
            },
        ]

        collapsed = self.mod._collapse_duplicate_drive_files(files)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["id"], "canonical")


if __name__ == "__main__":
    unittest.main()
