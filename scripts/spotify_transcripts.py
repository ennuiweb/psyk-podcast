#!/usr/bin/env python3
"""CLI wrapper for spotify_transcripts."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if (
    VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    and not os.environ.get("PODCASTS_SPOTIFY_TRANSCRIPTS_NO_REEXEC")
):
    os.execv(
        str(VENV_PYTHON),
        [
            str(VENV_PYTHON),
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
    )

from spotify_transcripts.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
