import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from notebooklm_app.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.yaml"
        self.service_account = Path(self.tmpdir.name) / "sa.json"
        self.service_account.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def write_config(self, body: str) -> None:
        self.config_path.write_text(textwrap.dedent(body), encoding="utf-8")

    def test_loads_show_and_resolves_defaults(self) -> None:
        self.write_config(
            f"""
            project_number: "123"
            location: "global"
            endpoint_prefix: "us-"
            podcast_parent: "projects/123/locations/global"
            default_notebook_id: "demo"
            language_code: "en-US"
            drive_upload_root: "drive-default"
            service_account_file: "{self.service_account}"
            shows:
              social-psychology:
                episode_focus: "Focus"
            """
        )
        config = load_config(self.config_path)
        resolved = config.resolve_show("social-psychology")
        self.assertEqual(resolved.notebook_id, "demo")
        self.assertEqual(resolved.drive_folder_id, "drive-default")
        self.assertEqual(resolved.episode_focus, "Focus")
        self.assertEqual(resolved.endpoint_prefix, "us-")

    def test_env_override_applies(self) -> None:
        self.write_config(
            f"""
            project_number: "123"
            location: "global"
            default_notebook_id: "demo"
            drive_upload_root: "drive-default"
            service_account_file: "{self.service_account}"
            shows:
              intro-vt: {{}}
            """
        )
        os.environ["NOTEBOOKLM_LANGUAGE"] = "da-DK"
        try:
            config = load_config(self.config_path)
        finally:
            os.environ.pop("NOTEBOOKLM_LANGUAGE", None)
        resolved = config.resolve_show("intro-vt")
        self.assertEqual(resolved.language_code, "da-DK")

    def test_missing_show_raises(self) -> None:
        self.write_config(
            f"""
            project_number: "123"
            location: "global"
            default_notebook_id: "demo"
            drive_upload_root: "drive-default"
            service_account_file: "{self.service_account}"
            shows:
              intro-vt: {{}}
            """
        )
        config = load_config(self.config_path)
        with self.assertRaises(ConfigError):
            config.resolve_show("unknown")


if __name__ == "__main__":
    unittest.main()

