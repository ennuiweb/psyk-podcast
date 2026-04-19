import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "transcode_drive_media.py"
    spec = importlib.util.spec_from_file_location("transcode_drive_media", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TranscodeDriveMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_filter_skips_source_when_healthy_target_exists(self):
        source_files = [
            {
                "id": "wav-broken",
                "name": "[TTS] W6L1 - Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav",
                "mimeType": "audio/x-wav",
                "size": "0",
                "parents": ["folder-a"],
            }
        ]
        target_files = [
            {
                "id": "mp3-repair",
                "name": "[TTS] W6L1 - Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14} {repair=20260310a}.mp3",
                "mimeType": "audio/mpeg",
                "size": "84406604",
                "parents": ["folder-a"],
            }
        ]

        filtered = self.mod.filter_source_files_for_transcode(
            source_files,
            existing_target_files=target_files,
            target_extension="mp3",
            target_mime_type="audio/mpeg",
        )

        self.assertEqual(filtered, [])

    def test_filter_keeps_source_without_matching_target(self):
        source_files = [
            {
                "id": "wav-source",
                "name": "[TTS] W5L2 - Grundbog kapitel 07 - Nyere psykoanalytiske teorier {type=tts voice=da-DK__chirp3_hd__da-DK-Chirp3-HD-Algenib date=2026-02-14}.wav",
                "mimeType": "audio/x-wav",
                "size": "162622124",
                "parents": ["folder-a"],
            }
        ]
        target_files = []

        filtered = self.mod.filter_source_files_for_transcode(
            source_files,
            existing_target_files=target_files,
            target_extension="mp3",
            target_mime_type="audio/mpeg",
        )

        self.assertEqual(filtered, source_files)

    def test_filter_keeps_source_when_target_is_other_folder(self):
        source_files = [
            {
                "id": "wav-source",
                "name": "W6L2 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.wav",
                "mimeType": "audio/x-wav",
                "size": "123",
                "parents": ["folder-a"],
            }
        ]
        target_files = [
            {
                "id": "mp3-other-folder",
                "name": "W6L2 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3",
                "mimeType": "audio/mpeg",
                "size": "83112707",
                "parents": ["folder-b"],
            }
        ]

        filtered = self.mod.filter_source_files_for_transcode(
            source_files,
            existing_target_files=target_files,
            target_extension="mp3",
            target_mime_type="audio/mpeg",
        )

        self.assertEqual(filtered, source_files)

    def test_main_skips_non_drive_storage_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage": {
                            "provider": "r2",
                            "bucket": "freudd",
                            "endpoint": "https://example.r2.cloudflarestorage.com",
                        },
                        "transcode": {
                            "enabled": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            original_argv = sys.argv
            sys.argv = [
                "transcode_drive_media.py",
                "--config",
                str(config_path),
            ]
            try:
                with redirect_stdout(stdout):
                    self.mod.main()
            finally:
                sys.argv = original_argv

            self.assertIn("Transcode is skipped for storage provider 'r2'", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
