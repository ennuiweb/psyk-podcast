#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_week_dir(root: Path, week: str) -> Path:
    week = week.upper()
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.upper().startswith(week)]
    if not candidates:
        raise SystemExit(f"No week folder found for {week} under {root}")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise SystemExit(f"Multiple week folders match {week}: {names}")
    return candidates[0]


def list_source_files(week_dir: Path) -> list[Path]:
    files = []
    for entry in sorted(week_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file():
            files.append(entry)
    return files


def week_has_missing(reading_key: Path, week: str) -> bool:
    week = week.upper()
    header = re.compile(rf"^\\*\\*{re.escape(week)}\\b")
    in_section = False
    for line in reading_key.read_text(encoding="utf-8").splitlines():
        if header.match(line.strip()):
            in_section = True
            continue
        if in_section and line.startswith("**W"):
            break
        if in_section and "MISSING:" in line:
            return True
    return False


def ensure_prompt(label: str, value: str) -> str:
    if not value.strip():
        raise SystemExit(f"Prompt for {label} is empty. Fill it in prompt_config.json.")
    return value.strip()


def run_generate(
    python: Path,
    script: Path,
    *,
    sources_file: Path | None,
    source_path: Path | None,
    notebook_title: str,
    instructions: str,
    audio_format: str,
    audio_length: str | None,
    language: str | None,
    output_path: Path,
    wait: bool,
    skip_existing: bool,
    source_timeout: float | None,
    generation_timeout: float | None,
) -> None:
    cmd = [
        str(python),
        str(script),
        "--notebook-title",
        notebook_title,
        "--reuse-notebook",
        "--instructions",
        instructions,
        "--audio-format",
        audio_format,
        "--output",
        str(output_path),
    ]
    if audio_length:
        cmd.extend(["--audio-length", audio_length])
    if language:
        cmd.extend(["--language", language])
    if sources_file:
        cmd.extend(["--sources-file", str(sources_file)])
    if source_path:
        cmd.extend(["--source", str(source_path)])
    if wait:
        cmd.append("--wait")
    if skip_existing:
        cmd.append("--skip-existing")
    if source_timeout is not None:
        cmd.extend(["--source-timeout", str(source_timeout)])
    if generation_timeout is not None:
        cmd.extend(["--generation-timeout", str(generation_timeout)])
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all episodes for a given week.")
    parser.add_argument("--week", required=True, help="Week label, e.g. W04")
    parser.add_argument(
        "--sources-root",
        default="shows/personlighedspsykologi/sources",
        help="Root folder containing week source folders.",
    )
    parser.add_argument(
        "--reading-key",
        default="shows/personlighedspsykologi/docs/reading-file-key.md",
        help="Reading key file (for missing checks).",
    )
    parser.add_argument(
        "--prompt-config",
        default="shows/personlighedspsykologi/prompt_config.json",
        help="Prompt configuration JSON.",
    )
    parser.add_argument(
        "--output-root",
        default="shows/personlighedspsykologi/output",
        help="Where to place generated MP3s.",
    )
    parser.add_argument("--wait", action="store_true", help="Wait for generation to finish.")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip generation when output file already exists.",
    )
    parser.add_argument(
        "--source-timeout",
        type=float,
        help="Seconds to wait for each source (passed through).",
    )
    parser.add_argument(
        "--generation-timeout",
        type=float,
        help="Seconds to wait for generation (passed through).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned outputs and exit without generating audio.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    sources_root = repo_root / args.sources_root
    reading_key = repo_root / args.reading_key
    prompt_config = repo_root / args.prompt_config
    output_root = repo_root / args.output_root
    generator_script = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"

    config = read_json(prompt_config)
    language = (config.get("language") or "").strip() or None
    weekly_cfg = config.get("weekly_overview", {})
    per_cfg = config.get("per_reading", {})
    brief_cfg = config.get("brief", {})

    week_dir = find_week_dir(sources_root, args.week)
    week_label = week_dir.name.split(" ", 1)[0].upper()
    week_topic = week_dir.name[len(week_label):].strip()

    week_output_dir = output_root / week_label
    week_output_dir.mkdir(parents=True, exist_ok=True)

    sources = list_source_files(week_dir)
    if not sources:
        raise SystemExit(f"No source files found in {week_dir}")

    missing = week_has_missing(reading_key, week_label)

    planned_lines: list[str] = []
    weekly_output = week_output_dir / f"{week_label} - Alle kilder.mp3"
    if not missing:
        planned_lines.append(f"WEEKLY: {weekly_output}")
    else:
        planned_lines.append(f"SKIP WEEKLY (missing readings): {weekly_output}")

    for source in sources:
        base_name = source.stem
        per_output = week_output_dir / f"{week_label} - {base_name}.mp3"
        planned_lines.append(f"READING: {per_output}")
        if "Grundbog kapitel" in source.name:
            title_prefix = brief_cfg.get("title_prefix", "[Brief]")
            brief_name = f"{title_prefix} {week_label} - {base_name}.mp3"
            planned_lines.append(f"BRIEF: {week_output_dir / brief_name}")

    if args.dry_run:
        for line in planned_lines:
            print(line)
        return 0

    if not missing:
        weekly_sources_file = week_output_dir / "sources_week.txt"
        weekly_sources_file.write_text("\n".join(str(p) for p in sources) + "\n", encoding="utf-8")
        run_generate(
            Path(sys.executable),
            generator_script,
            sources_file=weekly_sources_file,
            source_path=None,
            notebook_title=f"Personlighedspsykologi {week_label} Alle kilder",
            instructions=ensure_prompt("weekly_overview", weekly_cfg.get("prompt", "")),
            audio_format=weekly_cfg.get("format", "deep-dive"),
            audio_length=weekly_cfg.get("length", "long"),
            language=language,
            output_path=weekly_output,
            wait=args.wait,
            skip_existing=args.skip_existing,
            source_timeout=args.source_timeout,
            generation_timeout=args.generation_timeout,
        )
    else:
        print(f"Skipping weekly overview for {week_label} (missing readings).")

    for source in sources:
        base_name = source.stem
        run_generate(
            Path(sys.executable),
            generator_script,
            sources_file=None,
            source_path=source,
            notebook_title=f"Personlighedspsykologi {week_label} {base_name}",
            instructions=ensure_prompt("per_reading", per_cfg.get("prompt", "")),
            audio_format=per_cfg.get("format", "deep-dive"),
            audio_length=per_cfg.get("length", "default"),
            language=language,
            output_path=week_output_dir / f"{week_label} - {base_name}.mp3",
            wait=args.wait,
            skip_existing=args.skip_existing,
            source_timeout=args.source_timeout,
            generation_timeout=args.generation_timeout,
        )

        if "Grundbog kapitel" in source.name:
            title_prefix = brief_cfg.get("title_prefix", "[Brief]")
            brief_name = f"{title_prefix} {week_label} - {base_name}.mp3"
            run_generate(
                Path(sys.executable),
                generator_script,
                sources_file=None,
                source_path=source,
                notebook_title=f"Personlighedspsykologi {week_label} [Brief] {base_name}",
                instructions=ensure_prompt("brief", brief_cfg.get("prompt", "")),
                audio_format=brief_cfg.get("format", "brief"),
                audio_length=None,
                language=language,
                output_path=week_output_dir / brief_name,
                wait=args.wait,
                skip_existing=args.skip_existing,
                source_timeout=args.source_timeout,
                generation_timeout=args.generation_timeout,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
