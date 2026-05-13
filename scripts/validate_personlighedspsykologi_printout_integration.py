#!/usr/bin/env python3
"""Validate that personlighedspsykologi printouts use the canonical v3 integration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printouts as printouts  # noqa: E402


REQUIRED_PDF_NAMES = {
    "00-cover.pdf",
    "01-reading-guide.pdf",
    "02-active-reading.pdf",
    "03-abridged-version.pdf",
    "04-consolidation-sheet.pdf",
}
LEGACY_PDF_NAMES = {
    "01-abridged-guide.pdf",
    "02-unit-test-suite.pdf",
    "03-cloze-scaffold.pdf",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _validate_bundle(json_path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    bundle_dir = json_path.parent
    artifact = _load_json(json_path)
    rel_json = _rel(json_path, repo_root)
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    printout_payload = artifact.get("printouts") if isinstance(artifact.get("printouts"), dict) else {}
    pdf_names = {path.name for path in bundle_dir.glob("*.pdf")}

    if artifact.get("schema_version") != printouts.SCHEMA_VERSION:
        errors.append(f"{rel_json}: schema_version is not {printouts.SCHEMA_VERSION}")
    if artifact.get("artifact_type") != "reading_printouts":
        errors.append(f"{rel_json}: artifact_type is not reading_printouts")
    if variant.get("mode") != "canonical_main":
        errors.append(f"{rel_json}: variant.mode is not canonical_main")
    if variant.get("render_completion_markers") is not False:
        errors.append(f"{rel_json}: render_completion_markers is not false")

    missing_keys = (set(printouts.V3_FIXED_TITLES) - {"cover"}) - set(printout_payload)
    if missing_keys:
        errors.append(f"{rel_json}: missing printout keys {sorted(missing_keys)}")

    missing_pdfs = REQUIRED_PDF_NAMES - pdf_names
    if missing_pdfs:
        errors.append(f"{_rel(bundle_dir, repo_root)}: missing PDFs {sorted(missing_pdfs)}")
    legacy_pdfs = LEGACY_PDF_NAMES & pdf_names
    if legacy_pdfs:
        errors.append(f"{_rel(bundle_dir, repo_root)}: legacy PDFs still present {sorted(legacy_pdfs)}")
    prefixed_pdfs = sorted(name for name in pdf_names if "--" in name)
    if prefixed_pdfs:
        errors.append(f"{_rel(bundle_dir, repo_root)}: review-style provider-prefixed PDFs present {prefixed_pdfs}")
    return errors


def _validate_legacy_only_dirs(output_root: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    for source_dir in sorted(output_root.glob("*/printouts/*")):
        if not source_dir.is_dir():
            continue
        if (source_dir / printouts.CANONICAL_PRINTOUT_JSON_NAME).exists():
            continue
        legacy_pdfs = sorted(path.name for path in source_dir.glob("*.pdf") if path.name in LEGACY_PDF_NAMES)
        if legacy_pdfs:
            errors.append(
                f"{_rel(source_dir, repo_root)}: legacy-only printout dir without "
                f"{printouts.CANONICAL_PRINTOUT_JSON_NAME}: {legacy_pdfs}"
            )
    return errors


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        try:
            parsed, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
        index = start + end
    return objects


def _validate_log(path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_log = _rel(path, repo_root)
    payloads = [item for item in _extract_json_objects(text) if isinstance(item.get("results"), list)]
    if not payloads:
        return [f"{rel_log}: no build result JSON object found"]
    payload = payloads[-1]
    if int(payload.get("error_count") or 0) != 0:
        errors.append(f"{rel_log}: error_count is {payload.get('error_count')}")
    if "EXIT_CODE=" in text and "EXIT_CODE=0" not in text:
        errors.append(f"{rel_log}: process exit code was not zero")
    for result in payload.get("results", []):
        if not isinstance(result, dict) or result.get("status") != "skipped_existing":
            continue
        json_path = str(result.get("json_path") or "")
        pdf_paths = [Path(str(item)).name for item in result.get("pdf_paths", []) if item]
        if f"/{printouts.LEGACY_PRINTOUT_JSON_NAME}" in json_path or "/scaffolding/" in json_path:
            errors.append(f"{rel_log}: skipped_existing used legacy JSON for {result.get('source_id')}: {json_path}")
        legacy_pdfs = sorted(name for name in pdf_paths if name in LEGACY_PDF_NAMES)
        if legacy_pdfs:
            errors.append(f"{rel_log}: skipped_existing used legacy PDFs for {result.get('source_id')}: {legacy_pdfs}")
    return errors


def _validate_registry(repo_root: Path, canonical_json_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    if not canonical_json_paths:
        return errors
    command = [
        sys.executable,
        "scripts/sync_personlighedspsykologi_learning_material_registry.py",
        "--dry-run",
    ]
    completed = subprocess.run(command, cwd=repo_root, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        return [f"registry dry-run failed: {completed.stderr.strip() or completed.stdout.strip()}"]
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [f"registry dry-run did not return JSON: {exc}"]
    entries = payload.get("materials") if isinstance(payload.get("materials"), list) else []
    entries_by_source_id: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("source_id"):
            entries_by_source_id.setdefault(str(entry["source_id"]), []).append(entry)
    for json_path in canonical_json_paths:
        artifact = _load_json(json_path)
        source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        source_entries = entries_by_source_id.get(source_id, [])
        if not source_entries:
            errors.append(f"{_rel(json_path, repo_root)}: source missing from registry dry-run")
            continue
        artifact_paths = [
            str((entry.get("artifact_paths") or {}).get("json") or "")
            for entry in source_entries
            if isinstance(entry, dict)
        ]
        if not any(
            "/printouts/" in artifact_path and artifact_path.endswith(printouts.CANONICAL_PRINTOUT_JSON_NAME)
            for artifact_path in artifact_paths
        ):
            errors.append(f"{source_id}: registry does not include canonical printouts artifact: {artifact_paths}")
        stale_paths = sorted(artifact_path for artifact_path in artifact_paths if "/scaffolding/" in artifact_path)
        if stale_paths:
            errors.append(f"{source_id}: registry still includes legacy printout artifacts: {stale_paths}")
    return errors


def _validate_pdf_text(canonical_json_paths: list[Path], repo_root: Path) -> list[str]:
    if not shutil.which("pdftotext"):
        return ["pdftotext is not available; cannot scan PDFs for checkbox markers"]
    errors: list[str] = []
    for json_path in canonical_json_paths:
        for pdf_path in sorted(json_path.parent.glob("*.pdf")):
            completed = subprocess.run(
                ["pdftotext", str(pdf_path), "-"],
                check=False,
                text=True,
                capture_output=True,
            )
            if completed.returncode != 0:
                errors.append(f"{_rel(pdf_path, repo_root)}: pdftotext failed")
                continue
            if "[ ]" in completed.stdout:
                errors.append(f"{_rel(pdf_path, repo_root)}: checkbox marker still present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output",
    )
    parser.add_argument("--log", type=Path, action="append", default=[])
    parser.add_argument("--registry-check", action="store_true")
    parser.add_argument("--pdf-text", action="store_true")
    parser.add_argument("--min-canonical-bundles", type=int, default=1)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    canonical_json_paths = sorted(output_root.glob(f"*/printouts/*/{printouts.CANONICAL_PRINTOUT_JSON_NAME}"))
    errors: list[str] = []
    warnings: list[str] = []

    if printouts.SCHEMA_VERSION != 3:
        errors.append(f"canonical printout SCHEMA_VERSION is {printouts.SCHEMA_VERSION}, expected 3")
    if len(canonical_json_paths) < args.min_canonical_bundles:
        errors.append(f"found {len(canonical_json_paths)} canonical bundles, expected at least {args.min_canonical_bundles}")

    for json_path in canonical_json_paths:
        errors.extend(_validate_bundle(json_path, repo_root))
    errors.extend(_validate_legacy_only_dirs(output_root, repo_root))

    if args.registry_check:
        errors.extend(_validate_registry(repo_root, canonical_json_paths))
    if args.pdf_text:
        errors.extend(_validate_pdf_text(canonical_json_paths, repo_root))
    for log_path in args.log:
        errors.extend(_validate_log(log_path.resolve(), repo_root))

    review_pdfs = sorted(
        (repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "evaluation" / "printout_review" / "review").glob("*.pdf")
    )
    if review_pdfs:
        warnings.append(f"review directory still contains {len(review_pdfs)} candidate PDF(s)")

    summary = {
        "status": "failed" if errors else "ok",
        "canonical_bundle_count": len(canonical_json_paths),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
