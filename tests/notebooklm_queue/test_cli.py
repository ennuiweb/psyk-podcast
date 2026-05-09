from __future__ import annotations

from pathlib import Path

from notebooklm_queue.cli import _print_json
from notebooklm_queue.models import JobIdentity


def test_print_json_serializes_job_identity_and_paths(capsys) -> None:
    payload = {
        "repo_root": Path("/tmp/repo"),
        "identity": JobIdentity(
            show_slug="personlighedspsykologi-da",
            subject_slug="personlighedspsykologi",
            lecture_key="W01L1",
            content_types=("audio",),
            config_hash="cfg-da",
        ),
    }

    _print_json(payload)

    output = capsys.readouterr().out
    assert '"repo_root": "/tmp/repo"' in output
    assert '"show_slug": "personlighedspsykologi-da"' in output
    assert '"content_types": [' in output
