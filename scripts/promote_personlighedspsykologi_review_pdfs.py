#!/usr/bin/env python3
"""Promote already-rendered review PDFs into the canonical main output tree."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printouts as printouts
from notebooklm_queue import personlighedspsykologi_recursive as recursive

DEFAULT_REVIEW_ROOT = (
    "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/review"
)
SHEET_STEMS = tuple(stem for stem in printouts.V3_RENDER_STEMS if stem != "05-exam-bridge")
PDF_RE = re.compile(
    rf"^.+?--(?P<source_id>.+?)--(?P<stem>{'|'.join(re.escape(stem) for stem in printouts.V3_RENDER_STEMS)})\.pdf$"
)


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise printouts.PrintoutError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _catalog_sources(source_catalog_path: Path) -> dict[str, dict[str, Any]]:
    payload = recursive.load_json(source_catalog_path)
    return {
        str(source.get("source_id") or "").strip(): source
        for source in payload.get("sources", [])
        if isinstance(source, dict) and str(source.get("source_id") or "").strip()
    }


def _discover_review_pdfs(review_root: Path) -> dict[str, dict[str, Path]]:
    grouped: dict[str, dict[str, Path]] = {}
    for pdf_path in sorted(review_root.glob("*.pdf")):
        match = PDF_RE.match(pdf_path.name)
        if not match:
            continue
        source_id = match.group("source_id")
        stem = match.group("stem")
        current = grouped.setdefault(source_id, {})
        previous = current.get(stem)
        if previous is None or pdf_path.stat().st_mtime > previous.stat().st_mtime:
            current[stem] = pdf_path
    return grouped


def _discover_review_jsons(review_root: Path) -> dict[str, Path]:
    latest: dict[str, tuple[float, Path]] = {}
    for json_path in [
        *review_root.glob(".scaffolding/artifacts/*/*/reading-scaffolds.json"),
        *review_root.glob(".scaffolding/*/reading-scaffolds.json"),
    ]:
        try:
            artifact = _read_json(json_path)
        except Exception:
            continue
        source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
        metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
        source_id = str(source.get("source_id") or metadata.get("source_id") or json_path.parent.name).strip()
        current = latest.get(source_id)
        mtime = json_path.stat().st_mtime
        if current is None or mtime > current[0]:
            latest[source_id] = (mtime, json_path)
    return {source_id: path for source_id, (_, path) in sorted(latest.items())}


def _canonicalize_artifact(artifact: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(artifact)
    normalized["schema_version"] = printouts.SCHEMA_VERSION
    normalized["artifact_type"] = "reading_printouts"
    artifact_source = normalized.get("source") if isinstance(normalized.get("source"), dict) else {}
    artifact_source = {**artifact_source, **source}
    artifact_source["reading_title"] = printouts._reading_title_from_source(artifact_source)
    normalized["source"] = artifact_source
    existing_variant = normalized.get("variant") if isinstance(normalized.get("variant"), dict) else {}
    normalized["variant"] = {
        **existing_variant,
        "mode": "canonical_main",
        "variant_key": str(existing_variant.get("variant_key") or "problem_driven_v1"),
        "render_completion_markers": False,
        "render_exam_bridge": False,
    }
    return normalized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--output-root", default=str(printouts.DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--source-catalog", default=str(printouts.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-id", action="append", default=[], help="Promote one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Promote all discovered review PDFs.")
    parser.add_argument("--copy-json", action="store_true", help="Also copy matching review JSON to reading-printouts.json.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    review_root = _resolve(args.review_root)
    output_root = _resolve(args.output_root)
    sources = _catalog_sources(_resolve(args.source_catalog))
    review_pdfs = _discover_review_pdfs(review_root)
    review_jsons = _discover_review_jsons(review_root)
    requested_ids = [item.strip() for item in args.source_id if item.strip()]
    if not args.all and not requested_ids:
        raise SystemExit("select --all or at least one --source-id")
    selected_ids = sorted(review_pdfs) if args.all else requested_ids
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source_id in selected_ids:
        try:
            source = sources.get(source_id)
            if source is None:
                raise printouts.PrintoutError(f"source not found in catalog: {source_id}")
            stems = review_pdfs.get(source_id) or {}
            missing = [stem for stem in SHEET_STEMS if stem not in stems]
            if missing:
                raise printouts.PrintoutError(f"missing review PDFs for {source_id}: {', '.join(missing)}")
            out_dir = printouts.output_dir_for_source(
                output_root,
                source,
                output_layout=printouts.OUTPUT_LAYOUT_CANONICAL,
            )
            copied_paths: list[str] = []
            json_path = out_dir / printouts.CANONICAL_PRINTOUT_JSON_NAME
            if not args.dry_run:
                out_dir.mkdir(parents=True, exist_ok=True)
                for stem in SHEET_STEMS:
                    target = out_dir / f"{stem}.pdf"
                    shutil.copy2(stems[stem], target)
                    copied_paths.append(_relative(target))
                if args.copy_json:
                    review_json = review_jsons.get(source_id)
                    if review_json is None:
                        raise printouts.PrintoutError(f"review JSON not found for source: {source_id}")
                    _write_json(json_path, _canonicalize_artifact(_read_json(review_json), source))
            else:
                copied_paths = [_relative(out_dir / f"{stem}.pdf") for stem in SHEET_STEMS]
            results.append(
                {
                    "source_id": source_id,
                    "status": "planned" if args.dry_run else "copied",
                    "output_dir": _relative(out_dir),
                    "pdf_paths": copied_paths,
                    "json_path": _relative(json_path) if args.copy_json else "",
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
        "copied_count": sum(1 for item in results if item.get("status") == "copied"),
        "planned_count": sum(1 for item in results if item.get("status") == "planned"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
