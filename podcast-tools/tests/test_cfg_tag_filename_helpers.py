import importlib.util
import tempfile
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
        cls.generate_podcast = None
        try:
            cls.generate_podcast = _load_module(
                root / "notebooklm-podcast-auto" / "generate_podcast.py",
                "generate_podcast",
            )
        except ModuleNotFoundError:
            cls.generate_podcast = None

    def test_local_canonical_key_ignores_cfg_tag(self):
        mod = self.local_sync
        tagged = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        plain = "W01L1 - W1L1 Foo [EN]"
        self.assertEqual(mod.canonical_key(tagged), mod.canonical_key(plain))

    def test_local_derive_mp3_name_ignores_cfg_tag(self):
        mod = self.local_sync
        stem = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        self.assertEqual(mod.derive_mp3_name_from_html(stem), "W01L1 - Foo [EN].mp3")

    def test_local_canonical_key_ignores_cfg_tag_with_profile_suffix(self):
        mod = self.local_sync
        tagged = (
            "W01L1 - W1L1 Foo [EN] "
            "{type=audio lang=en format=deep-dive length=long hash=deadbeef} [default-2]"
        )
        plain = "W01L1 - W1L1 Foo [EN]"
        self.assertEqual(mod.canonical_key(tagged), mod.canonical_key(plain))

    def test_drive_canonical_key_ignores_cfg_tag(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        tagged = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        plain = "W01L1 - W1L1 Foo [EN]"
        self.assertEqual(mod.canonical_key(tagged), mod.canonical_key(plain))

    def test_local_select_audio_candidate_prefers_non_double_prefixed_week_name(self):
        mod = self.local_sync
        candidates = [
            Path("W8L1 - W8L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=aaaa1111}.mp3"),
            Path("W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"),
        ]
        selected = mod.select_audio_candidate(candidates)
        self.assertIsNotNone(selected)
        self.assertEqual(
            selected.name,
            "W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3",
        )

    def test_local_select_audio_candidate_returns_none_when_tied(self):
        mod = self.local_sync
        candidates = [
            Path("W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=aaaa1111}.mp3"),
            Path("W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3"),
        ]
        self.assertIsNone(mod.select_audio_candidate(candidates))

    def test_local_build_mapping_entry_prefers_medium_primary_and_keeps_all_links(self):
        mod = self.local_sync
        entry = mod.build_mapping_entry(
            [
                {"relative_path": "W1L1/foo-hard.html", "format": "html", "difficulty": "hard"},
                {"relative_path": "W1L1/foo-medium.html", "format": "html", "difficulty": "medium"},
                {"relative_path": "W1L1/foo-easy.html", "format": "html", "difficulty": "easy"},
            ]
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["relative_path"], "W1L1/foo-medium.html")
        self.assertEqual(entry["difficulty"], "medium")
        self.assertEqual(
            [item["difficulty"] for item in entry["links"]],
            ["easy", "medium", "hard"],
        )

    def test_cfg_tag_suffix_strip_removes_repeated_tags(self):
        local = self.local_sync
        value = "W01L1 - Foo {type=quiz lang=en quantity=more difficulty=hard download=html hash=beef1234}"
        self.assertEqual(local.strip_cfg_tag_suffix(value), "W01L1 - Foo")
        if self.drive_sync is not None:
            self.assertEqual(self.drive_sync.strip_cfg_tag_suffix(value), "W01L1 - Foo")

    def test_local_matches_quiz_difficulty_from_cfg_tag(self):
        mod = self.local_sync
        stem = (
            "W01L1 - Foo [EN] "
            "{type=quiz lang=en quantity=standard difficulty=easy download=html hash=beef1234}"
        )
        self.assertTrue(mod.matches_quiz_difficulty(stem, "easy"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "medium"))

    def test_local_matches_quiz_difficulty_treats_untagged_as_medium(self):
        mod = self.local_sync
        stem = "W01L1 - Foo [EN]"
        self.assertTrue(mod.matches_quiz_difficulty(stem, "medium"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "hard"))

    def test_drive_matches_quiz_difficulty_from_cfg_tag(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        stem = (
            "W01L1 - Foo [EN] "
            "{type=quiz lang=en quantity=standard difficulty=hard download=html hash=beef1234}"
        )
        self.assertTrue(mod.matches_quiz_difficulty(stem, "hard"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "easy"))

    def test_drive_matches_quiz_difficulty_treats_untagged_as_medium(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        stem = "W01L1 - Foo [EN]"
        self.assertTrue(mod.matches_quiz_difficulty(stem, "medium"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "easy"))

    def test_drive_select_audio_candidate_prefers_non_double_prefixed_week_name(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        candidates = [
            "W8L1 - W8L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=aaaa1111}.mp3",
            "W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3",
        ]
        selected = mod.select_audio_candidate(candidates)
        self.assertEqual(
            selected,
            "W8L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=bbbb2222}.mp3",
        )

    def test_drive_build_mapping_entry_prefers_medium_primary_and_keeps_all_links(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        entry = mod.build_mapping_entry(
            [
                {"relative_path": "W1L1/foo-hard.html", "format": "html", "difficulty": "hard"},
                {"relative_path": "W1L1/foo-medium.html", "format": "html", "difficulty": "medium"},
                {"relative_path": "W1L1/foo-easy.html", "format": "html", "difficulty": "easy"},
            ]
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["relative_path"], "W1L1/foo-medium.html")
        self.assertEqual(entry["difficulty"], "medium")
        self.assertEqual(
            [item["difficulty"] for item in entry["links"]],
            ["easy", "medium", "hard"],
        )

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
        original = Path("W01L1 - Foo [EN] {type=audio lang=en format=brief length=default hash=a1b2c3d4}.mp3")
        new_tag = " {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        tagged = mod.apply_config_tag(original, new_tag)
        self.assertEqual(
            tagged.name,
            "W01L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}.mp3",
        )
        tagged_again = mod.apply_config_tag(tagged, new_tag)
        self.assertEqual(tagged_again.name, tagged.name)

    def test_generate_week_strip_week_prefix_from_title_matches_week_numbers(self):
        mod = self.generate_week
        self.assertEqual(
            mod.strip_week_prefix_from_title("W1L1 Lewis (1999)", "W01L1"),
            "Lewis (1999)",
        )
        self.assertEqual(
            mod.strip_week_prefix_from_title("W1L2 Lewis (1999)", "W01L1"),
            "W1L2 Lewis (1999)",
        )

    def test_generate_week_normalize_episode_title_strips_duplicate_week_tokens(self):
        mod = self.generate_week
        self.assertEqual(
            mod.normalize_episode_title("W1L1 - W1L1 Lewis (1999)", "W01L1"),
            "Lewis (1999)",
        )

    def test_generate_week_normalize_episode_title_collapses_dots_and_whitespace(self):
        mod = self.generate_week
        self.assertEqual(
            mod.normalize_episode_title("W1L2   Phan et al.....   (2024)", "W01L2"),
            "Phan et al. (2024)",
        )

    def test_generate_week_apply_config_tag_replaces_existing_with_profile_suffix(self):
        mod = self.generate_week
        original = Path(
            "W01L1 - Foo [EN] {type=audio lang=en format=brief length=default hash=a1b2c3d4} [default].mp3"
        )
        new_tag = " {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        tagged = mod.apply_config_tag(original, new_tag)
        self.assertEqual(
            tagged.name,
            "W01L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}.mp3",
        )

    def test_generate_week_apply_config_tag_truncates_long_filename(self):
        mod = self.generate_week
        long_stem = "W01L1 - " + ("x" * 400)
        path = Path(f"{long_stem}.mp3")
        tag = " {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        tagged = mod.apply_config_tag(path, tag)
        self.assertTrue(tagged.name.endswith(f"{tag}.mp3"))
        self.assertLessEqual(len(tagged.name.encode("utf-8")), mod.MAX_FILENAME_BYTES)

    def test_generate_week_ensure_unique_output_path_never_appends_profile_suffix(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "W01L1 - Foo.mp3"
            output_path.write_bytes(b"x")
            resolved = mod.ensure_unique_output_path(output_path, "default")
            self.assertEqual(resolved, output_path)

    def test_generate_podcast_ensure_unique_output_path_never_appends_profile_suffix(self):
        if self.generate_podcast is None:
            self.skipTest("notebooklm dependencies unavailable for generate_podcast import")
        mod = self.generate_podcast
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "W01L1 - Foo.mp3"
            output_path.write_bytes(b"x")
            resolved = mod._ensure_unique_output_path(
                output_path,
                {
                    "profile": "default",
                    "storage_path": "/tmp/default_storage_state.json",
                },
            )
            self.assertEqual(resolved, output_path)

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
        self.assertRegex(token, r"hash=[0-9a-f]{8}")

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
        self.assertRegex(token, r"hash=[0-9a-f]{8}")

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

    def test_generate_week_build_output_cfg_tag_token_hash_is_deterministic(self):
        mod = self.generate_week
        token_a = mod.build_output_cfg_tag_token(
            content_type="quiz",
            language="en",
            instructions="weekly prompt",
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
        token_b = mod.build_output_cfg_tag_token(
            content_type="quiz",
            language="en",
            instructions="weekly prompt",
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
        self.assertEqual(token_a, token_b)

    def test_generate_week_build_output_cfg_tag_token_hash_changes_with_effective_config(self):
        mod = self.generate_week
        token_a = mod.build_output_cfg_tag_token(
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
            source_count=5,
            hash_len=8,
        )
        token_b = mod.build_output_cfg_tag_token(
            content_type="audio",
            language="en",
            instructions="weekly prompt",
            audio_format="deep-dive",
            audio_length="short",
            infographic_orientation=None,
            infographic_detail=None,
            quiz_quantity=None,
            quiz_difficulty=None,
            quiz_format=None,
            source_count=5,
            hash_len=8,
        )
        self.assertNotEqual(token_a, token_b)

    def test_generate_week_normalize_quiz_difficulty_accepts_all(self):
        mod = self.generate_week
        self.assertEqual(mod.normalize_quiz_difficulty("all"), "all")

    def test_generate_week_quiz_difficulty_values_expands_all(self):
        mod = self.generate_week
        self.assertEqual(mod.quiz_difficulty_values("quiz", "all"), ["easy", "medium", "hard"])
        self.assertEqual(mod.quiz_difficulty_values("audio", "all"), [None])

    def test_generate_podcast_output_path_for_quiz_difficulty_rewrites_cfg_tag(self):
        if self.generate_podcast is None:
            self.skipTest("notebooklm dependencies unavailable for generate_podcast import")
        mod = self.generate_podcast
        output = Path(
            "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=all download=html hash=deadbeef}.html"
        )
        rewritten = mod._output_path_for_quiz_difficulty(output, "hard")
        self.assertEqual(
            rewritten.name,
            "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=hard download=html hash=deadbeef}.html",
        )

    def test_generate_podcast_output_path_for_quiz_difficulty_fallback_suffix(self):
        if self.generate_podcast is None:
            self.skipTest("notebooklm dependencies unavailable for generate_podcast import")
        mod = self.generate_podcast
        output = Path("quiz.html")
        rewritten = mod._output_path_for_quiz_difficulty(output, "easy")
        self.assertEqual(rewritten.name, "quiz [difficulty=easy].html")


if __name__ == "__main__":
    unittest.main()
