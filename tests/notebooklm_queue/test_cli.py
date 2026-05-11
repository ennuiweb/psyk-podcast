from __future__ import annotations

from pathlib import Path

from notebooklm_queue.cli import _print_json, main
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


def test_main_serve_show_treats_blocked_backlog_as_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.cli.serve_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stop_reason": "blocked_backlog_remaining",
            "wait_plan": {"state_counts": {"blocked_auth_stale": 1}},
        },
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "serve-show",
            "--show-slug",
            "bioneuro",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 0


def test_main_serve_show_treats_service_timeout_as_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.cli.serve_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stop_reason": "service_timeout_reached",
            "wait_plan": {"reason": "next_wait_exceeds_time_budget"},
        },
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "serve-show",
            "--show-slug",
            "bioneuro",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 0


def test_main_serve_show_keeps_manual_intervention_nonzero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.cli.serve_show_queue",
        lambda **kwargs: {
            "show_slug": "bioneuro",
            "stop_reason": "manual_intervention_required",
            "wait_plan": {"reason": "invalid_retry_schedule"},
        },
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "serve-show",
            "--show-slug",
            "bioneuro",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 1
