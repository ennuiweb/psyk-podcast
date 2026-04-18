#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_generate_week_module():
    module_path = Path(__file__).with_name("generate_week.py")
    spec = importlib.util.spec_from_file_location("generate_week", module_path)
    if not spec or not spec.loader:
        raise SystemExit(f"Unable to load generate_week.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    mod = _load_generate_week_module()

    parser = argparse.ArgumentParser(description="Generate one NotebookLM meta-prompt sidecar.")
    parser.add_argument(
        "--prompt-config",
        default="notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json",
        help="Prompt configuration JSON used for meta_prompting defaults.",
    )
    parser.add_argument(
        "--prompt-type",
        required=True,
        choices=mod.AUDIO_PROMPT_TYPES,
        help="Prompt scenario to generate pre-analysis for.",
    )
    parser.add_argument(
        "--course-title",
        default="Personlighedspsykologi",
        help="Course title for the meta-analysis prompt.",
    )
    parser.add_argument(
        "--reading-source",
        action="append",
        default=[],
        help="Path to a reading source file. Repeat as needed.",
    )
    parser.add_argument(
        "--slide-source",
        action="append",
        default=[],
        help="Path to a slide source file. Repeat as needed.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the generated sidecar Markdown.",
    )
    parser.add_argument(
        "--label",
        help="Optional display label for the job. Defaults to the output stem.",
    )
    parser.add_argument(
        "--week-label",
        help="Optional lecture/week label, e.g. W01L1.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated Markdown instead of writing it.",
    )
    args = parser.parse_args()

    reading_paths = [Path(value).expanduser().resolve() for value in args.reading_source]
    slide_paths = [Path(value).expanduser().resolve() for value in args.slide_source]
    if not reading_paths and not slide_paths:
        raise SystemExit("Provide at least one --reading-source or --slide-source.")

    repo_root = mod.find_repo_root(Path(__file__).resolve())
    prompt_config_path = (repo_root / args.prompt_config).resolve()
    config = mod.read_json(prompt_config_path)
    meta_prompting = mod.normalize_meta_prompting(config.get("meta_prompting"))

    source_items = [
        mod.SourceItem(path=path, base_name=path.stem, source_type="reading")
        for path in reading_paths
    ]
    source_items.extend(
        mod.SourceItem(path=path, base_name=path.stem, source_type="slide", slide_subcategory="lecture")
        for path in slide_paths
    )

    client, anthropic_module = mod._anthropic_client_for_meta_prompting()
    output_path = Path(args.output).expanduser().resolve()
    label = args.label or output_path.stem
    job = mod.MetaPromptJob(
        prompt_type=args.prompt_type,
        output_path=output_path,
        label=label,
        source_items=tuple(source_items),
        week_label=args.week_label,
    )
    content = mod.generate_meta_prompt_markdown(
        job=job,
        course_title=args.course_title,
        meta_prompting=meta_prompting,
        client=client,
        anthropic_module=anthropic_module,
    )

    if args.dry_run:
        print(content)
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
