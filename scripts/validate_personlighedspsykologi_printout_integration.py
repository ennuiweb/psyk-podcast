#!/usr/bin/env python3
"""Validate that personlighedspsykologi printouts use the canonical v3 integration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printouts as printouts  # noqa: E402


REQUIRED_PDF_STEMS = {
    "00-cover",
    "01-reading-guide",
    "02-active-reading",
    "03-abridged-version",
    "04-consolidation-sheet",
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
    output_root = json_path.parents[2]
    artifact = _load_json(json_path)
    rel_json = _rel(json_path, repo_root)
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    printout_payload = artifact.get("printouts") if isinstance(artifact.get("printouts"), dict) else {}
    expected_pdf_paths = {
        stem: output_root / printouts.canonical_pdf_filename(artifact, stem)
        for stem in REQUIRED_PDF_STEMS
    }
    pdf_names = {path.name for path in expected_pdf_paths.values() if path.exists()}

    if artifact.get("schema_version") != printouts.SCHEMA_VERSION:
        errors.append(f"{rel_json}: schema_version is not {printouts.SCHEMA_VERSION}")
    if artifact.get("artifact_type") != "reading_printouts":
        errors.append(f"{rel_json}: artifact_type is not reading_printouts")
    if variant.get("mode") != "canonical_main":
        errors.append(f"{rel_json}: variant.mode is not canonical_main")
    if variant.get("render_completion_markers") is not False:
        errors.append(f"{rel_json}: render_completion_markers is not false")
    if generator.get("prompt_version") != printouts.PROBLEM_DRIVEN_PROMPT_VERSION:
        errors.append(f"{rel_json}: prompt_version is not {printouts.PROBLEM_DRIVEN_PROMPT_VERSION}")
    if variant.get("variant_key") != printouts.PROBLEM_DRIVEN_VARIANT_KEY:
        errors.append(f"{rel_json}: variant_key is not {printouts.PROBLEM_DRIVEN_VARIANT_KEY}")
    if variant.get("variant_prompt_path") != str(printouts.PROBLEM_DRIVEN_VARIANT_PROMPT_PATH):
        errors.append(f"{rel_json}: variant_prompt_path is not the canonical problem-driven prompt")

    missing_keys = (set(printouts.V3_FIXED_TITLES) - {"cover"}) - set(printout_payload)
    if missing_keys:
        errors.append(f"{rel_json}: missing printout keys {sorted(missing_keys)}")

    missing_pdfs = {
        path.name
        for path in expected_pdf_paths.values()
        if not path.exists()
    }
    if missing_pdfs:
        errors.append(f"{_rel(output_root, repo_root)}: missing PDFs {sorted(missing_pdfs)}")
    legacy_pdfs = LEGACY_PDF_NAMES & pdf_names
    if legacy_pdfs:
        errors.append(f"{_rel(output_root, repo_root)}: legacy PDFs still present {sorted(legacy_pdfs)}")
    return errors


def _validate_legacy_only_dirs(output_root: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    for legacy_dir in sorted(output_root.glob("*/scaffolding")):
        if legacy_dir.is_dir():
            errors.append(f"{_rel(legacy_dir, repo_root)}: legacy scaffolding directory still present")
    for nested_printout_dir in sorted(output_root.glob("*/printouts")):
        if nested_printout_dir.is_dir():
            errors.append(f"{_rel(nested_printout_dir, repo_root)}: nested printouts directory still present")
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
        canonical_segment = f"/{printouts.CANONICAL_PRINTOUT_JSON_DIRNAME}/"
        if not any(canonical_segment in artifact_path and artifact_path.endswith(printouts.CANONICAL_PRINTOUT_JSON_NAME) for artifact_path in artifact_paths):
            errors.append(f"{source_id}: registry does not include canonical printouts artifact: {artifact_paths}")
        stale_paths = sorted(
            artifact_path
            for artifact_path in artifact_paths
            if "/scaffolding/" in artifact_path or "/printouts/" in artifact_path
        )
        if stale_paths:
            errors.append(f"{source_id}: registry still includes legacy printout artifacts: {stale_paths}")
    return errors


def _validate_pdf_text(canonical_json_paths: list[Path], repo_root: Path) -> list[str]:
    if not shutil.which("pdftotext"):
        return ["pdftotext is not available; cannot scan PDFs for checkbox markers"]
    errors: list[str] = []
    for json_path in canonical_json_paths:
        artifact = _load_json(json_path)
        output_root = json_path.parents[2]
        stems = printouts._expected_pdf_stems_for_artifact(artifact)
        for pdf_path in printouts._artifact_pdf_paths_for_stems(output_root, artifact, stems):
            if not pdf_path.exists():
                continue
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


def _review_json_source_id(path: Path, artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    return str(source.get("source_id") or metadata.get("source_id") or path.parent.name).strip()


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
            artifact = _load_json(path)
        except Exception:
            continue
        source_id = _review_json_source_id(path, artifact)
        if not source_id:
            continue
        mtime = path.stat().st_mtime
        current = latest.get(source_id)
        if current is None or mtime > current[0]:
            latest[source_id] = (mtime, path)
    return {source_id: path for source_id, (_, path) in sorted(latest.items())}


def _canonicalized_for_parity(artifact: dict[str, Any], main_artifact: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(artifact))
    main_source = main_artifact.get("source") if isinstance(main_artifact.get("source"), dict) else {}
    source = normalized.get("source") if isinstance(normalized.get("source"), dict) else {}
    normalized["source"] = {**source, **main_source}
    length_budget = main_artifact.get("length_budget")
    if not isinstance(length_budget, dict):
        length_budget = normalized.get("length_budget") if isinstance(normalized.get("length_budget"), dict) else {}
    if not isinstance(length_budget, dict) or not length_budget:
        length_budget = printouts.build_printout_length_budget(source=normalized["source"])
    payload = normalized.get("printouts") or normalized.get("scaffolds") or {}
    printout_payload = printouts.validate_printout_payload(
        printouts.normalize_scaffold_payload(payload, legacy_compat=True, length_budget=length_budget),
        length_budget=length_budget,
        validate_exam_bridge=False,
    )
    normalized["schema_version"] = printouts.SCHEMA_VERSION
    normalized["artifact_type"] = "reading_printouts"
    normalized["length_budget"] = length_budget
    normalized["printouts"] = printout_payload
    normalized["scaffolds"] = printout_payload
    normalized["variant"] = printouts.problem_driven_variant_metadata(
        mode="canonical_main",
        render_completion_markers=False,
        render_exam_bridge=False,
    )
    return normalized


def _render_markdown_by_name(artifact: dict[str, Any], output_dir: Path) -> dict[str, str]:
    rendered = printouts.render_printout_files(artifact=artifact, output_dir=output_dir, render_pdf=False)
    return {Path(path).name: Path(path).read_text(encoding="utf-8") for path in rendered["markdown_paths"]}


def _pdf_texts_by_name(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    stems = printouts._expected_pdf_stems_for_artifact(artifact)
    for pdf_path in printouts._artifact_pdf_paths_for_stems(output_dir, artifact, stems):
        if not pdf_path.exists():
            continue
        completed = subprocess.run(["pdftotext", str(pdf_path), "-"], text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise printouts.PrintoutError(f"pdftotext failed for {pdf_path}: {completed.stderr.strip()}")
        texts[pdf_path.name] = completed.stdout
    return texts


def _pdf_page_counts_by_name(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    if not shutil.which("pdfinfo"):
        return {}
    counts: dict[str, str] = {}
    stems = printouts._expected_pdf_stems_for_artifact(artifact)
    for pdf_path in printouts._artifact_pdf_paths_for_stems(output_dir, artifact, stems):
        if not pdf_path.exists():
            continue
        completed = subprocess.run(["pdfinfo", str(pdf_path)], text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise printouts.PrintoutError(f"pdfinfo failed for {pdf_path}: {completed.stderr.strip()}")
        for line in completed.stdout.splitlines():
            if line.startswith("Pages:"):
                counts[pdf_path.name] = line.split(":", 1)[1].strip()
                break
    return counts


def _validate_review_parity(
    *,
    review_root: Path,
    output_root: Path,
    repo_root: Path,
    render_pdf: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    review_jsons = _discover_review_jsons(review_root)
    compared = 0
    pdf_compared = 0
    if render_pdf and not shutil.which("pdftotext"):
        return ["pdftotext is not available; cannot compare rendered review/main PDFs"], {}
    with tempfile.TemporaryDirectory(prefix="printout-parity-") as temp_dir_str:
        temp_root = Path(temp_dir_str)
        for source_id, review_json_path in review_jsons.items():
            main_json_path = output_root / printouts.CANONICAL_PRINTOUT_JSON_DIRNAME / source_id / printouts.CANONICAL_PRINTOUT_JSON_NAME
            if not main_json_path.exists():
                errors.append(f"{source_id}: review artifact has no canonical main JSON")
                continue
            review_artifact = _load_json(review_json_path)
            main_artifact = _load_json(main_json_path)
            review_canonical = _canonicalized_for_parity(review_artifact, main_artifact)
            main_canonical = _canonicalized_for_parity(main_artifact, main_artifact)
            if review_canonical["printouts"] != main_canonical["printouts"]:
                errors.append(f"{source_id}: normalized review JSON printouts differ from main JSON")
                continue
            review_dir = temp_root / source_id / "review"
            main_dir = temp_root / source_id / "main"
            review_markdown = _render_markdown_by_name(review_canonical, review_dir)
            main_markdown = _render_markdown_by_name(main_canonical, main_dir)
            if review_markdown != main_markdown:
                errors.append(f"{source_id}: renderer markdown differs between cached review JSON and main JSON")
                continue
            compared += 1
            if render_pdf:
                printouts.render_printout_files(artifact=review_canonical, output_dir=review_dir, render_pdf=True)
                if _pdf_texts_by_name(review_dir, review_canonical) != _pdf_texts_by_name(output_root, main_artifact):
                    errors.append(f"{source_id}: rendered cached-review PDF text differs from current main PDFs")
                    continue
                if _pdf_page_counts_by_name(review_dir, review_canonical) != _pdf_page_counts_by_name(output_root, main_artifact):
                    errors.append(f"{source_id}: rendered cached-review PDF page counts differ from current main PDFs")
                    continue
                pdf_compared += 1
    return errors, {
        "review_artifact_count": len(review_jsons),
        "review_markdown_parity_count": compared,
        "review_pdf_parity_count": pdf_compared,
    }


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
    parser.add_argument(
        "--review-root",
        type=Path,
        default=REPO_ROOT / "notebooklm-podcast-auto" / "personlighedspsykologi" / "evaluation" / "printout_review" / "review",
    )
    parser.add_argument("--review-parity", action="store_true", help="Compare cached review JSON with canonical main JSON.")
    parser.add_argument("--review-pdf-parity", action="store_true", help="Also render and compare PDF text/page counts.")
    parser.add_argument("--min-canonical-bundles", type=int, default=1)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    canonical_json_paths = sorted(
        output_root.glob(
            f"{printouts.CANONICAL_PRINTOUT_JSON_DIRNAME}/*/{printouts.CANONICAL_PRINTOUT_JSON_NAME}"
        )
    )
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
    parity_summary: dict[str, Any] = {}
    if args.review_parity or args.review_pdf_parity:
        parity_errors, parity_summary = _validate_review_parity(
            review_root=args.review_root.resolve(),
            output_root=output_root,
            repo_root=repo_root,
            render_pdf=bool(args.review_pdf_parity),
        )
        errors.extend(parity_errors)
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
        **parity_summary,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
