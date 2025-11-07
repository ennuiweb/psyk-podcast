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

    def test_loads_profile_and_resolves_defaults(self) -> None:
        self.write_config(
            f"""
            project_id: "proj-123"
            location: "global"
            language_code: "en-US"
            default_length: "SHORT"
            service_account_file: "{self.service_account}"
            workspace_root: "{self.tmpdir.name}/workspace"
            profiles:
              social-psychology:
                focus: "Focus"
                contexts:
                  - type: "text"
                    value: "Inline"
            """
        )
        config = load_config(self.config_path)
        resolved = config.resolve_profile("social-psychology")
        self.assertEqual(resolved.focus, "Focus")
        self.assertEqual(resolved.length, "SHORT")
        self.assertEqual(resolved.project_id, "proj-123")
        self.assertEqual(resolved.endpoint, "https://discoveryengine.googleapis.com")
        self.assertEqual(len(resolved.contexts), 1)
        self.assertIn("workspace", str(resolved.workspace_dir))

    def test_env_override_applies(self) -> None:
        self.write_config(
            f"""
            project_id: "proj-123"
            location: "global"
            service_account_file: "{self.service_account}"
            profiles:
              intro-vt: {{}}
            """
        )
        os.environ["NOTEBOOKLM_LANGUAGE"] = "da-DK"
        try:
            config = load_config(self.config_path)
        finally:
            os.environ.pop("NOTEBOOKLM_LANGUAGE", None)
        resolved = config.resolve_profile("intro-vt")
        self.assertEqual(resolved.language_code, "da-DK")

    def test_missing_profile_raises(self) -> None:
        self.write_config(
            f"""
            project_id: "proj-123"
            location: "global"
            service_account_file: "{self.service_account}"
            profiles:
              intro-vt: {{}}
            """
        )
        config = load_config(self.config_path)
        with self.assertRaises(ConfigError):
            config.resolve_profile("unknown")


if __name__ == "__main__":
    unittest.main()
