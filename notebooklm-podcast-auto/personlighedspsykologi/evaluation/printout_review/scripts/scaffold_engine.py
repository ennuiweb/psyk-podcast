"""Legacy compatibility wrapper for the renamed printout review engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().with_name("printout_engine.py")
SPEC = importlib.util.spec_from_file_location("printout_engine", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
globals().update({name: getattr(MODULE, name) for name in dir(MODULE) if not name.startswith("__")})
