#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def parse_weeks(week: str | None, weeks: str | None) -> list[str]:
    if not week and not weeks:
        raise SystemExit("Provide --week or --weeks.")
    items: list[str] = []
    if week:
        items.append(week)
    if weeks:
        items.extend(part.strip() for part in weeks.split(",") if part.strip())
    if not items:
        raise SystemExit("No valid weeks provided.")
    return items


def find_week_dir(root: Path, week: str) -> Path:
    week = week.upper()
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.upper() == week]
    if not candidates:
        raise SystemExit(f"No output folder found for {week} under {root}")
    return candidates[0]


def run_cmd(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"Error: {exc}")
        return False


def wait_and_download(
    notebooklm: Path,
    artifact_id: str,
    notebook_id: str,
    output_path: Path,
    timeout: int | None,
    interval: int | None,
) -> None:
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing: {output_path}")
        return

    wait_cmd = [str(notebooklm), "artifact", "wait", artifact_id, "-n", notebook_id]
    if timeout is not None:
        wait_cmd.extend(["--timeout", str(timeout)])
    if interval is not None:
        wait_cmd.extend(["--interval", str(interval)])

    if not run_cmd(wait_cmd):
        return

    download_cmd = [
        str(notebooklm),
        "download",
        "audio",
        str(output_path),
        "-a",
        artifact_id,
        "-n",
        notebook_id,
    ]
    run_cmd(download_cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait and download all podcasts for a week from request logs."
    )
    parser.add_argument("--week", help="Single week label, e.g. W01")
    parser.add_argument("--weeks", help="Comma-separated week labels, e.g. W01,W02")
    parser.add_argument(
        "--output-root",
        default="shows/personlighedspsykologi/output",
        help="Root folder containing W## output folders.",
    )
    parser.add_argument(
        "--notebooklm",
        default="notebooklm-podcast-auto/.venv/bin/notebooklm",
        help="Path to the notebooklm CLI.",
    )
    parser.add_argument("--timeout", type=int, help="Seconds to wait for completion.")
    parser.add_argument("--interval", type=int, help="Polling interval in seconds.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without waiting/downloading.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    output_root = repo_root / args.output_root
    notebooklm = repo_root / args.notebooklm

    week_inputs = parse_weeks(args.week, args.weeks)

    for week_input in week_inputs:
        week_dir = find_week_dir(output_root, week_input)
        request_logs = sorted(week_dir.glob("*.request.json"))
        if not request_logs:
            print(f"No request logs found in {week_dir}")
            continue

        print(f"## {week_dir.name}")
        for log_path in request_logs:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            notebook_id = payload.get("notebook_id")
            artifact_id = payload.get("artifact_id")
            output_path = payload.get("output_path")
            if not (notebook_id and artifact_id and output_path):
                print(f"Skipping malformed log: {log_path}")
                continue

            output_file = Path(output_path)
            if args.dry_run:
                print(f"WAIT: {artifact_id} (notebook {notebook_id})")
                print(f"DOWNLOAD: {output_file}")
                continue

            wait_and_download(
                notebooklm,
                artifact_id,
                notebook_id,
                output_file,
                args.timeout,
                args.interval,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
