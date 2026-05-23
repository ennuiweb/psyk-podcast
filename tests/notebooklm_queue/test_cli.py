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


def test_main_serve_show_treats_profile_capacity_wait_as_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.cli.serve_show_queue",
        lambda **kwargs: {
            "show_slug": "personlighedspsykologi-en",
            "stop_reason": "profile_capacity_wait",
            "wait_plan": {"reason": "no_usable_profiles"},
        },
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "serve-show",
            "--show-slug",
            "personlighedspsykologi-en",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 0


def test_main_serve_show_fails_manual_profile_capacity_wait(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "notebooklm_queue.cli.serve_show_queue",
        lambda **kwargs: {
            "show_slug": "personlighedspsykologi-en",
            "stop_reason": "profile_capacity_wait",
            "wait_plan": {
                "reason": "no_usable_profiles",
                "manual_intervention_required": True,
            },
        },
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "serve-show",
            "--show-slug",
            "personlighedspsykologi-en",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 1


def test_main_profile_status_reports_capacity_without_failing(tmp_path: Path, monkeypatch) -> None:
    printed: list[dict] = []
    monkeypatch.setattr(
        "notebooklm_queue.cli.inspect_profile_capacity",
        lambda **kwargs: {"configured": True, "has_capacity": False, "reason": "no_usable_profiles"},
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: printed.append(payload))

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "profile-status",
        ]
    )

    assert result == 0
    assert printed == [{"configured": True, "has_capacity": False, "reason": "no_usable_profiles"}]


def test_main_refresh_profiles_dispatches(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []
    printed: list[dict] = []

    def fake_refresh_profiles(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "summary": {"refreshed": 1}}

    monkeypatch.setattr("notebooklm_queue.cli.refresh_profiles", fake_refresh_profiles)
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: printed.append(payload))

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "refresh-profiles",
            "--profiles-file",
            str(tmp_path / "profiles.host.json"),
            "--profile-priority",
            "default,work",
            "--profile-state-file",
            str(tmp_path / "profile_state.json"),
            "--profile",
            "default",
            "--force",
            "--actor",
            "test",
        ]
    )

    assert result == 0
    options = calls[0]["options"]
    assert options.profile_priority == "default,work"
    assert options.profiles == ("default",)
    assert options.force is True
    assert options.actor == "test"
    assert printed == [{"status": "ok", "summary": {"refreshed": 1}}]


def test_main_refresh_profiles_dispatches_reclaim_options(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []

    def fake_refresh_profiles(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "summary": {"refreshed": 1}}

    monkeypatch.setattr("notebooklm_queue.cli.refresh_profiles", fake_refresh_profiles)
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: None)

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "refresh-profiles",
            "--reclaim-on-recovery",
            "--reclaim-target-free-slots",
            "17",
            "--reclaim-max-deletions",
            "9",
            "--reclaim-apply",
        ]
    )

    assert result == 0
    options = calls[0]["options"]
    assert options.reclaim_on_recovery is True
    assert options.reclaim_target_free_slots == 17
    assert options.reclaim_max_deletions == 9
    assert options.reclaim_dry_run is False


def test_main_reclaim_notebooks_dispatches_dry_run_by_default(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []
    printed: list[dict] = []

    def fake_reclaim_notebooks(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "summary": {"dry_run": 1}}

    monkeypatch.setattr("notebooklm_queue.cli.reclaim_notebooks", fake_reclaim_notebooks)
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: printed.append(payload))

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "reclaim-notebooks",
            "--profiles-file",
            str(tmp_path / "profiles.host.json"),
            "--profile",
            "default",
            "--target-free-slots",
            "25",
            "--max-deletions",
            "11",
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    )

    assert result == 0
    options = calls[0]["options"]
    assert options.profiles == ("default",)
    assert options.target_free_slots == 25
    assert options.max_deletions == 11
    assert options.dry_run is True
    assert printed == [{"status": "ok", "summary": {"dry_run": 1}}]


def test_main_refresh_retry_schedules_dispatches(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []
    printed: list[list[dict]] = []

    def fake_refresh_retry_schedules(**kwargs):
        calls.append(kwargs)
        return [{"job_id": "job-1", "state": "retry_scheduled"}]

    monkeypatch.setattr(
        "notebooklm_queue.cli.refresh_retry_schedules",
        fake_refresh_retry_schedules,
    )
    monkeypatch.setattr("notebooklm_queue.cli._print_json", lambda payload: printed.append(payload))

    result = main(
        [
            "--storage-root",
            str(tmp_path / "queue-root"),
            "refresh-retry-schedules",
            "--show-slug",
            "personlighedspsykologi-en",
            "--actor",
            "test",
        ]
    )

    assert result == 0
    assert calls[0]["show_slug"] == "personlighedspsykologi-en"
    assert calls[0]["actor"] == "test"
    assert printed == [[{"job_id": "job-1", "state": "retry_scheduled"}]]


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
