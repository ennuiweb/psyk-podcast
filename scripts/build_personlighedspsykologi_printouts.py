#!/usr/bin/env python3
"""Generate canonical reading printouts for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue import personlighedspsykologi_printouts as printouts
from notebooklm_queue import openai_preprocessing
from notebooklm_queue.gemini_preprocessing import (
    GeminiPreprocessingError,
    has_gemini_api_key,
    preflight_gemini_json_generation,
)

SUPPORTED_PROVIDERS = ("gemini", "openai")


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _all_lecture_keys(source_catalog_path: Path) -> list[str]:
    payload = recursive.load_json(source_catalog_path)
    keys: list[str] = []
    for lecture in payload.get("lectures", []):
        if isinstance(lecture, dict):
            keys.extend(recursive.normalize_lecture_keys(str(lecture.get("lecture_key") or "")))
    return keys


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _default_model_for_provider(provider: str) -> str:
    if provider == "openai":
        return str(openai_preprocessing.DEFAULT_OPENAI_PREPROCESSING_MODEL)
    return str(printouts.DEFAULT_GEMINI_PREPROCESSING_MODEL)


def _has_provider_key(provider: str) -> bool:
    if provider == "openai":
        return bool(openai_preprocessing.has_openai_api_key())
    return bool(has_gemini_api_key())


def _run_provider_preflight(*, provider: str, model: str) -> None:
    if provider == "openai":
        openai_preprocessing.preflight_openai_json_generation(model=model)
        return
    preflight_gemini_json_generation(model=model)


def _make_provider_json_generator(*, provider: str, model: str):
    if provider != "openai":
        return None, printouts.printout_generation_config_metadata()
    backend = openai_preprocessing.make_openai_backend(model=model)

    def _openai_json_generator(**kwargs):
        return openai_preprocessing.generate_json(
            backend=backend,
            system_instruction=str(kwargs["system_instruction"]),
            user_prompt=str(kwargs["user_prompt"]),
            source_paths=list(kwargs.get("source_paths") or []),
            max_output_tokens=int(kwargs.get("max_output_tokens") or 8192),
            response_json_schema=kwargs.get("response_json_schema"),
        )

    return _openai_json_generator, openai_preprocessing.generation_config_metadata()


def _provider_generation_config_metadata(provider: str) -> dict[str, Any]:
    if provider == "openai":
        return openai_preprocessing.generation_config_metadata()
    return printouts.printout_generation_config_metadata()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--source-id", action="append", default=[], help="Generate one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Generate printouts for all selected source families.")
    parser.add_argument("--source-family", action="append", default=[], help="Source family filter; default: reading.")
    parser.add_argument("--all-families", action="store_true", help="Do not filter by source family.")
    parser.add_argument("--source-catalog", default=str(printouts.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-card-dir", default=str(printouts.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument(
        "--revised-lecture-substrate-dir",
        default=str(printouts.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR),
    )
    parser.add_argument("--course-synthesis-path", default=str(printouts.DEFAULT_COURSE_SYNTHESIS_PATH))
    parser.add_argument("--subject-root", default=str(printouts.DEFAULT_SUBJECT_ROOT))
    parser.add_argument("--output-root", default=str(printouts.DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default="gemini")
    parser.add_argument("--model", help="Provider model. Defaults to the repo default for --provider.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing printout artifacts.")
    parser.add_argument(
        "--rerender-existing",
        action="store_true",
        help="Renderer-only mode: normalize/rerender matching existing JSON without provider calls.",
    )
    parser.add_argument(
        "--include-exam-bridge",
        action="store_true",
        help="Render the optional schema-v3 exam bridge sheet when present in generated JSON.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan work without calling Gemini or writing artifacts.")
    parser.add_argument("--continue-on-error", action="store_true", help="Collect per-source errors instead of stopping.")
    parser.add_argument("--no-pdf", action="store_true", help="Write JSON/Markdown only; skip local PDF rendering.")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check that Gemini JSON generation works for the selected model.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the small Gemini JSON preflight before a live run.",
    )
    parser.add_argument("--fail-on-missing-key", action="store_true", help="Fail even in dry-run if Gemini key is absent.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    provider = str(args.provider)
    model = str(args.model or _default_model_for_provider(provider))
    live_generation = not args.dry_run and not (args.rerender_existing and not args.force)
    if live_generation and not _has_provider_key(provider):
        if args.dry_run and not args.fail_on_missing_key:
            pass
        else:
            if provider == "openai":
                raise SystemExit("OPENAI_API_KEY is not set")
            raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        try:
            printouts.preflight_render_toolchain(render_pdf=not args.no_pdf)
            _run_provider_preflight(provider=provider, model=model)
        except (GeminiPreprocessingError, openai_preprocessing.OpenAIPreprocessingError, printouts.PrintoutError) as exc:
            raise SystemExit(str(exc)) from exc
        _print_result({"status": "ok", "provider": provider, "model": model})
        return 0

    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    source_ids = [item.strip() for item in args.source_id if item.strip()]
    if not lecture_keys and not source_ids:
        raise SystemExit("select --all, --lectures, or --source-id")
    if live_generation and not args.skip_preflight:
        try:
            _run_provider_preflight(provider=provider, model=model)
        except (GeminiPreprocessingError, openai_preprocessing.OpenAIPreprocessingError) as exc:
            raise SystemExit(str(exc)) from exc
    if live_generation:
        provider_json_generator, generation_config_metadata = _make_provider_json_generator(provider=provider, model=model)
    else:
        provider_json_generator = None
        generation_config_metadata = _provider_generation_config_metadata(provider)
    variant_prompt_text = printouts.read_problem_driven_variant_prompt(REPO_ROOT)

    result = printouts.build_printouts(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=source_catalog_path,
        source_card_dir=_resolve(args.source_card_dir),
        revised_lecture_substrate_dir=_resolve(args.revised_lecture_substrate_dir),
        course_synthesis_path=_resolve(args.course_synthesis_path),
        output_root=_resolve(args.output_root),
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=printouts.parse_source_families(
            args.source_family,
            all_families=bool(args.all_families),
        ),
        model=model,
        json_generator=provider_json_generator,
        render_pdf=not args.no_pdf,
        force=args.force,
        rerender_existing=args.rerender_existing,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        prompt_version=printouts.PROBLEM_DRIVEN_PROMPT_VERSION,
        system_instruction=printouts.problem_driven_system_instruction(),
        user_prompt_builder=printouts.problem_driven_user_prompt_builder(variant_prompt_text=variant_prompt_text),
        variant_metadata=printouts.problem_driven_variant_metadata(
            mode="canonical_main",
            render_completion_markers=False,
            render_exam_bridge=bool(args.include_exam_bridge),
        ),
        generation_provider=provider,
        generation_config_metadata_override=generation_config_metadata,
        output_layout=printouts.OUTPUT_LAYOUT_CANONICAL,
    )
    _print_result(result)
    return 1 if result.get("error_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
