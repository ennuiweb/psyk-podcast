import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
        cls.rename_outputs = _load_module(
            root / "scripts" / "rename_personlighedspsykologi_outputs.py",
            "rename_personlighedspsykologi_outputs",
        )
        cls.mirror_outputs = _load_module(
            root / "scripts" / "mirror_output_dirs.py",
            "mirror_output_dirs",
        )

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

    def test_drive_derive_mp3_name_ignores_cfg_tag(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        stem = "W01L1 - W1L1 Foo [EN] {type=audio lang=en format=deep-dive length=long hash=deadbeef}"
        self.assertEqual(mod.derive_mp3_name_from_html(stem), "W01L1 - Foo [EN].mp3")

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
            ],
            "personlighedspsykologi",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["relative_path"], "W1L1/foo-medium.html")
        self.assertEqual(entry["difficulty"], "medium")
        self.assertEqual(entry["subject_slug"], "personlighedspsykologi")
        self.assertEqual(
            [item["difficulty"] for item in entry["links"]],
            ["easy", "medium", "hard"],
        )
        self.assertTrue(all(item["subject_slug"] == "personlighedspsykologi" for item in entry["links"]))

    def test_local_build_flat_quiz_relative_path_is_deterministic(self):
        mod = self.local_sync
        rel_a, seed_a = mod.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "medium",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        rel_b, seed_b = mod.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "medium",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        self.assertEqual(rel_a, rel_b)
        self.assertEqual(seed_a, seed_b)
        self.assertRegex(rel_a, r"^[0-9a-f]{8}\.html$")

    def test_local_build_flat_quiz_relative_path_changes_with_difficulty(self):
        mod = self.local_sync
        rel_easy, _ = mod.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "easy",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        rel_medium, _ = mod.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "medium",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        self.assertNotEqual(rel_easy, rel_medium)

    def test_local_ensure_unique_flat_quiz_relative_path_detects_collisions(self):
        mod = self.local_sync
        registry = {}
        mod.ensure_unique_flat_quiz_relative_path(
            registry,
            "abcd1234.html",
            "w01l1 - foo|medium",
            context="first.html",
        )
        with self.assertRaises(ValueError):
            mod.ensure_unique_flat_quiz_relative_path(
                registry,
                "abcd1234.html",
                "w01l1 - bar|medium",
                context="second.html",
            )

    def test_cfg_tag_suffix_strip_removes_repeated_tags(self):
        local = self.local_sync
        value = "W01L1 - Foo {type=quiz lang=en quantity=more difficulty=hard hash=beef1234}"
        self.assertEqual(local.strip_cfg_tag_suffix(value), "W01L1 - Foo")
        if self.drive_sync is not None:
            self.assertEqual(self.drive_sync.strip_cfg_tag_suffix(value), "W01L1 - Foo")

    def test_local_matches_quiz_difficulty_from_cfg_tag(self):
        mod = self.local_sync
        stem = (
            "W01L1 - Foo [EN] "
            "{type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}"
        )
        self.assertTrue(mod.matches_quiz_difficulty(stem, "easy"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "medium"))

    def test_local_matches_quiz_difficulty_treats_untagged_as_medium(self):
        mod = self.local_sync
        stem = "W01L1 - Foo [EN]"
        self.assertTrue(mod.matches_quiz_difficulty(stem, "medium"))
        self.assertFalse(mod.matches_quiz_difficulty(stem, "hard"))

    def test_local_excludes_non_quiz_json_artifacts(self):
        mod = self.local_sync
        self.assertTrue(mod.is_excluded_quiz_json_name("quiz_json_manifest.json"))
        self.assertTrue(mod.is_excluded_quiz_json_name("foo.html.request.json"))
        self.assertTrue(mod.is_excluded_quiz_json_name("foo.html.request.done.json"))
        self.assertTrue(
            mod.is_excluded_quiz_json_name(
                "[Brief] W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}.json"
            )
        )
        self.assertFalse(
            mod.is_excluded_quiz_json_name(
                "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}.json"
            )
        )

    def test_local_quiz_json_payload_validation_accepts_supported_shapes(self):
        mod = self.local_sync
        self.assertTrue(mod.is_valid_quiz_payload([{"question": "Q1"}]))
        self.assertTrue(mod.is_valid_quiz_payload({"questions": []}))
        self.assertTrue(mod.is_valid_quiz_payload({"quiz": []}))
        self.assertFalse(mod.is_valid_quiz_payload({"foo": "bar"}))

    def test_local_quiz_path_conversion_keeps_public_html_and_json_upload_source(self):
        mod = self.local_sync
        self.assertEqual(
            mod.to_public_quiz_relative_path("W01L1/quiz-file.json"),
            "W01L1/quiz-file.html",
        )
        self.assertEqual(
            mod.to_source_quiz_json_relative_path("W01L1/quiz-file.html"),
            "W01L1/quiz-file.json",
        )

    def test_local_sync_fails_when_no_valid_quiz_json_files_exist(self):
        script_path = _repo_root() / "scripts" / "sync_quiz_links.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--output-root",
                    tmp_dir,
                    "--subject-slug",
                    "personlighedspsykologi",
                    "--dry-run",
                    "--no-upload",
                ],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No valid quiz JSON files found", result.stderr + result.stdout)

    def test_drive_matches_quiz_difficulty_from_cfg_tag(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        stem = (
            "W01L1 - Foo [EN] "
            "{type=quiz lang=en quantity=standard difficulty=hard hash=beef1234}"
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

    def test_drive_excludes_non_quiz_json_artifacts(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        self.assertTrue(mod.is_excluded_quiz_json_name("quiz_json_manifest.json"))
        self.assertTrue(mod.is_excluded_quiz_json_name("foo.html.request.json"))
        self.assertTrue(mod.is_excluded_quiz_json_name("foo.html.request.done.json"))
        self.assertTrue(
            mod.is_excluded_quiz_json_name(
                "[Brief] W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=hard hash=beef1234}.json"
            )
        )
        self.assertFalse(
            mod.is_excluded_quiz_json_name(
                "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=hard hash=beef1234}.json"
            )
        )

    def test_drive_quiz_path_conversion_keeps_public_html_and_json_download_source(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        self.assertEqual(
            mod.to_public_quiz_relative_path("W01L1/quiz-file.json"),
            "W01L1/quiz-file.html",
        )
        self.assertEqual(
            mod.to_source_quiz_json_relative_path("W01L1/quiz-file.html"),
            "W01L1/quiz-file.json",
        )

    def test_drive_sync_fails_when_no_valid_quiz_json_files_exist(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "service_account_file": str(Path(tmp_dir) / "service-account.json"),
                        "drive_folder_id": "folder-123",
                        "quiz": {
                            "links_file": str(Path(tmp_dir) / "quiz_links.json"),
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(mod, "build_drive_service", return_value=object()):
                with mock.patch.object(mod, "list_drive_files", return_value=[]):
                    with mock.patch.object(
                        sys,
                        "argv",
                        ["sync_drive_quiz_links.py", "--config", str(config_path)],
                    ):
                        with self.assertRaises(SystemExit) as exc_info:
                            mod.main()
        self.assertIn("No valid quiz JSON files found", str(exc_info.exception))

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
            ],
            "personlighedspsykologi",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["relative_path"], "W1L1/foo-medium.html")
        self.assertEqual(entry["difficulty"], "medium")
        self.assertEqual(entry["subject_slug"], "personlighedspsykologi")
        self.assertEqual(
            [item["difficulty"] for item in entry["links"]],
            ["easy", "medium", "hard"],
        )
        self.assertTrue(all(item["subject_slug"] == "personlighedspsykologi" for item in entry["links"]))

    def test_local_sync_fallback_derive_mp3_names_maps_quiz_without_audio_file(self):
        script_path = _repo_root() / "scripts" / "sync_quiz_links.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            quiz_file = (
                root
                / "W01L1 - Slide lecture: Intro [EN] {type=quiz lang=en quantity=standard difficulty=medium hash=beef1234}.json"
            )
            quiz_file.write_text(json.dumps({"questions": []}), encoding="utf-8")
            links_file = root / "quiz_links.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--output-root",
                    str(root),
                    "--links-file",
                    str(links_file),
                    "--subject-slug",
                    "personlighedspsykologi",
                    "--fallback-derive-mp3-names",
                    "--no-upload",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(links_file.read_text(encoding="utf-8"))
        self.assertIn("W01L1 - Slide lecture: Intro [EN].mp3", payload["by_name"])

    def test_drive_sync_fallback_derive_mp3_names_maps_quiz_without_audio_file(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        mod = self.drive_sync
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            links_path = Path(tmp_dir) / "quiz_links.json"
            config_path.write_text(
                json.dumps(
                    {
                        "service_account_file": str(Path(tmp_dir) / "service-account.json"),
                        "drive_folder_id": "folder-123",
                        "quiz": {
                            "links_file": str(links_path),
                        },
                    }
                ),
                encoding="utf-8",
            )
            side_effect = [
                [],
                [
                    {
                        "id": "quiz-1",
                        "name": (
                            "W01L1 - Slide lecture: Intro [EN] "
                            "{type=quiz lang=en quantity=standard difficulty=medium hash=beef1234}.json"
                        ),
                    }
                ],
            ]
            with mock.patch.object(mod, "build_drive_service", return_value=object()):
                with mock.patch.object(mod, "list_drive_files", side_effect=side_effect):
                    with mock.patch.object(
                        sys,
                        "argv",
                        [
                            "sync_drive_quiz_links.py",
                            "--config",
                            str(config_path),
                            "--fallback-derive-mp3-names",
                        ],
                    ):
                        self.assertEqual(mod.main(), 0)
            payload = json.loads(links_path.read_text(encoding="utf-8"))
        self.assertIn("W01L1 - Slide lecture: Intro [EN].mp3", payload["by_name"])

    def test_flat_quiz_relative_path_matches_between_local_and_drive_sync(self):
        if self.drive_sync is None:
            self.skipTest("google-api dependencies unavailable for sync_drive_quiz_links import")
        local_rel, local_seed = self.local_sync.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "hard",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        drive_rel, drive_seed = self.drive_sync.build_flat_quiz_relative_path(
            "W01L1 - Foo [EN].mp3",
            "hard",
            8,
            include_subject=False,
            subject_slug="personlighedspsykologi",
        )
        self.assertEqual(local_rel, drive_rel)
        self.assertEqual(local_seed, drive_seed)

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
            quiz_format="json",
            source_count=None,
            hash_len=8,
        )
        self.assertIn("type=quiz", token)
        self.assertIn("lang=en", token)
        self.assertIn("quantity=more", token)
        self.assertIn("difficulty=hard", token)
        self.assertIn("download=json", token)
        self.assertRegex(token, r"hash=[0-9a-f]{8}")

    def test_generate_week_build_output_cfg_tag_token_omits_html_download_field(self):
        mod = self.generate_week
        token = mod.build_output_cfg_tag_token(
            content_type="quiz",
            language="en",
            instructions="quiz prompt",
            audio_format=None,
            audio_length=None,
            infographic_orientation=None,
            infographic_detail=None,
            quiz_quantity="standard",
            quiz_difficulty="medium",
            quiz_format="html",
            source_count=None,
            hash_len=8,
        )
        self.assertNotIn("download=", token)

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

    def test_generate_week_per_slide_override_changes_only_matching_slide(self):
        mod = self.generate_week
        matching = mod.SourceItem(
            Path("slide-a.pdf"),
            "Slide lecture: A",
            "slide",
            "w01l1-lecture-a",
            "lecture",
        )
        other = mod.SourceItem(
            Path("slide-b.pdf"),
            "Slide lecture: B",
            "slide",
            "w01l1-lecture-b",
            "lecture",
        )
        per_slide_cfg = {
            "format": "deep-dive",
            "length": "default",
            "prompt": "base prompt",
            "overrides": {
                "w01l1-lecture-a": {
                    "length": "long",
                    "prompt": "expanded prompt",
                }
            },
        }
        overrides = mod.validate_per_slide_audio_config(per_slide_cfg)

        self.assertEqual(
            mod.per_source_audio_settings(
                matching,
                per_reading_cfg={},
                per_slide_cfg=per_slide_cfg,
                per_slide_overrides=overrides,
            ),
            ("per_slide", "expanded prompt", "deep-dive", "long"),
        )
        self.assertEqual(
            mod.per_source_audio_settings(
                other,
                per_reading_cfg={},
                per_slide_cfg=per_slide_cfg,
                per_slide_overrides=overrides,
            ),
            ("per_slide", "base prompt", "deep-dive", "default"),
        )

    def test_generate_week_per_slide_override_rejects_unknown_fields(self):
        mod = self.generate_week
        with self.assertRaises(SystemExit) as exc:
            mod.validate_per_slide_audio_config(
                {
                    "overrides": {
                        "w01l1-lecture-a": {
                            "duration": "long",
                        }
                    }
                }
            )
        self.assertIn("Unknown per_slide override field", str(exc.exception))

    def test_generate_week_per_slide_override_rejects_invalid_length(self):
        mod = self.generate_week
        with self.assertRaises(SystemExit) as exc:
            mod.validate_per_slide_audio_config(
                {
                    "overrides": {
                        "w01l1-lecture-a": {
                            "length": "very-long",
                        }
                    }
                }
            )
        self.assertIn("Unknown per_slide.overrides.w01l1-lecture-a.length", str(exc.exception))

    def test_generate_week_only_slide_dry_run_plans_selected_slide_audio(self):
        root = _repo_root()
        script = (
            root
            / "notebooklm-podcast-auto"
            / "personlighedspsykologi"
            / "scripts"
            / "generate_week.py"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sources_root = tmp_path / "sources"
            week_dir = sources_root / "W01L1"
            week_dir.mkdir(parents=True)
            (week_dir / "Reading.pdf").write_bytes(b"%PDF-1.4\n%reading\n")

            slides_root = tmp_path / "slides"
            slides_root.mkdir()
            (slides_root / "Slide A.pdf").write_bytes(b"%PDF-1.4\n%slide\n")
            slides_catalog = tmp_path / "slides_catalog.json"
            slide_key = "w01l1-lecture-slide-a"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "slides": [
                            {
                                "slide_key": slide_key,
                                "lecture_key": "W01L1",
                                "subcategory": "lecture",
                                "title": "Slide A",
                                "source_filename": "Slide A.pdf",
                                "local_relative_path": "Slide A.pdf",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            prompt_config = tmp_path / "prompt_config.json"
            prompt_config.write_text(
                json.dumps(
                    {
                        "language": "en",
                        "languages": [{"code": "en", "suffix": "[EN]"}],
                        "per_reading": {"format": "deep-dive", "length": "long", "prompt": ""},
                        "per_slide": {
                            "format": "deep-dive",
                            "length": "default",
                            "prompt": "",
                            "overrides": {slide_key: {"length": "long"}},
                        },
                        "course_title": "Test Course",
                        "slides_catalog": str(slides_catalog),
                        "slides_source_root": str(slides_root),
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--week",
                    "W01L1",
                    "--sources-root",
                    str(sources_root),
                    "--prompt-config",
                    str(prompt_config),
                    "--output-root",
                    str(tmp_path / "output"),
                    "--content-types",
                    "audio",
                    "--only-slide",
                    slide_key,
                    "--dry-run",
                    "--no-print-downloads",
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SLIDE AUDIO (en):", result.stdout)
        self.assertIn("length=long", result.stdout)
        self.assertNotIn("READING AUDIO", result.stdout)
        self.assertNotIn("WEEKLY AUDIO", result.stdout)

    def test_generate_week_quarantines_stale_slide_audio_outputs(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_output_dir = root / "output" / "W01L1"
            week_output_dir.mkdir(parents=True)
            stale = week_output_dir / (
                "W01L1 - Slide lecture: Slide A [EN] "
                "{type=audio lang=en format=deep-dive length=default hash=old11111}.mp3"
            )
            stale.write_bytes(b"old")
            sidecar = stale.with_suffix(stale.suffix + ".request.json")
            sidecar.write_text("{}", encoding="utf-8")
            canonical = week_output_dir / (
                "W01L1 - Slide lecture: Slide A [EN] "
                "{type=audio lang=en format=deep-dive length=long hash=new22222}.mp3"
            )
            canonical.write_bytes(b"new")
            unrelated = week_output_dir / (
                "W01L1 - Reading [EN] "
                "{type=audio lang=en format=deep-dive length=default hash=old11111}.mp3"
            )
            unrelated.write_bytes(b"reading")

            moved = mod.quarantine_stale_slide_audio_outputs(
                repo_root=root,
                week_output_dir=week_output_dir,
                canonical_output_path=canonical,
                timestamp="20260415-120000",
            )

            quarantine_dir = (
                root / ".ai/quarantine/slide-audio-overrides/20260415-120000/W01L1"
            )
            self.assertEqual(len(moved), 2)
            self.assertFalse(stale.exists())
            self.assertFalse(sidecar.exists())
            self.assertTrue((quarantine_dir / stale.name).exists())
            self.assertTrue((quarantine_dir / sidecar.name).exists())
            self.assertTrue(canonical.exists())
            self.assertTrue(unrelated.exists())

    def test_generate_week_normalize_quiz_difficulty_accepts_all(self):
        mod = self.generate_week
        self.assertEqual(mod.normalize_quiz_difficulty("all"), "all")

    def test_generate_week_quiz_difficulty_values_expands_all(self):
        mod = self.generate_week
        self.assertEqual(mod.quiz_difficulty_values("quiz", "all"), ["easy", "medium", "hard"])
        self.assertEqual(mod.quiz_difficulty_values("audio", "all"), [None])

    def test_generate_week_build_source_items_includes_manual_slides(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_dir = root / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            (week_dir / "Lewis (1999).pdf").write_bytes(b"%PDF-1.4\n%reading\n")

            slides_root = root / "slides-root"
            (slides_root / "Forelaesningsraekken").mkdir(parents=True, exist_ok=True)
            (slides_root / "Forelaesningsraekken" / "Forelaesning intro slides.pdf").write_bytes(
                b"%PDF-1.4\n%slide\n"
            )
            slides_catalog = root / "slides_catalog.json"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subject_slug": "personlighedspsykologi",
                        "slides": [
                            {
                                "slide_key": "w01l1-lecture-intro-slides",
                                "lecture_key": "W01L1",
                                "subcategory": "lecture",
                                "title": "Forelæsning intro slides",
                                "source_filename": "Forelaesning intro slides.pdf",
                                "local_relative_path": "Forelaesningsraekken/Forelaesning intro slides.pdf",
                                "relative_path": "W01L1/lecture/Forelaesning intro slides.pdf",
                            }
                        ],
                        "unresolved": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            reading_sources, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W01L1",
                slides_catalog_path=slides_catalog,
                slides_source_root=slides_root,
            )

        self.assertEqual(len(reading_sources), 1)
        self.assertEqual(len(generation_sources), 2)
        self.assertEqual([item.source_type for item in generation_sources], ["reading", "slide"])
        self.assertEqual(generation_sources[0].base_name, "Lewis (1999)")
        self.assertEqual(generation_sources[1].base_name, "Slide lecture: Forelæsning intro slides")
        self.assertEqual(generation_sources[1].slide_key, "w01l1-lecture-intro-slides")

    def test_generate_week_build_source_items_matches_unpadded_week_label_to_catalog(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_dir = root / "W1L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            (week_dir / "Lewis (1999).pdf").write_bytes(b"%PDF-1.4\n%reading\n")

            slides_root = root / "slides-root"
            (slides_root / "Oevelseshold" / "Slides").mkdir(parents=True, exist_ok=True)
            (slides_root / "Oevelseshold" / "Slides" / "1. Introduktion.pdf").write_bytes(
                b"%PDF-1.4\n%slide\n"
            )
            slides_catalog = root / "slides_catalog.json"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subject_slug": "personlighedspsykologi",
                        "slides": [
                            {
                                "slide_key": "w01l1-exercise-intro",
                                "lecture_key": "W01L1",
                                "subcategory": "exercise",
                                "title": "Introduktion",
                                "source_filename": "1. Introduktion.pdf",
                                "local_relative_path": "Oevelseshold/Slides/1. Introduktion.pdf",
                                "relative_path": "W01L1/exercise/1. Introduktion.pdf",
                            }
                        ],
                        "unresolved": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            _, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W1L1",
                slides_catalog_path=slides_catalog,
                slides_source_root=slides_root,
            )

        self.assertEqual([item.source_type for item in generation_sources], ["reading", "slide"])
        self.assertEqual(generation_sources[1].slide_key, "w01l1-exercise-intro")
        self.assertEqual(generation_sources[1].slide_subcategory, "exercise")

    def test_generate_week_canonical_week_label_from_dir_pads_week_numbers(self):
        mod = self.generate_week
        self.assertEqual(mod.canonical_week_label_from_dir(Path("W1L1 Intro")), "W01L1")
        self.assertEqual(mod.canonical_week_label_from_dir(Path("W01L1 Intro")), "W01L1")

    def test_generate_week_rejects_duplicate_canonical_week_dirs(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_a = root / "W1L1 Intro"
            week_b = root / "W01L1 Intro"
            week_a.mkdir()
            week_b.mkdir()
            with self.assertRaises(SystemExit) as exc:
                mod.ensure_unique_canonical_week_dirs([week_a, week_b], week_input="W1L1")
        self.assertIn("collapse to the same canonical lecture key", str(exc.exception))

    def test_generate_week_build_source_items_matches_secondary_lecture_key_in_catalog(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_dir = root / "W01L2"
            week_dir.mkdir(parents=True, exist_ok=True)
            (week_dir / "Mayer & Bryan (2024).pdf").write_bytes(b"%PDF-1.4\n%reading\n")

            slides_root = root / "slides-root"
            (slides_root / "Oevelseshold" / "Slides").mkdir(parents=True, exist_ok=True)
            (slides_root / "Oevelseshold" / "Slides" / "4. Psykoanalyse I.pdf").write_bytes(
                b"%PDF-1.4\n%slide\n"
            )
            slides_catalog = root / "slides_catalog.json"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subject_slug": "personlighedspsykologi",
                        "slides": [
                            {
                                "slide_key": "w04l1-exercise-psykoanalyse-i",
                                "lecture_key": "W04L1",
                                "lecture_keys": ["W04L1", "W01L2"],
                                "subcategory": "exercise",
                                "title": "Psykoanalyse I",
                                "source_filename": "4. Psykoanalyse I.pdf",
                                "local_relative_path": "Oevelseshold/Slides/4. Psykoanalyse I.pdf",
                                "relative_path": "W04L1/exercise/4. Psykoanalyse I.pdf",
                            }
                        ],
                        "unresolved": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            _, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W01L2",
                slides_catalog_path=slides_catalog,
                slides_source_root=slides_root,
            )

        self.assertEqual([item.source_type for item in generation_sources], ["reading", "slide"])
        self.assertEqual(generation_sources[1].slide_key, "w04l1-exercise-psykoanalyse-i")
        self.assertEqual(generation_sources[1].base_name, "Slide exercise: Psykoanalyse I")

    def test_generate_week_weekly_overview_count_excludes_slides(self):
        mod = self.generate_week
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            week_dir = root / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            (week_dir / "Only reading.pdf").write_bytes(b"%PDF-1.4\n%reading\n")

            slides_root = root / "slides-root"
            (slides_root / "Forelaesningsraekken").mkdir(parents=True, exist_ok=True)
            (slides_root / "Forelaesningsraekken" / "Only slide.pdf").write_bytes(b"%PDF-1.4\n%slide\n")
            slides_catalog = root / "slides_catalog.json"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subject_slug": "personlighedspsykologi",
                        "slides": [
                            {
                                "slide_key": "w01l1-lecture-only-slide",
                                "lecture_key": "W01L1",
                                "subcategory": "lecture",
                                "title": "Only slide",
                                "source_filename": "Only slide.pdf",
                                "local_relative_path": "Forelaesningsraekken/Only slide.pdf",
                                "relative_path": "W01L1/lecture/Only slide.pdf",
                            }
                        ],
                        "unresolved": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            reading_sources, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W01L1",
                slides_catalog_path=slides_catalog,
                slides_source_root=slides_root,
            )

        reading_count = len(reading_sources)
        slide_count = sum(1 for item in generation_sources if item.source_type == "slide")

        self.assertEqual(reading_count, 1)
        self.assertEqual(slide_count, 1)
        self.assertFalse(mod.should_generate_weekly_overview(reading_count))
        self.assertGreater(len(generation_sources), reading_count)

    def test_rename_outputs_plan_file_moves_merges_unpadded_week_dir(self):
        mod = self.rename_outputs
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_path = root / "W1L1" / "W1L1 - Foo [EN].mp3"
            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_bytes(b"audio")
            planned = mod.plan_file_moves(root)

        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].destination.relative_to(root), Path("W01L1/W01L1 - Foo [EN].mp3"))
        self.assertFalse(planned[0].identical)

    def test_rename_outputs_apply_moves_removes_legacy_dir_and_rewrites_request_json(self):
        mod = self.rename_outputs
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            legacy_dir = root / "W1L1"
            canonical_dir = root / "W01L1"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            canonical_dir.mkdir(parents=True, exist_ok=True)
            source = legacy_dir / "W1L1 - Foo [EN].mp3"
            source.write_bytes(b"audio")
            request_json = legacy_dir / "W1L1 - Foo [EN].mp3.request.json"
            request_json.write_text(
                json.dumps({"output_path": str(source.resolve())}, ensure_ascii=False),
                encoding="utf-8",
            )

            planned = mod.plan_file_moves(root)
            moved, removed_duplicates, removed_dirs = mod.apply_planned_moves(root, planned)
            rewritten = mod.rewrite_request_json_paths(root)

            migrated_audio = canonical_dir / "W01L1 - Foo [EN].mp3"
            migrated_request = canonical_dir / "W01L1 - Foo [EN].mp3.request.json"

            self.assertTrue(migrated_audio.exists())
            self.assertTrue(migrated_request.exists())
            self.assertFalse(legacy_dir.exists())
            self.assertEqual(moved, 2)
            self.assertEqual(removed_duplicates, 0)
            self.assertGreaterEqual(removed_dirs, 1)
            self.assertEqual(rewritten, 1)
            payload = json.loads(migrated_request.read_text(encoding="utf-8"))
            self.assertTrue(payload["output_path"].endswith("W01L1/W01L1 - Foo [EN].mp3"))

    def test_rename_outputs_rejects_conflicting_canonical_destination(self):
        mod = self.rename_outputs
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "W1L1" / "W1L1 - Foo [EN].mp3"
            destination = root / "W01L1" / "W01L1 - Foo [EN].mp3"
            source.parent.mkdir(parents=True, exist_ok=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"left")
            destination.write_bytes(b"right")
            with self.assertRaises(SystemExit) as exc:
                mod.plan_file_moves(root)
        self.assertIn("different content", str(exc.exception))

    def test_mirror_outputs_rejects_non_canonical_week_layout_for_personlighedspsykologi(self):
        mod = self.mirror_outputs
        with self.assertRaises(SystemExit) as exc:
            mod.validate_canonical_week_layout(
                "personlighedspsykologi",
                [Path("W1L1/W1L1 - Foo [EN].mp3"), Path("W01L2/W01L2 - Bar [EN].mp3")],
            )
        self.assertIn("non-canonical week directories", str(exc.exception))

    def test_generate_podcast_output_path_for_quiz_difficulty_rewrites_cfg_tag(self):
        if self.generate_podcast is None:
            self.skipTest("notebooklm dependencies unavailable for generate_podcast import")
        mod = self.generate_podcast
        output = Path(
            "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=all hash=deadbeef}.html"
        )
        rewritten = mod._output_path_for_quiz_difficulty(output, "hard")
        self.assertEqual(
            rewritten.name,
            "W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=hard hash=deadbeef}.html",
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
