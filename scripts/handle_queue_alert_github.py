#!/usr/bin/env python3
"""Create or update a GitHub issue for a queue alert."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


DEFAULT_REPO = "ennuiweb/psyk-podcast"
DEFAULT_LABELS: tuple[str, ...] = ()


def run_json(cmd: list[str]) -> Any:
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


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


def ensure_issue(repo: str, title: str, body: str, labels: list[str]) -> tuple[int, bool]:
    issues = run_json(
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
        ]
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
        created = run(create_cmd)
    except subprocess.CalledProcessError:
        created = run(
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
            ]
        )
    issue_url = created.stdout.strip().splitlines()[-1]
    issue_number = issue_url.rstrip("/").rsplit("/", 1)[-1]
    return int(issue_number), True


def main() -> int:
    payload = json.load(sys.stdin)
    repo = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_GITHUB_REPO") or DEFAULT_REPO).strip() or DEFAULT_REPO
    labels = [
        item.strip()
        for item in str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_GITHUB_LABELS") or ",".join(DEFAULT_LABELS)).split(",")
        if item.strip()
    ]
    title = build_title(payload)
    body = build_body(payload)
    issue_number, created = ensure_issue(repo, title, body, labels)

    if not created:
        comment_body = "\n".join(
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
        run(
            [
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body",
                comment_body,
            ]
        )
    print(json.dumps({"repo": repo, "issue_number": issue_number, "created": created}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
