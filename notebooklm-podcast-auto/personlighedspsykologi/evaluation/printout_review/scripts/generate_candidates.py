#!/usr/bin/env python3
"""Generate experimental printout candidates into a review run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import printout_engine
from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue.gemini_preprocessing import (
    GeminiPreprocessingError,
    has_gemini_api_key,
    preflight_gemini_json_generation,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

DEFAULT_DESIGN_DOC = "shows/personlighedspsykologi-en/docs/problem-driven-printouts.md"
DEFAULT_PROMPT_VERSION = "personlighedspsykologi-reading-printouts-problem-driven-v1"
DEFAULT_VARIANT_KEY = "problem_driven_v1"


def _resolve(path_value: str | Path, *, base: Path | None = None) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    anchor = base or REPO_ROOT
    return (anchor / path).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _relative_to(base: Path, target: Path) -> str:
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def _is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _ensure_safe_output_root(candidate_output_root: Path, canonical_output_root: Path) -> None:
    if candidate_output_root.resolve() == canonical_output_root.resolve():
        raise SystemExit("candidate output root must not equal the canonical output root")
    if _is_inside(canonical_output_root, candidate_output_root):
        raise SystemExit("candidate output root must not live under the canonical output root")


def _variant_system_instruction() -> str:
    return "\n".join(
        [
            printout_engine.printout_system_instruction(),
            "This run is an experimental prompt overlay.",
            "Keep the schema-v3 shape and validation contract unchanged.",
            "Let the user-prompt variant instructions change the pedagogical feel, not the artifact structure.",
        ]
    )


def _variant_user_prompt(
    *,
    variant_key: str,
    variant_prompt_text: str,
    source: dict[str, Any],
    source_card: dict[str, Any],
    lecture_context: dict[str, Any] | None,
    course_context: dict[str, Any] | None,
) -> str:
    base_prompt = printout_engine.printout_user_prompt(
        source=source,
        source_card=source_card,
        lecture_context=lecture_context,
        course_context=course_context,
    )
    return "\n\n".join(
        [
            "This is an experimental printout-review run.",
            f"Variant key: {variant_key}",
            "Apply the following variant instructions while keeping the same JSON contract and required keys.",
            variant_prompt_text.strip(),
            base_prompt,
        ]
    )


def _build_prompt_capture_builder(
    *,
    run_dir: Path,
    source_id: str,
    variant_key: str,
    variant_prompt_text: str,
) -> tuple[str, str, printout_engine.UserPromptBuilder]:
    system_rel = f"prompts/{source_id}.system.txt"
    user_rel = f"prompts/{source_id}.user.txt"
    system_text = _variant_system_instruction()
    _write_text(run_dir / system_rel, system_text)

    def builder(
        *,
        source: dict[str, Any],
        source_card: dict[str, Any],
        lecture_context: dict[str, Any] | None,
        course_context: dict[str, Any] | None,
    ) -> str:
        prompt = _variant_user_prompt(
            variant_key=variant_key,
            variant_prompt_text=variant_prompt_text,
            source=source,
            source_card=source_card,
            lecture_context=lecture_context,
            course_context=course_context,
        )
        _write_text(run_dir / user_rel, prompt)
        return prompt

    return system_rel, user_rel, builder


def _refresh_summary(manifest: dict[str, Any]) -> None:
    entries = manifest.get("entries", [])
    written = sum(1 for entry in entries if entry.get("candidate", {}).get("status") == "written")
    rerendered = sum(1 for entry in entries if entry.get("candidate", {}).get("status") == "rerendered_existing")
    skipped = sum(1 for entry in entries if entry.get("candidate", {}).get("status") == "skipped_existing")
    errors = sum(1 for entry in entries if entry.get("candidate", {}).get("status") == "error")
    manifest["summary"] = {
        "source_count": len(entries),
        "written_count": written,
        "rerendered_count": rerendered,
        "skipped_count": skipped,
        "error_count": errors,
    }
    manifest["status"] = "generate_partial" if errors else "generated"
    manifest["updated_at"] = utc_now_iso()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to a printout review manifest.json.")
    parser.add_argument("--source-id", action="append", default=[], help="Generate only one source id; repeatable.")
    parser.add_argument(
        "--variant-prompt",
        help="Optional override for the variant prompt markdown. Defaults to the path recorded in the manifest.",
    )
    parser.add_argument("--source-catalog", default=str(printout_engine.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-card-dir", default=str(printout_engine.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument(
        "--revised-lecture-substrate-dir",
        default=str(printout_engine.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR),
    )
    parser.add_argument("--course-synthesis-path", default=str(printout_engine.DEFAULT_COURSE_SYNTHESIS_PATH))
    parser.add_argument("--subject-root", default=str(printout_engine.DEFAULT_SUBJECT_ROOT))
    parser.add_argument("--model", default=printout_engine.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--force", action="store_true", help="Overwrite existing candidate scaffold artifacts.")
    parser.add_argument(
        "--rerender-existing",
        action="store_true",
        help="Normalize and rerender existing candidate JSON artifacts without calling Gemini unless --force is also set.",
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
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = _read_json(manifest_path)
    run_dir = manifest_path.parent
    variant_prompt_rel = str(manifest.get("variant_prompt_path") or "")
    variant_prompt_path = (
        _resolve(args.variant_prompt, base=run_dir)
        if args.variant_prompt
        else _resolve(variant_prompt_rel, base=REPO_ROOT)
    )
    variant_prompt_text = variant_prompt_path.read_text(encoding="utf-8")
    candidate_output_root = Path(manifest["candidate_output_root"]).expanduser().resolve()
    canonical_output_root = Path(
        manifest.get("canonical_output_root")
        or (REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/output")
    ).expanduser().resolve()
    _ensure_safe_output_root(candidate_output_root, canonical_output_root)

    live_generation = not args.dry_run and not (args.rerender_existing and not args.force)
    if live_generation and not has_gemini_api_key():
        if args.dry_run and not args.fail_on_missing_key:
            pass
        else:
            raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps({"status": "ok", "model": str(args.model), "variant": DEFAULT_VARIANT_KEY}, indent=2))
        return 0
    if live_generation and not args.skip_preflight:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc

    selected_ids = {item.strip() for item in args.source_id if item.strip()}
    entries = [
        entry
        for entry in manifest.get("entries", [])
        if not selected_ids or str(entry.get("source_id") or "").strip() in selected_ids
    ]
    if not entries:
        raise SystemExit("no manifest entries matched the requested source ids")

    source_ids = [str(entry.get("source_id") or "").strip() for entry in entries]
    sources = printout_engine.select_sources(
        source_catalog_path=_resolve(args.source_catalog),
        source_ids=source_ids,
    )
    sources_by_id = {str(source.get("source_id") or "").strip(): source for source in sources}

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "planned",
                    "variant": DEFAULT_VARIANT_KEY,
                    "source_count": len(entries),
                    "manifest_path": str(manifest_path),
                    "candidate_output_root": str(candidate_output_root),
                    "sources": [
                        {
                            "source_id": source_id,
                            "output_dir": str(
                                printout_engine.output_dir_for_source(candidate_output_root, sources_by_id[source_id])
                            ),
                        }
                        for source_id in source_ids
                        if source_id in sources_by_id
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    for entry in entries:
        source_id = str(entry.get("source_id") or "").strip()
        candidate = entry.setdefault("candidate", {})
        source = sources_by_id.get(source_id)
        if source is None:
            candidate["status"] = "error"
            candidate["error"] = f"source not found in catalog: {source_id}"
            errors.append({"source_id": source_id, "error": candidate["error"]})
            if not args.continue_on_error:
                break
            continue
        system_rel, user_rel, user_prompt_builder = _build_prompt_capture_builder(
            run_dir=run_dir,
            source_id=source_id,
            variant_key=DEFAULT_VARIANT_KEY,
            variant_prompt_text=variant_prompt_text,
        )
        candidate["prompt_capture_paths"] = {"system": system_rel, "user": user_rel}
        try:
            result = printout_engine.build_printout_for_source(
                repo_root=REPO_ROOT,
                subject_root=_resolve(args.subject_root),
                source=source,
                source_card_dir=_resolve(args.source_card_dir),
                revised_lecture_substrate_dir=_resolve(args.revised_lecture_substrate_dir),
                course_synthesis_path=_resolve(args.course_synthesis_path),
                output_root=candidate_output_root,
                model=str(args.model),
                render_pdf=not args.no_pdf,
                force=args.force,
                rerender_existing=args.rerender_existing,
                prompt_version=str(args.prompt_version),
                system_instruction=_variant_system_instruction(),
                user_prompt_builder=user_prompt_builder,
                variant_metadata={
                    "mode": "evaluation_sandbox",
                    "variant_key": DEFAULT_VARIANT_KEY,
                    "variant_prompt_path": _relative_to(REPO_ROOT, variant_prompt_path),
                    "design_doc": DEFAULT_DESIGN_DOC,
                    "workspace": "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/",
                },
            )
            candidate["status"] = str(result.get("status") or "written")
            candidate["output_dir"] = _relative_to(run_dir, Path(result["output_dir"]))
            candidate["json_path"] = _relative_to(run_dir, Path(result["json_path"]))
            candidate["markdown_paths"] = [
                _relative_to(run_dir, Path(path))
                for path in result.get("markdown_paths", [])
            ]
            candidate["pdf_paths"] = [
                _relative_to(run_dir, Path(path))
                for path in result.get("pdf_paths", [])
            ]
            candidate["error"] = ""
            results.append({"source_id": source_id, "status": candidate["status"]})
        except Exception as exc:
            candidate["status"] = "error"
            candidate["error"] = recursive.format_error(exc)
            errors.append({"source_id": source_id, "error": candidate["error"]})
            if not args.continue_on_error:
                break

    _refresh_summary(manifest)
    _write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "variant": DEFAULT_VARIANT_KEY,
                "source_count": len(entries),
                "written_count": manifest["summary"]["written_count"],
                "rerendered_count": manifest["summary"]["rerendered_count"],
                "skipped_count": manifest["summary"]["skipped_count"],
                "error_count": manifest["summary"]["error_count"],
                "results": results,
                "errors": errors,
                "manifest_path": str(manifest_path),
                "candidate_output_root": str(candidate_output_root),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
