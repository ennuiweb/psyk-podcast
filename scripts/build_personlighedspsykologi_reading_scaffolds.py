#!/usr/bin/env python3
"""Legacy compatibility wrapper for the renamed printouts CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().with_name("build_personlighedspsykologi_printouts.py")
SPEC = importlib.util.spec_from_file_location("build_personlighedspsykologi_printouts", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
main = MODULE.main


if __name__ == "__main__":
    raise SystemExit(main())
