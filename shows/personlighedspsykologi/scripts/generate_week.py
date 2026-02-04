#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
import shlex


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


def ensure_prompt(_: str, value: str) -> str:
    return value.strip()


def build_language_variants(config: dict) -> list[dict]:
    variants: list[dict] = []
    raw = config.get("languages")
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                code = entry.strip()
                if code:
                    variants.append({"code": code, "suffix": "", "title_suffix": ""})
                continue
            if not isinstance(entry, dict):
                continue
            code = (entry.get("code") or "").strip()
            if not code:
                continue
            suffix = (entry.get("suffix") or "").strip()
            title_suffix = (entry.get("title_suffix") or suffix).strip()
            variants.append({"code": code, "suffix": suffix, "title_suffix": title_suffix})

    if not variants:
        code = (config.get("language") or "").strip()
        variants.append({"code": code or None, "suffix": "", "title_suffix": ""})

    return variants


def apply_suffix(name: str, suffix: str) -> str:
    return f"{name} {suffix}".strip() if suffix else name


def apply_path_suffix(path: Path, suffix: str) -> Path:
    if not suffix:
        return path
    return path.with_name(f"{path.stem} {suffix}{path.suffix}")


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
    parser.add_argument("--week", help="Single week label, e.g. W04")
    parser.add_argument(
        "--weeks",
        help="Comma-separated week labels, e.g. W01,W02",
    )
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
    parser.add_argument(
        "--print-downloads",
        action="store_true",
        help="Print commands to wait and download audio for this run (non-blocking only).",
    )
    args = parser.parse_args()

    if not args.week and not args.weeks:
        raise SystemExit("Provide --week or --weeks.")

    week_inputs: list[str] = []
    if args.week:
        week_inputs.append(args.week)
    if args.weeks:
        week_inputs.extend(part.strip() for part in args.weeks.split(",") if part.strip())
    if not week_inputs:
        raise SystemExit("No valid weeks provided.")

    repo_root = Path(__file__).resolve().parents[3]
    sources_root = repo_root / args.sources_root
    reading_key = repo_root / args.reading_key
    prompt_config = repo_root / args.prompt_config
    output_root = repo_root / args.output_root
    generator_script = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"
    notebooklm_cli = repo_root / "notebooklm-podcast-auto" / ".venv" / "bin" / "notebooklm"

    config = read_json(prompt_config)
    language_variants = build_language_variants(config)
    weekly_cfg = config.get("weekly_overview", {})
    per_cfg = config.get("per_reading", {})
    brief_cfg = config.get("brief", {})

    request_logs: list[Path] = []

    for week_input in week_inputs:
        week_dir = find_week_dir(sources_root, week_input)
        week_label = week_dir.name.split(" ", 1)[0].upper()

        week_output_dir = output_root / week_label
        week_output_dir.mkdir(parents=True, exist_ok=True)

        sources = list_source_files(week_dir)
        if not sources:
            raise SystemExit(f"No source files found in {week_dir}")

        missing = week_has_missing(reading_key, week_label)

        planned_lines: list[str] = []
        weekly_output = week_output_dir / f"{week_label} - Alle kilder.mp3"
        if not missing:
            for variant in language_variants:
                planned_lines.append(
                    f"WEEKLY ({variant['code'] or 'default'}): "
                    f"{apply_path_suffix(weekly_output, variant['suffix'])}"
                )
        else:
            planned_lines.append(f"SKIP WEEKLY (missing readings): {weekly_output}")

        for source in sources:
            base_name = source.stem
            per_output = week_output_dir / f"{week_label} - {base_name}.mp3"
            for variant in language_variants:
                planned_lines.append(
                    f"READING ({variant['code'] or 'default'}): "
                    f"{apply_path_suffix(per_output, variant['suffix'])}"
                )
            if "Grundbog kapitel" in source.name:
                title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                brief_name = f"{title_prefix} {week_label} - {base_name}.mp3"
                for variant in language_variants:
                    planned_lines.append(
                        f"BRIEF ({variant['code'] or 'default'}): "
                        f"{apply_path_suffix(week_output_dir / brief_name, variant['suffix'])}"
                    )

        if args.dry_run:
            print(f"## {week_label}")
            for line in planned_lines:
                print(line)
            continue

        if not missing:
            weekly_sources_file = week_output_dir / "sources_week.txt"
            weekly_sources_file.write_text("\n".join(str(p) for p in sources) + "\n", encoding="utf-8")
            for variant in language_variants:
                output_path = apply_path_suffix(weekly_output, variant["suffix"])
                run_generate(
                    Path(sys.executable),
                    generator_script,
                    sources_file=weekly_sources_file,
                    source_path=None,
                    notebook_title=apply_suffix(
                        f"Personlighedspsykologi {week_label} Alle kilder",
                        variant["title_suffix"],
                    ),
                    instructions=ensure_prompt("weekly_overview", weekly_cfg.get("prompt", "")),
                    audio_format=weekly_cfg.get("format", "deep-dive"),
                    audio_length=weekly_cfg.get("length", "long"),
                    language=variant["code"],
                    output_path=output_path,
                    wait=args.wait,
                    skip_existing=args.skip_existing,
                    source_timeout=args.source_timeout,
                    generation_timeout=args.generation_timeout,
                )
                request_logs.append(output_path.with_suffix(output_path.suffix + ".request.json"))
        else:
            print(f"Skipping weekly overview for {week_label} (missing readings).")

        for source in sources:
            base_name = source.stem
            per_output = week_output_dir / f"{week_label} - {base_name}.mp3"
            for variant in language_variants:
                output_path = apply_path_suffix(per_output, variant["suffix"])
                run_generate(
                    Path(sys.executable),
                    generator_script,
                    sources_file=None,
                    source_path=source,
                    notebook_title=apply_suffix(
                        f"Personlighedspsykologi {week_label} {base_name}",
                        variant["title_suffix"],
                    ),
                    instructions=ensure_prompt("per_reading", per_cfg.get("prompt", "")),
                    audio_format=per_cfg.get("format", "deep-dive"),
                    audio_length=per_cfg.get("length", "default"),
                    language=variant["code"],
                    output_path=output_path,
                    wait=args.wait,
                    skip_existing=args.skip_existing,
                    source_timeout=args.source_timeout,
                    generation_timeout=args.generation_timeout,
                )
                request_logs.append(output_path.with_suffix(output_path.suffix + ".request.json"))

            if "Grundbog kapitel" in source.name:
                title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                brief_name = f"{title_prefix} {week_label} - {base_name}.mp3"
                brief_output = week_output_dir / brief_name
                for variant in language_variants:
                    output_path = apply_path_suffix(brief_output, variant["suffix"])
                    run_generate(
                        Path(sys.executable),
                        generator_script,
                        sources_file=None,
                        source_path=source,
                        notebook_title=apply_suffix(
                            f"Personlighedspsykologi {week_label} [Brief] {base_name}",
                            variant["title_suffix"],
                        ),
                        instructions=ensure_prompt("brief", brief_cfg.get("prompt", "")),
                        audio_format=brief_cfg.get("format", "brief"),
                        audio_length=None,
                        language=variant["code"],
                        output_path=output_path,
                        wait=args.wait,
                        skip_existing=args.skip_existing,
                        source_timeout=args.source_timeout,
                        generation_timeout=args.generation_timeout,
                    )
                    request_logs.append(output_path.with_suffix(output_path.suffix + ".request.json"))

    if args.print_downloads:
        commands: list[str] = []
        for log_path in request_logs:
            if not log_path.exists():
                continue
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            notebook_id = payload.get("notebook_id")
            artifact_id = payload.get("artifact_id")
            output_path = payload.get("output_path")
            if not (notebook_id and artifact_id and output_path):
                continue
            cli = shlex.quote(str(notebooklm_cli))
            out = shlex.quote(str(output_path))
            commands.append(
                f"{cli} artifact wait {artifact_id} -n {notebook_id}"
            )
            commands.append(
                f"{cli} download audio {out} -a {artifact_id} -n {notebook_id}"
            )

        if commands:
            print("\n# Wait + download commands")
            for cmd in commands:
                print(cmd)
        else:
            print("\nNo request logs found. Run without --wait to generate them.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
