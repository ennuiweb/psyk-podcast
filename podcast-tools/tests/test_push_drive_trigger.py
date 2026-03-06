import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class PushDriveTriggerScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.source_script = cls.repo_root / "apps-script" / "push_drive_trigger.sh"

    def setUp(self):
        self._tmpdirs: list[Path] = []

    def tearDown(self):
        for path in reversed(self._tmpdirs):
            shutil.rmtree(path, ignore_errors=True)

    def _make_tmpdir(self, prefix: str) -> Path:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        self._tmpdirs.append(path)
        return path

    def _prepare_script_tree(self, *, include_clasp_json: bool) -> Path:
        root = self._make_tmpdir("push-drive-trigger-tree-")
        apps_script_dir = root / "apps-script"
        apps_script_dir.mkdir(parents=True, exist_ok=True)
        target_script = apps_script_dir / "push_drive_trigger.sh"
        shutil.copy2(self.source_script, target_script)
        mode = target_script.stat().st_mode
        target_script.chmod(mode | stat.S_IXUSR)

        if include_clasp_json:
            (apps_script_dir / ".clasp.json").write_text(
                '{\n  "scriptId": "test-script-id",\n  "rootDir": "."\n}\n',
                encoding="utf-8",
            )

        return target_script

    def _make_fake_clasp(self, *, exit_code: int) -> tuple[Path, Path]:
        bin_dir = self._make_tmpdir("push-drive-trigger-bin-")
        args_file = bin_dir / "clasp-args.log"
        clasp_script = bin_dir / "clasp"
        clasp_script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf '%s\\n' \"$*\" >> \"{args_file}\"\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        clasp_script.chmod(0o755)
        return bin_dir, args_file

    def _run_script(self, script_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script_path)],
            cwd=str(script_path.parent),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_missing_config_best_effort_continues(self):
        script_path = self._prepare_script_tree(include_clasp_json=False)
        bin_dir, args_file = self._make_fake_clasp(exit_code=0)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env.pop("APPS_SCRIPT_PUSH_MODE", None)
        env.pop("APPS_SCRIPT_CLASP_JSON", None)

        result = self._run_script(script_path, env)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("missing Apps Script project config", result.stderr)
        self.assertFalse(args_file.exists(), "clasp should not be called when config is missing")

    def test_missing_config_required_fails(self):
        script_path = self._prepare_script_tree(include_clasp_json=False)
        bin_dir, _ = self._make_fake_clasp(exit_code=0)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["APPS_SCRIPT_PUSH_MODE"] = "required"

        result = self._run_script(script_path, env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing Apps Script project config", result.stderr)

    def test_required_mode_uses_override_project_file(self):
        script_path = self._prepare_script_tree(include_clasp_json=False)
        bin_dir, args_file = self._make_fake_clasp(exit_code=0)
        override_dir = self._make_tmpdir("push-drive-trigger-override-")
        override_project = override_dir / ".clasp.json"
        override_project.write_text(
            '{\n  "scriptId": "override-id",\n  "rootDir": "."\n}\n',
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["APPS_SCRIPT_PUSH_MODE"] = "required"
        env["APPS_SCRIPT_CLASP_JSON"] = str(override_project)

        result = self._run_script(script_path, env)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        args_text = args_file.read_text(encoding="utf-8")
        self.assertIn(f"-P {override_project} push", args_text)

    def test_clasp_failure_is_non_blocking_in_best_effort(self):
        script_path = self._prepare_script_tree(include_clasp_json=True)
        bin_dir, _ = self._make_fake_clasp(exit_code=9)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env.pop("APPS_SCRIPT_PUSH_MODE", None)

        result = self._run_script(script_path, env)

        self.assertEqual(result.returncode, 0)
        self.assertIn("clasp push failed", result.stderr)

    def test_clasp_failure_blocks_in_required_mode(self):
        script_path = self._prepare_script_tree(include_clasp_json=True)
        bin_dir, _ = self._make_fake_clasp(exit_code=9)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["APPS_SCRIPT_PUSH_MODE"] = "required"

        result = self._run_script(script_path, env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clasp push failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
