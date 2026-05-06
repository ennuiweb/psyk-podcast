"""GitHub issue transport for queue alert events."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable

from .processes import run_process

DEFAULT_REPO = "ennuiweb/psyk-podcast"
DEFAULT_LABELS: tuple[str, ...] = ()
DEFAULT_GITHUB_TIMEOUT_SECONDS = int(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_GITHUB_TIMEOUT_SECONDS") or "30")

RunJsonFn = Callable[[list[str], int], Any]
RunFn = Callable[[list[str], int], str]
REQUIRED_ALERT_FIELDS: tuple[str, ...] = ("kind", "show_slug", "summary")


def run_json(cmd: list[str], timeout_seconds: int) -> Any:
    completed = run_process(
        cmd,
        cwd=os.getcwd(),
        timeout_seconds=timeout_seconds,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            cmd,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return json.loads(completed.stdout)


def run(cmd: list[str], timeout_seconds: int) -> str:
    completed = run_process(
        cmd,
        cwd=os.getcwd(),
        timeout_seconds=timeout_seconds,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            cmd,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed.stdout


def build_title(payload: dict[str, Any]) -> str:
    kind = str(payload.get("kind") or "queue_alert").replace("_", " ")
    show_slug = str(payload.get("show_slug") or "unknown-show")
    return f"[Queue Alert] {kind} - {show_slug}"


def build_body(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(payload.get("summary") or "Queue alert"),
            "",
            f"- Kind: `{payload.get('kind') or ''}`",
            f"- Show: `{payload.get('show_slug') or ''}`",
            f"- Lecture: `{payload.get('lecture_key') or ''}`",
            f"- Job: `{payload.get('job_id') or ''}`",
            f"- State: `{payload.get('state') or ''}`",
            f"- Attempt: `{payload.get('attempt_count') or ''}`",
            f"- Host: `{payload.get('host') or ''}`",
            f"- Occurred at: `{payload.get('occurred_at') or ''}`",
            "",
            "```text",
            str(payload.get("error") or "").strip(),
            "```",
        ]
    ).strip() + "\n"


def build_comment_body(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"New occurrence at `{payload.get('occurred_at') or ''}`",
            "",
            f"- Lecture: `{payload.get('lecture_key') or ''}`",
            f"- Job: `{payload.get('job_id') or ''}`",
            f"- State: `{payload.get('state') or ''}`",
            "",
            "```text",
            str(payload.get("error") or "").strip(),
            "```",
        ]
    ).strip()


def parse_labels(raw: str | None) -> list[str]:
    value = str(raw or ",".join(DEFAULT_LABELS))
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Queue alert payload must be a JSON object.")
    missing = [field for field in REQUIRED_ALERT_FIELDS if not str(payload.get(field) or "").strip()]
    if missing:
        missing_fields = ", ".join(missing)
        raise ValueError(f"Queue alert payload missing required field(s): {missing_fields}")
    return payload


def ensure_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    *,
    timeout_seconds: int,
    run_json_fn: RunJsonFn = run_json,
    run_fn: RunFn = run,
) -> tuple[int, bool]:
    issues = run_json_fn(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f'"{title}" in:title',
            "--json",
            "number,title",
        ],
        timeout_seconds,
    )
    for issue in issues:
        if str(issue.get("title") or "").strip() == title:
            return int(issue["number"]), False

    create_cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        title,
        "--body",
        body,
    ]
    if labels:
        create_cmd.extend(["--label", ",".join(labels)])
    try:
        created = run_fn(create_cmd, timeout_seconds)
    except subprocess.CalledProcessError:
        created = run_fn(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--body",
                body,
            ],
            timeout_seconds,
        )
    issue_url = created.strip().splitlines()[-1]
    issue_number = issue_url.rstrip("/").rsplit("/", 1)[-1]
    return int(issue_number), True


def deliver_alert_to_github(
    payload: dict[str, Any],
    *,
    repo: str,
    labels: list[str],
    timeout_seconds: int,
    run_json_fn: RunJsonFn = run_json,
    run_fn: RunFn = run,
) -> dict[str, Any]:
    payload = validate_payload(payload)
    title = build_title(payload)
    body = build_body(payload)
    issue_number, created = ensure_issue(
        repo,
        title,
        body,
        labels,
        timeout_seconds=timeout_seconds,
        run_json_fn=run_json_fn,
        run_fn=run_fn,
    )

    if not created:
        run_fn(
            [
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body",
                build_comment_body(payload),
            ],
            timeout_seconds,
        )
    return {"repo": repo, "issue_number": issue_number, "created": created}


def main() -> int:
    try:
        payload = validate_payload(json.load(sys.stdin))
    except (json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    repo = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_GITHUB_REPO") or DEFAULT_REPO).strip() or DEFAULT_REPO
    labels = parse_labels(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_GITHUB_LABELS"))
    delivered = deliver_alert_to_github(
        payload,
        repo=repo,
        labels=labels,
        timeout_seconds=DEFAULT_GITHUB_TIMEOUT_SECONDS,
    )
    print(json.dumps(delivered))
    return 0
