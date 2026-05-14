#!/usr/bin/env python3
"""Render accepted review printout artifacts into the canonical main output tree.

This command is intentionally renderer-only: it reads existing JSON artifacts and
never instantiates Gemini/OpenAI clients.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printouts as printouts
from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

DEFAULT_REVIEW_ROOT = (
    "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/review"
)


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise printouts.PrintoutError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _source_id_from_artifact(path: Path, artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_id = str(source.get("source_id") or "").strip()
    if source_id:
        return source_id
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    source_id = str(metadata.get("source_id") or "").strip()
    if source_id:
        return source_id
    return path.parent.name


def _discover_review_jsons(review_root: Path) -> dict[str, Path]:
    candidates = [
        *review_root.glob(".scaffolding/artifacts/*/*/reading-scaffolds.json"),
        *review_root.glob(".scaffolding/*/reading-scaffolds.json"),
        *review_root.glob("*/.scaffolding/artifacts/*/*/reading-scaffolds.json"),
        *review_root.glob("*/.scaffolding/*/reading-scaffolds.json"),
    ]
    latest: dict[str, tuple[float, Path]] = {}
    for path in candidates:
        try:
            artifact = _read_json(path)
        except Exception:
            continue
        source_id = _source_id_from_artifact(path, artifact)
        current = latest.get(source_id)
        mtime = path.stat().st_mtime
        if current is None or mtime > current[0]:
            latest[source_id] = (mtime, path)
    return {source_id: path for source_id, (_, path) in sorted(latest.items())}


def _catalog_sources(source_catalog_path: Path) -> dict[str, dict[str, Any]]:
    payload = recursive.load_json(source_catalog_path)
    return {
        str(source.get("source_id") or "").strip(): source
        for source in payload.get("sources", [])
        if isinstance(source, dict) and str(source.get("source_id") or "").strip()
    }


def _canonical_artifact(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    source: dict[str, Any],
    include_exam_bridge: bool,
) -> dict[str, Any]:
    normalized = dict(artifact)
    normalized["schema_version"] = printouts.SCHEMA_VERSION
    normalized["artifact_type"] = "reading_printouts"
    artifact_source = normalized.get("source") if isinstance(normalized.get("source"), dict) else {}
    artifact_source = {**artifact_source, **source}
    artifact_source["reading_title"] = printouts._reading_title_from_source(artifact_source)
    normalized["source"] = artifact_source
    length_budget = normalized.get("length_budget")
    if not isinstance(length_budget, dict):
        length_budget = printouts.build_printout_length_budget(source=artifact_source)
    payload = normalized.get("printouts") or normalized.get("scaffolds") or {}
    printout_payload = printouts.validate_printout_payload(
        printouts.normalize_scaffold_payload(payload, legacy_compat=True, length_budget=length_budget),
        length_budget=length_budget,
        validate_exam_bridge=include_exam_bridge,
    )
    normalized["length_budget"] = length_budget
    normalized["printouts"] = printout_payload
    normalized["scaffolds"] = printout_payload
    existing_variant = normalized.get("variant") if isinstance(normalized.get("variant"), dict) else {}
    normalized["variant"] = {
        **existing_variant,
        **printouts.problem_driven_variant_metadata(
            mode="canonical_main",
            render_completion_markers=False,
            render_exam_bridge=bool(include_exam_bridge),
        ),
        "backfilled_from_review_json": _relative(artifact_path),
        "backfilled_at": utc_now_iso(),
    }
    return normalized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--output-root", default=str(printouts.DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--source-catalog", default=str(printouts.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-id", action="append", default=[], help="Backfill one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Backfill all discovered review artifacts.")
    parser.add_argument("--include-exam-bridge", action="store_true")
    parser.add_argument("--no-pdf", action="store_true", help="Write Markdown only; skip PDF rendering.")
    parser.add_argument("--dry-run", action="store_true", help="Plan work without writing artifacts.")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    review_root = _resolve(args.review_root)
    output_root = _resolve(args.output_root)
    source_catalog_path = _resolve(args.source_catalog)
    discovered = _discover_review_jsons(review_root)
    requested_ids = [item.strip() for item in args.source_id if item.strip()]
    if not args.all and not requested_ids:
        raise SystemExit("select --all or at least one --source-id")
    selected_ids = sorted(discovered) if args.all else requested_ids
    sources = _catalog_sources(source_catalog_path)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source_id in selected_ids:
        artifact_path = discovered.get(source_id)
        source = sources.get(source_id)
        try:
            if artifact_path is None:
                raise printouts.PrintoutError(f"review JSON not found for source: {source_id}")
            if source is None:
                artifact = _read_json(artifact_path)
                artifact_source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
                source = {
                    **artifact_source,
                    "source_id": source_id,
                    "lecture_key": str(artifact_source.get("lecture_key") or "UNKNOWN"),
                }
            else:
                artifact = _read_json(artifact_path)
            out_dir = printouts.output_dir_for_source(
                output_root,
                source,
                output_layout=printouts.OUTPUT_LAYOUT_CANONICAL,
            )
            json_path = printouts.artifact_json_path_for_output_dir(
                output_root,
                source,
                out_dir,
                output_layout=printouts.OUTPUT_LAYOUT_CANONICAL,
            )
            if args.dry_run:
                results.append(
                    {
                        "source_id": source_id,
                        "status": "planned",
                        "review_json_path": _relative(artifact_path),
                        "output_dir": _relative(out_dir),
                        "json_path": _relative(json_path),
                    }
                )
                continue
            canonical_artifact = _canonical_artifact(
                artifact=artifact,
                artifact_path=artifact_path,
                source=source,
                include_exam_bridge=bool(args.include_exam_bridge),
            )
            rendered = printouts.render_printout_files(
                artifact=canonical_artifact,
                output_dir=out_dir,
                render_pdf=not args.no_pdf,
            )
            _write_json(json_path, canonical_artifact)
            results.append(
                {
                    "source_id": source_id,
                    "status": "written",
                    "review_json_path": _relative(artifact_path),
                    "output_dir": _relative(out_dir),
                    "json_path": _relative(json_path),
                    "markdown_paths": [_relative(Path(path)) for path in rendered.get("markdown_paths", [])],
                    "pdf_paths": [_relative(Path(path)) for path in rendered.get("pdf_paths", [])],
                }
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "error": recursive.format_error(exc)})
            if not args.continue_on_error:
                break
    payload = {
        "status": "error" if errors else "ok",
        "review_root": _relative(review_root),
        "output_root": _relative(output_root),
        "selected_count": len(selected_ids),
        "written_count": sum(1 for item in results if item.get("status") == "written"),
        "planned_count": sum(1 for item in results if item.get("status") == "planned"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
