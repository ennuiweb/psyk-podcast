import importlib.util
import unittest
from pathlib import Path


def _load_module(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class CfgTagFilenameHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = _repo_root()
        cls.local_sync = _load_module(root / "scripts" / "sync_quiz_links.py", "local_sync")
        cls.drive_sync = None
        try:
            cls.drive_sync = _load_module(
                root / "podcast-tools" / "sync_drive_quiz_links.py", "drive_sync"
            )
        except ModuleNotFoundError:
            cls.drive_sync = None
        cls.generate_week = _load_module(
            root
            / "notebooklm-podcast-auto"
            / "personlighedspsykologi"
            / "scripts"
            / "generate_week.py",
            "generate_week",
        )

    def test_local_canonical_key_ignores_cfg_tag(self):
        mod = self.local_sync
        tagged = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long prompt=deadbeef}"
        plain = "W01L1 - W1L1 Foo [EN]"
        self.assertEqual(mod.canonical_key(tagged), mod.canonical_key(plain))

    def test_local_derive_mp3_name_ignores_cfg_tag(self):
        mod = self.local_sync
        stem = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long prompt=deadbeef}"
        self.assertEqual(mod.derive_mp3_name_from_html(stem), "W01L1 - Foo [EN].mp3")

    def test_drive_canonical_key_ignores_cfg_tag(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        tagged = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long prompt=deadbeef}"
        plain = "W01L1 - W1L1 Foo [EN]"
        self.assertEqual(mod.canonical_key(tagged), mod.canonical_key(plain))

    def test_cfg_tag_suffix_strip_removes_repeated_tags(self):
        local = self.local_sync
        value = "W01L1 - Foo {type=quiz lang=en quantity=more difficulty=hard download=html prompt=beef1234}"
        self.assertEqual(local.strip_cfg_tag_suffix(value), "W01L1 - Foo")
        if self.drive_sync is not None:
            self.assertEqual(self.drive_sync.strip_cfg_tag_suffix(value), "W01L1 - Foo")

    def test_generate_week_config_tag_is_deterministic_and_changes(self):
        mod = self.generate_week
        cfg_a = {"language": "en", "weekly_overview": {"format": "deep-dive"}}
        cfg_b = {"language": "en", "weekly_overview": {"format": "brief"}}
        first = mod.compute_config_tag(cfg_a, 8)
        second = mod.compute_config_tag(cfg_a, 8)
        third = mod.compute_config_tag(cfg_b, 8)
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_generate_week_apply_config_tag_replaces_existing(self):
        mod = self.generate_week
        original = Path("W01L1 - Foo [EN] {type=audio lang=en format=brief length=default prompt=a1b2c3d4}.mp3")
        new_tag = " {type=audio lang=en format=deep-dive length=long prompt=deadbeef}"
        tagged = mod.apply_config_tag(original, new_tag)
        self.assertEqual(
            tagged.name,
            "W01L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long prompt=deadbeef}.mp3",
        )
        tagged_again = mod.apply_config_tag(tagged, new_tag)
        self.assertEqual(tagged_again.name, tagged.name)

    def test_generate_week_apply_config_tag_truncates_long_filename(self):
        mod = self.generate_week
        long_stem = "W01L1 - " + ("x" * 400)
        path = Path(f"{long_stem}.mp3")
        tag = " {type=audio lang=en format=deep-dive length=long prompt=deadbeef}"
        tagged = mod.apply_config_tag(path, tag)
        self.assertTrue(tagged.name.endswith(f"{tag}.mp3"))
        self.assertLessEqual(len(tagged.name.encode("utf-8")), mod.MAX_FILENAME_BYTES)

    def test_generate_week_build_output_cfg_tag_token_includes_all_audio_options(self):
        mod = self.generate_week
        token = mod.build_output_cfg_tag_token(
            content_type="audio",
            language="en",
            instructions="make it engaging",
            audio_format="deep-dive",
            audio_length="long",
            infographic_orientation=None,
            infographic_detail=None,
            quiz_quantity=None,
            quiz_difficulty=None,
            quiz_format=None,
            source_count=None,
            hash_len=8,
        )
        self.assertIn("type=audio", token)
        self.assertIn("lang=en", token)
        self.assertIn("format=deep-dive", token)
        self.assertIn("length=long", token)
        self.assertRegex(token, r"prompt=[0-9a-f]{8}")

    def test_generate_week_build_output_cfg_tag_token_includes_all_quiz_options(self):
        mod = self.generate_week
        token = mod.build_output_cfg_tag_token(
            content_type="quiz",
            language="en",
            instructions="quiz prompt",
            audio_format=None,
            audio_length=None,
            infographic_orientation=None,
            infographic_detail=None,
            quiz_quantity="more",
            quiz_difficulty="hard",
            quiz_format="html",
            source_count=None,
            hash_len=8,
        )
        self.assertIn("type=quiz", token)
        self.assertIn("lang=en", token)
        self.assertIn("quantity=more", token)
        self.assertIn("difficulty=hard", token)
        self.assertIn("download=html", token)
        self.assertRegex(token, r"prompt=[0-9a-f]{8}")

    def test_generate_week_build_output_cfg_tag_token_includes_source_count_for_weekly_audio(self):
        mod = self.generate_week
        token = mod.build_output_cfg_tag_token(
            content_type="audio",
            language="en",
            instructions="weekly prompt",
            audio_format="deep-dive",
            audio_length="long",
            infographic_orientation=None,
            infographic_detail=None,
            quiz_quantity=None,
            quiz_difficulty=None,
            quiz_format=None,
            source_count=7,
            hash_len=8,
        )
        self.assertIn("sources=7", token)


if __name__ == "__main__":
    unittest.main()
