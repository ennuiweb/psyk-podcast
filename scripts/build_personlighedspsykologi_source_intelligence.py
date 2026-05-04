#!/usr/bin/env python3
"""Rebuild the full Source Intelligence Layer for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STEP_SCRIPTS = [
    "build_personlighedspsykologi_source_catalog.py",
    "build_personlighedspsykologi_lecture_bundles.py",
    "build_personlighedspsykologi_semantic_artifacts.py",
    "build_personlighedspsykologi_source_weighting.py",
    "build_personlighedspsykologi_concept_graph.py",
]
INVARIANT_SCRIPT = "check_personlighedspsykologi_artifact_invariants.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_step(*, repo_root: Path, python_bin: str, script_name: str) -> None:
    script_path = repo_root / "scripts" / script_name
    print(f"[source-intelligence] {script_name}", flush=True)
    subprocess.run(
        [python_bin, str(script_path)],
        cwd=repo_root,
        check=True,
    )


def rebuild_source_intelligence(*, repo_root: Path, python_bin: str, run_invariants: bool) -> None:
    for script_name in STEP_SCRIPTS:
        _run_step(repo_root=repo_root, python_bin=python_bin, script_name=script_name)
    if run_invariants:
        _run_step(repo_root=repo_root, python_bin=python_bin, script_name=INVARIANT_SCRIPT)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter to use for child build scripts.",
    )
    parser.add_argument(
        "--skip-invariants",
        action="store_true",
        help="Skip the final artifact invariant check.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rebuild_source_intelligence(
        repo_root=_repo_root(),
        python_bin=args.python_bin,
        run_invariants=not args.skip_invariants,
    )
    print("[source-intelligence] completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
