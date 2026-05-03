import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "show_config_policy.py"
    spec = importlib.util.spec_from_file_location("show_config_policy", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShowConfigPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_defaults_to_legacy_workflow_and_drive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")

            payload = self.mod.resolve_show_policy(config_path)

            self.assertEqual(payload["storage_provider"], "drive")
            self.assertEqual(payload["publication_owner"], "legacy_workflow")
            self.assertEqual(payload["workflow_writer_enabled"], "true")

    def test_resolves_queue_owned_r2_show(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "storage": {"provider": "r2"},
                        "publication": {"owner": "queue"},
                    }
                ),
                encoding="utf-8",
            )

            payload = self.mod.resolve_show_policy(config_path)

            self.assertEqual(payload["storage_provider"], "r2")
            self.assertEqual(payload["publication_owner"], "queue")
            self.assertEqual(payload["workflow_writer_enabled"], "false")

    def test_rejects_invalid_publication_owner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"publication": {"owner": "both"}}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsupported publication.owner"):
                self.mod.resolve_show_policy(config_path)

    def test_cli_writes_github_output(self):
        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "podcast-tools" / "show_config_policy.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            output_path = Path(tmpdir) / "github-output.txt"
            config_path.write_text(
                json.dumps({"storage": {"provider": "r2"}, "publication": {"owner": "queue"}}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "resolve",
                    "--config",
                    str(config_path),
                    "--github-output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["publication_owner"], "queue")
            output_lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertIn("storage_provider=r2", output_lines)
            self.assertIn("publication_owner=queue", output_lines)
            self.assertIn("workflow_writer_enabled=false", output_lines)


if __name__ == "__main__":
    unittest.main()
