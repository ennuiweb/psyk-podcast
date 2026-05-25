#!/usr/bin/env python3
"""Evaluate Personlighedspsykologi printouts against the exam theory matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printout_matrix_qa as matrix_qa
from notebooklm_queue import personlighedspsykologi_printouts as printouts


def _resolve(path_value: str | Path, *, base: Path | None = None) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return (base or REPO_ROOT) / path


def _load_json(path: Path) -> dict[str, Any]:
    return matrix_qa.load_json(path)


def _normalize_lecture_keys(value: str | None) -> list[str]:
    if not value:
        return []
    keys: list[str] = []
    for part in str(value).split(","):
        raw = part.strip().upper()
        if raw:
            keys.append(raw)
    return keys


def _canonical_json_path(output_root: Path, source_id: str) -> Path:
    return output_root / matrix_qa.CANONICAL_PRINTOUT_JSON_DIRNAME / source_id / matrix_qa.CANONICAL_PRINTOUT_JSON_NAME


def _discover_canonical_jsons(output_root: Path) -> list[Path]:
    return sorted(
        output_root.glob(
            f"{matrix_qa.CANONICAL_PRINTOUT_JSON_DIRNAME}/*/{matrix_qa.CANONICAL_PRINTOUT_JSON_NAME}"
        )
    )


def _source_ids_for_lectures(*, source_catalog_path: Path, lecture_keys: set[str]) -> list[str]:
    payload = _load_json(source_catalog_path)
    ids: list[str] = []
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "").strip()
        lecture_values = {str(source.get("lecture_key") or "").strip().upper()}
        lecture_values.update(str(item or "").strip().upper() for item in source.get("lecture_keys", []) or [])
        if source_id and lecture_values & lecture_keys:
            ids.append(source_id)
    return sorted(set(ids))


def _review_manifest_jsons(manifest_path: Path) -> list[Path]:
    manifest = _load_json(manifest_path)
    manifest_dir = manifest_path.parent
    paths: list[Path] = []
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        candidate = entry.get("candidate") if isinstance(entry.get("candidate"), dict) else {}
        if str(candidate.get("status") or "") not in {"written", "rerendered_existing", "skipped_existing"}:
            continue
        raw_path = str(candidate.get("json_path") or "").strip()
        if not raw_path:
            continue
        path = _resolve(raw_path, base=manifest_dir)
        if path.exists():
            paths.append(path)
    return sorted(set(paths))


def _selected_artifact_paths(args: argparse.Namespace) -> list[Path]:
    output_root = _resolve(args.output_root)
    selected: list[Path] = []
    for raw_path in args.artifact_json:
        selected.append(_resolve(raw_path))
    for raw_manifest in args.review_manifest:
        selected.extend(_review_manifest_jsons(_resolve(raw_manifest)))
    if args.all_canonical:
        selected.extend(_discover_canonical_jsons(output_root))
    source_ids = {str(item).strip() for item in args.source_id if str(item).strip()}
    lecture_keys = set(_normalize_lecture_keys(args.lectures))
    if lecture_keys:
        source_ids.update(
            _source_ids_for_lectures(
                source_catalog_path=_resolve(args.source_catalog),
                lecture_keys=lecture_keys,
            )
        )
    for source_id in sorted(source_ids):
        selected.append(_canonical_json_path(output_root, source_id))
    return sorted(set(selected))


def _report_root(args: argparse.Namespace) -> Path:
    report_root = _resolve(args.report_root)
    if args.run_name and args.report_root == str(matrix_qa.DEFAULT_REPORT_ROOT):
        return report_root.parent / str(args.run_name)
    return report_root


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--matrix", default=str(matrix_qa.DEFAULT_MATRIX_PATH))
    parser.add_argument("--source-catalog", default=str(printouts.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--output-root", default=str(matrix_qa.DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--report-root", default=str(matrix_qa.DEFAULT_REPORT_ROOT))
    parser.add_argument("--run-name", help="Optional report subdirectory name under the default report root parent.")
    parser.add_argument("--source-id", action="append", default=[], help="Evaluate one canonical source id; repeatable.")
    parser.add_argument("--lectures", help="Comma-separated lecture keys; evaluates canonical printouts for matching sources.")
    parser.add_argument("--all-canonical", action="store_true", help="Evaluate all canonical printout-json artifacts.")
    parser.add_argument("--artifact-json", action="append", default=[], help="Evaluate a specific printout JSON path; repeatable.")
    parser.add_argument("--review-manifest", action="append", default=[], help="Evaluate candidate JSONs recorded in a review manifest.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not write report files.")
    parser.add_argument("--fail-below", type=int, help="Exit non-zero if any report has overall_score below this value.")
    parser.add_argument("--allow-missing", action="store_true", help="Warn and continue when selected artifact paths are missing.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _resolve(args.repo_root).resolve()
    matrix_path = _resolve(args.matrix)
    if not matrix_path.exists():
        raise SystemExit(f"matrix not found: {matrix_path}")
    matrix = _load_json(matrix_path)
    artifact_paths = _selected_artifact_paths(args)
    if not artifact_paths:
        raise SystemExit("select --source-id, --lectures, --all-canonical, --artifact-json, or --review-manifest")

    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for artifact_path in artifact_paths:
        if not artifact_path.exists():
            message = f"artifact not found: {artifact_path}"
            if args.allow_missing:
                errors.append({"path": str(artifact_path), "error": message})
                continue
            raise SystemExit(message)
        try:
            reports.append(
                matrix_qa.evaluate_printout_artifact(
                    artifact=_load_json(artifact_path),
                    artifact_path=artifact_path,
                    matrix=matrix,
                    matrix_path=matrix_path,
                    repo_root=repo_root,
                )
            )
        except matrix_qa.MatrixQAError as exc:
            errors.append({"path": str(artifact_path), "error": str(exc)})

    report_root = _report_root(args)
    summary = matrix_qa.build_summary_report(reports, report_root=report_root, repo_root=repo_root)
    payload = {
        **summary,
        "error_count": len(errors),
        "errors": errors,
        "report_root": str(report_root),
    }
    if not args.dry_run:
        matrix_qa.write_report_bundle(report_root, reports, repo_root=repo_root)
        summary_path = report_root / "summary.json"
        if summary_path.exists():
            written_summary = _load_json(summary_path)
            written_summary["error_count"] = len(errors)
            written_summary["errors"] = errors
            matrix_qa.write_json(summary_path, written_summary)
            (report_root / "summary.md").write_text(
                matrix_qa.render_summary_markdown(written_summary),
                encoding="utf-8",
            )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    threshold_failed = False
    if args.fail_below is not None:
        threshold_failed = any(int(report.get("overall_score") or 0) < int(args.fail_below) for report in reports)
    return 1 if errors or threshold_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
