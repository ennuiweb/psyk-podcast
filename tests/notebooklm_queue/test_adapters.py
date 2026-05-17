from pathlib import Path

from notebooklm_queue.adapters import SHOW_ADAPTERS


def test_personligheds_generate_command_includes_profile_env_args(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_PRIORITY", "freudagsbaren,baduljen")
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", "/etc/podcasts/notebooklm-queue/profiles.host.json")

    command = SHOW_ADAPTERS["personlighedspsykologi-da"].build_generate_command(
        Path("/opt/podcasts"),
        lecture_key="W01L1",
        content_types=("audio",),
        dry_run=False,
    )

    assert command[0] == "/opt/podcasts/.venv/bin/python"
    assert "--profile-priority" in command
    assert command[command.index("--profile-priority") + 1] == "freudagsbaren,baduljen"
    assert "--profiles-file" in command
    assert command[command.index("--profiles-file") + 1] == "/etc/podcasts/notebooklm-queue/profiles.host.json"


def test_personligheds_download_command_includes_profile_env_args(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_PRIORITY", "default,oskarvedel")
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", "/etc/podcasts/notebooklm-queue/profiles.host.json")

    command = SHOW_ADAPTERS["personlighedspsykologi-en"].build_download_command(
        Path("/opt/podcasts"),
        lecture_key="W01L1",
        content_types=("audio",),
        dry_run=False,
    )

    assert command[0] == "/opt/podcasts/.venv/bin/python"
    assert "--profile-priority" in command
    assert command[command.index("--profile-priority") + 1] == "default,oskarvedel"
    assert "--profiles-file" in command
    assert command[command.index("--profiles-file") + 1] == "/etc/podcasts/notebooklm-queue/profiles.host.json"


def test_bioneuro_generate_command_does_not_receive_personligheds_profile_args(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_PRIORITY", "freudagsbaren,baduljen")
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", "/etc/podcasts/notebooklm-queue/profiles.host.json")

    command = SHOW_ADAPTERS["bioneuro"].build_generate_command(
        Path("/opt/podcasts"),
        lecture_key="W01",
        content_types=("audio",),
        dry_run=False,
    )

    assert "--profile-priority" not in command
    assert "--profiles-file" not in command


def test_bioneuro_download_command_does_not_receive_personligheds_profile_args(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_PRIORITY", "freudagsbaren,baduljen")
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", "/etc/podcasts/notebooklm-queue/profiles.host.json")

    command = SHOW_ADAPTERS["bioneuro"].build_download_command(
        Path("/opt/podcasts"),
        lecture_key="W01",
        content_types=("audio",),
        dry_run=False,
    )

    assert "--profile-priority" not in command
    assert "--profiles-file" not in command
