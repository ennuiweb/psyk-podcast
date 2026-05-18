#!/usr/bin/env python3
"""Export recent Codex prompts for a specific working directory."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable


DEFAULT_LIMIT = 100


@dataclass(frozen=True)
class PromptEntry:
    timestamp: str
    session_id: str
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write the most recent Codex prompts for a working directory to a "
            "Markdown file."
        )
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Only include sessions whose cwd exactly matches this path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Number of prompts to export (default: {DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path.home() / ".codex",
        help="Path to the local Codex data directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "codex-last-100-prompts.md",
        help="Where to write the exported prompts.",
    )
    return parser.parse_args()


def canonicalize_path(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def iter_session_files(codex_home: Path) -> Iterable[Path]:
    for dirname in ("sessions", "archived_sessions"):
        base = codex_home / dirname
        if not base.is_dir():
            continue
        yield from base.rglob("*.jsonl")


def extract_prompts(session_path: Path, target_cwd: str) -> list[PromptEntry]:
    prompts: list[PromptEntry] = []
    session_id = ""
    session_matches = False

    with session_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                # Active session files can contain a partial last line while Codex
                # is still writing to them.
                continue

            if entry.get("type") == "session_meta":
                payload = entry.get("payload", {})
                session_id = payload.get("id", "")
                session_cwd = payload.get("cwd")
                session_matches = bool(session_cwd) and (
                    canonicalize_path(session_cwd) == target_cwd
                )
                continue

            if not session_matches or entry.get("type") != "event_msg":
                continue

            payload = entry.get("payload", {})
            if payload.get("type") != "user_message":
                continue

            text = (payload.get("message") or "").strip()
            if not text:
                text = "\n\n".join(
                    element.get("text", "").strip()
                    for element in payload.get("text_elements", [])
                    if element.get("text")
                ).strip()

            if not text:
                continue

            prompts.append(
                PromptEntry(
                    timestamp=entry.get("timestamp", ""),
                    session_id=session_id,
                    text=text,
                )
            )

    return prompts


def render_markdown(target_cwd: str, codex_home: Path, prompts: list[PromptEntry]) -> str:
    generated_at = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    lines = [
        f"# Last {len(prompts)} Codex prompts for `{target_cwd}`",
        "",
        f"- Generated: `{generated_at}`",
        f"- Source: `{codex_home}`",
        "- Order: oldest to newest within the selected window",
        "",
    ]

    if not prompts:
        lines.append("_No matching prompts found._")
        return "\n".join(lines) + "\n"

    for index, prompt in enumerate(prompts, start=1):
        lines.extend(
            [
                f"## {index}. `{prompt.timestamp}`",
                "",
                "```text",
                prompt.text,
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    target_cwd = canonicalize_path(args.cwd)
    codex_home = args.codex_home.expanduser().resolve(strict=False)
    output_path = args.output.expanduser().resolve(strict=False)

    prompts: list[PromptEntry] = []
    for session_path in iter_session_files(codex_home):
        prompts.extend(extract_prompts(session_path, target_cwd))

    prompts.sort(key=lambda prompt: (prompt.timestamp, prompt.session_id, prompt.text))
    prompts = prompts[-max(args.limit, 0) :]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_markdown(target_cwd=target_cwd, codex_home=codex_home, prompts=prompts),
        encoding="utf-8",
    )

    print(f"Wrote {len(prompts)} prompts to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
