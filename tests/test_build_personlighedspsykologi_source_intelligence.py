from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_personlighedspsykologi_source_intelligence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_personlighedspsykologi_source_intelligence",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load source intelligence builder module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildPersonlighedspsykologiSourceIntelligenceTests(TestCase):
    def test_rebuild_runs_all_steps_in_order(self) -> None:
        module = _load_module()
        calls: list[tuple[list[str], Path]] = []

        def fake_run(cmd, *, cwd, check):
            self.assertTrue(check)
            calls.append((list(cmd), cwd))
            return None

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            module.rebuild_source_intelligence(
                repo_root=ROOT,
                python_bin="/tmp/python",
                run_invariants=True,
            )

        called_scripts = [Path(cmd[1]).name for cmd, _ in calls]
        self.assertEqual(
            called_scripts,
            module.STEP_SCRIPTS + [module.INVARIANT_SCRIPT],
        )
        for cmd, cwd in calls:
            self.assertEqual(cmd[0], "/tmp/python")
            self.assertEqual(cwd, ROOT)

    def test_rebuild_can_skip_invariants(self) -> None:
        module = _load_module()
        calls: list[str] = []

        def fake_run(cmd, *, cwd, check):
            self.assertEqual(cwd, ROOT)
            self.assertTrue(check)
            calls.append(Path(cmd[1]).name)
            return None

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            module.rebuild_source_intelligence(
                repo_root=ROOT,
                python_bin="/tmp/python",
                run_invariants=False,
            )

        self.assertEqual(calls, module.STEP_SCRIPTS)
