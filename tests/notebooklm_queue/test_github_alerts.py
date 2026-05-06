from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from notebooklm_queue.github_alerts import build_comment_body, build_title, deliver_alert_to_github, ensure_issue


def _payload() -> dict[str, object]:
    return {
        "kind": "auth_stale",
        "show_slug": "bioneuro",
        "summary": "NotebookLM auth appears stale for bioneuro W1L1",
        "lecture_key": "W1L1",
        "job_id": "job-1",
        "state": "failed_retryable",
        "attempt_count": 2,
        "host": "queue-host",
        "occurred_at": "2026-05-04T12:00:00+00:00",
        "error": "authentication expired",
    }


def test_ensure_issue_retries_without_labels_on_create_failure() -> None:
    run_calls: list[list[str]] = []

    def fake_run_json(cmd: list[str], timeout_seconds: int):  # noqa: ANN202
        assert timeout_seconds == 15
        return []

    def fake_run(cmd: list[str], timeout_seconds: int) -> str:
        run_calls.append(cmd)
        if "--label" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="missing label")
        assert timeout_seconds == 15
        return "https://github.com/ennuiweb/psyk-podcast/issues/42\n"

    issue_number, created = ensure_issue(
        "ennuiweb/psyk-podcast",
        build_title(_payload()),
        "body",
        ["queue-alert"],
        timeout_seconds=15,
        run_json_fn=fake_run_json,
        run_fn=fake_run,
    )

    assert issue_number == 42
    assert created is True
    assert len(run_calls) == 2
    assert "--label" in run_calls[0]
    assert "--label" not in run_calls[1]


def test_deliver_alert_to_github_comments_on_existing_issue() -> None:
    commands: list[list[str]] = []
    payload = _payload()

    def fake_run_json(cmd: list[str], timeout_seconds: int):  # noqa: ANN202
        assert timeout_seconds == 20
        return [{"number": 7, "title": build_title(payload)}]

    def fake_run(cmd: list[str], timeout_seconds: int) -> str:
        commands.append(cmd)
        assert timeout_seconds == 20
        return ""

    delivered = deliver_alert_to_github(
        payload,
        repo="ennuiweb/psyk-podcast",
        labels=["queue-alert"],
        timeout_seconds=20,
        run_json_fn=fake_run_json,
        run_fn=fake_run,
    )

    assert delivered == {"repo": "ennuiweb/psyk-podcast", "issue_number": 7, "created": False}
    assert commands and commands[0][:3] == ["gh", "issue", "comment"]
    assert build_comment_body(payload) == commands[0][-1]


def test_handle_queue_alert_wrapper_executes_with_repo_root_import_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    wrapper = repo_root / "scripts" / "handle_queue_alert_github.py"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"issue\" ] && [ \"$2\" = \"list\" ]; then\n"
        "  echo '[]'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"issue\" ] && [ \"$2\" = \"create\" ]; then\n"
        "  echo 'https://github.com/ennuiweb/psyk-podcast/issues/99'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected gh invocation: $@\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, str(wrapper)],
        input=json.dumps(_payload()),
        text=True,
        capture_output=True,
        cwd=repo_root,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "repo": "ennuiweb/psyk-podcast",
        "issue_number": 99,
        "created": True,
    }
