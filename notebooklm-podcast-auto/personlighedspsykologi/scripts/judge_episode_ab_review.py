#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import NamedTuple
from pathlib import Path

GEMINI_JUDGE_MODEL = "gemini-3.1-pro-preview"
GEMINI_FILE_POLL_INTERVAL_SECONDS = 2
GEMINI_FILE_POLL_TIMEOUT_SECONDS = 90


class UploadedFile(NamedTuple):
    name: str
    uri: str
    mime_type: str


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_prompt_config() -> dict:
    path = repo_root() / "notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json"
    return read_json(path) if path.exists() else {}


def read_text(path: Path, *, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n[...truncated...]"
    return text


def resolve_run_path(manifest_path: Path, rel_path: str) -> Path:
    path = Path(rel_path).expanduser()
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def preferred_transcript_path(entry: dict, side: str) -> str:
    side_obj = entry.get(side, {})
    return (
        side_obj.get("speaker_transcript_path")
        or side_obj.get("transcript_path")
        or side_obj.get("plain_transcript_path")
        or ""
    )


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return stem or "source"


def normalized_slide_filename(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"\bgang\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def stage_upload_path(path: Path) -> tuple[Path, Path]:
    staged_dir = Path(tempfile.mkdtemp(prefix="gemini-judge-upload-"))
    staged_path = staged_dir / f"{safe_stem(path.stem)}{path.suffix.lower() or '.bin'}"
    shutil.copy2(path, staged_path)
    return staged_path, staged_dir


def infer_mime_type(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def wait_for_gemini_file_ready(client: object, uploaded: object, path: Path) -> UploadedFile:
    file_name = str(getattr(uploaded, "name", "") or "").strip()
    if not file_name:
        raise RuntimeError(f"Gemini upload returned no file name for {path.name}")

    def ready_file(file_obj: object) -> UploadedFile:
        file_uri = str(getattr(file_obj, "uri", "") or "").strip()
        mime_type = str(getattr(file_obj, "mime_type", "") or "").strip() or infer_mime_type(path)
        if not file_uri:
            raise RuntimeError(f"Gemini upload returned no URI for {path.name}")
        return UploadedFile(name=file_name, uri=file_uri, mime_type=mime_type)

    latest = uploaded
    deadline = time.time() + GEMINI_FILE_POLL_TIMEOUT_SECONDS
    while True:
        state = getattr(latest, "state", None)
        if state is None or str(state).endswith("ACTIVE"):
            return ready_file(latest)
        if str(state).endswith("FAILED"):
            detail = getattr(latest, "error", None)
            raise RuntimeError(f"Gemini could not process {path.name}: {detail or 'unknown error'}")
        if time.time() >= deadline:
            raise RuntimeError(f"Gemini timed out while preparing {path.name}")
        time.sleep(GEMINI_FILE_POLL_INTERVAL_SECONDS)
        latest = client.files.get(name=file_name)


def upload_source_file(client: object, path: Path) -> UploadedFile:
    staged_path, staged_dir = stage_upload_path(path)
    try:
        uploaded = client.files.upload(
            file=str(staged_path),
            config={"mime_type": infer_mime_type(path)},
        )
    finally:
        shutil.rmtree(staged_dir, ignore_errors=True)
    return wait_for_gemini_file_ready(client, uploaded, path)


def delete_uploaded_files(client: object, uploaded_files: list[UploadedFile]) -> None:
    for uploaded in uploaded_files:
        try:
            client.files.delete(name=uploaded.name)
        except Exception as exc:
            print(f"Warning: could not delete Gemini upload {uploaded.name}: {exc}")


def resolve_source_file(raw: str, entry: dict, config: dict) -> Path | None:
    if not raw:
        return None
    raw_path = Path(raw).expanduser()
    if raw_path.is_absolute() and raw_path.exists():
        return raw_path.resolve()
    if raw_path.exists():
        return raw_path.resolve()

    slides_root_raw = str(config.get("slides_source_root") or "").strip()
    slides_root = Path(slides_root_raw).expanduser() if slides_root_raw else None
    catalog_match = entry.get("source_context", {}).get("catalog_match") or {}
    candidates: list[Path] = []
    if slides_root:
        for key in ("local_relative_path", "relative_path"):
            value = str(catalog_match.get(key) or "").strip()
            if value:
                candidates.append(slides_root / value)
        candidates.append(slides_root / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    if slides_root:
        search_names = {
            name
            for name in (
                raw_path.name,
                Path(str(catalog_match.get("source_filename") or "")).name,
                Path(str(catalog_match.get("local_relative_path") or "")).name,
                Path(str(catalog_match.get("relative_path") or "")).name,
            )
            if name
        }
        for name in search_names:
            matches = sorted(slides_root.rglob(name))
            if len(matches) == 1:
                return matches[0].resolve()
        wanted = {normalized_slide_filename(name) for name in search_names}
        fuzzy_matches = [
            path
            for path in slides_root.rglob("*.pdf")
            if normalized_slide_filename(path.name) in wanted
        ]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0].resolve()
    return None


def source_files_for_entry(entry: dict, config: dict) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()
    for raw in entry.get("source_context", {}).get("source_files", []) or []:
        path = resolve_source_file(str(raw), entry, config)
        if path is None:
            raise FileNotFoundError(f"source file not found for {entry['sample_id']}: {raw}")
        if path not in seen:
            seen.add(path)
            resolved.append(path)
    if not resolved:
        raise FileNotFoundError(f"no source files recorded for {entry['sample_id']}")
    return resolved


def format_source_context(entry: dict, source_paths: list[Path]) -> str:
    context = entry.get("source_context", {})
    lines = [
        "## Source Context",
        "",
        "Resolved source files:",
        *[f"- {path.name}" for path in source_paths],
    ]
    summary_lines = context.get("summary_lines") or []
    if summary_lines:
        lines.extend(["", "Trusted summary lines:", *[f"- {line}" for line in summary_lines]])
    key_points = context.get("key_points") or []
    if key_points:
        lines.extend(["", "Trusted key points:", *[f"- {point}" for point in key_points]])
    catalog_match = context.get("catalog_match") or {}
    if catalog_match:
        lines.extend(
            [
                "",
                "Slide catalog context:",
                f"- title: {catalog_match.get('title')}",
                f"- subcategory: {catalog_match.get('subcategory')}",
                f"- matched_by: {catalog_match.get('matched_by')}",
            ]
        )
    return "\n".join(str(line) for line in lines)


def episode_type_focus(prompt_type: str) -> str:
    if prompt_type == "single_reading":
        return (
            "Focus especially on the text's argument structure, conceptual distinctions, "
            "misunderstanding prevention, and exam-useful analytical moves."
        )
    if prompt_type == "single_slide":
        return (
            "Focus especially on whether the candidate reconstructs lecture sequence and "
            "logic from fragmentary slides without inventing unsupported claims."
        )
    if prompt_type == "weekly_readings_only":
        return (
            "Focus especially on synthesis across readings, tensions between sources, and "
            "whether each source keeps its role instead of being flattened into one summary."
        )
    if prompt_type == "short":
        return (
            "Focus especially on compression quality: the candidate may be shorter, but it "
            "must preserve the most important distinctions and avoid vague generalities."
        )
    return "Use the general rubric."


def build_judge_prompt(
    *,
    judge_prompt_template: str,
    entry: dict,
    source_paths: list[Path],
    transcript_a: str,
    transcript_b: str,
) -> str:
    prompt_type = str(entry.get("prompt_type") or "")
    baseline = entry.get("baseline", {})
    candidate = entry.get("candidate", {})
    sections = [
        judge_prompt_template.strip(),
        "",
        "# Concrete Review Task",
        "",
        f"Sample id: {entry['sample_id']}",
        f"Episode type: {prompt_type}",
        f"Lecture key: {entry.get('lecture_key')}",
        f"Baseline source name: {baseline.get('source_name')}",
        f"Candidate source name: {candidate.get('source_name')}",
        "",
        episode_type_focus(prompt_type),
        "",
        "Use the attached source PDFs/slides as the primary authority. The trusted source "
        "context below is only a navigation aid; do not rely on it instead of the files.",
        "",
        format_source_context(entry, source_paths),
        "",
        "## Transcript A - Baseline",
        transcript_a,
        "",
        "## Transcript B - Candidate",
        transcript_b,
        "",
        "Return exactly one Markdown report using the output format from the judge prompt. "
        "Be strict, concrete, and comparative. If transcript wording appears to be an STT "
        "error, say so instead of treating it as a conceptual error.",
    ]
    return "\n".join(sections)


def gemini_api_key() -> str:
    key = str(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set.")
    return key


def gemini_client() -> tuple[object, object]:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise SystemExit("google-genai package not installed.") from exc
    return genai.Client(api_key=gemini_api_key()), genai_types


def extract_gemini_text(response: object) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", "")
            if value:
                parts.append(str(value))
    return "\n".join(parts).strip()


def is_transient_gemini_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "500",
            "502",
            "503",
            "504",
            "internal",
            "unavailable",
            "deadline",
            "timeout",
            "temporarily",
            "resource_exhausted",
            "rate limit",
            "429",
        )
    )


def parse_verdict(markdown: str) -> dict:
    winner = None
    confidence = None
    for line in markdown.splitlines():
        winner_match = re.search(r"overall winner:\s*(A|B|Tie)\b", line, re.IGNORECASE)
        if winner_match:
            winner = winner_match.group(1)
            if winner.lower() == "tie":
                winner = "Tie"
        confidence_match = re.search(r"confidence:\s*(low|medium|high)\b", line, re.IGNORECASE)
        if confidence_match:
            confidence = confidence_match.group(1).lower()
    return {"overall_winner": winner, "confidence": confidence}


def judge_entry(
    *,
    client: object | None,
    genai_types: object | None,
    model: str,
    manifest_path: Path,
    judge_prompt_template: str,
    entry: dict,
    config: dict,
    max_transcript_chars: int | None,
    max_output_tokens: int,
    request_retries: int,
    request_backoff_seconds: float,
    dry_run: bool,
) -> tuple[str, dict]:
    run_dir = manifest_path.parent
    source_paths = source_files_for_entry(entry, config)
    transcript_a_path = resolve_run_path(manifest_path, preferred_transcript_path(entry, "baseline"))
    transcript_b_path = resolve_run_path(manifest_path, preferred_transcript_path(entry, "candidate"))
    if not transcript_a_path.exists():
        raise FileNotFoundError(f"missing baseline transcript: {transcript_a_path}")
    if not transcript_b_path.exists():
        raise FileNotFoundError(f"missing candidate transcript: {transcript_b_path}")

    prompt = build_judge_prompt(
        judge_prompt_template=judge_prompt_template,
        entry=entry,
        source_paths=source_paths,
        transcript_a=read_text(transcript_a_path, max_chars=max_transcript_chars),
        transcript_b=read_text(transcript_b_path, max_chars=max_transcript_chars),
    )
    prompt_path = run_dir / "judge_prompts" / f"{entry['sample_id']}.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")

    if dry_run:
        report = (
            f"# {entry['sample_id']}\n\n"
            "Dry run only. Judge prompt and source paths resolved successfully.\n"
        )
    else:
        assert client is not None
        assert genai_types is not None
        uploaded_files: list[UploadedFile] = []
        try:
            contents: list[object] = [
                genai_types.Part.from_text(text=f"Source file attached: {path.name}")
                for path in source_paths
            ]
            for path in source_paths:
                uploaded = upload_source_file(client, path)
                uploaded_files.append(uploaded)
                contents.append(
                    genai_types.Part.from_uri(
                        file_uri=uploaded.uri,
                        mime_type=uploaded.mime_type,
                    )
                )
            contents.append(genai_types.Part.from_text(text=prompt))
            response = None
            for attempt in range(request_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=(
                                "You are a strict academic QA reviewer for university psychology "
                                "podcast episodes. Judge source fidelity and pedagogical usefulness, "
                                "not entertainment value."
                            ),
                            max_output_tokens=max_output_tokens,
                        ),
                    )
                    break
                except Exception as exc:
                    if attempt >= request_retries or not is_transient_gemini_error(exc):
                        raise
                    wait_seconds = request_backoff_seconds * (2**attempt)
                    print(
                        f"{entry['sample_id']}: transient Gemini error; "
                        f"retrying in {wait_seconds:g}s ({attempt + 1}/{request_retries})"
                    )
                    time.sleep(wait_seconds)
            if response is None:
                raise RuntimeError(f"Gemini judge request did not return for {entry['sample_id']}")
            report = extract_gemini_text(response)
            if not report:
                raise RuntimeError(f"empty Gemini judge response for {entry['sample_id']}")
        finally:
            delete_uploaded_files(client, uploaded_files)

    report_rel = entry.get("review", {}).get("judge_report_path") or f"judgments/{entry['sample_id']}.md"
    report_path = run_dir / report_rel
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.rstrip() + "\n", encoding="utf-8")

    parsed = parse_verdict(report)
    review = entry.setdefault("review", {})
    review.update(
        {
            "status": "judged_dry_run" if dry_run else "judged",
            "judge_report_path": report_rel,
            "judge_prompt_path": str(prompt_path.relative_to(run_dir)),
            "judge_model": model,
            "judged_at": utc_now(),
            **{key: value for key, value in parsed.items() if value is not None},
        }
    )
    return report_rel, parsed


def write_summary(manifest_path: Path, manifest: dict) -> None:
    run_dir = manifest_path.parent
    judgments_dir = run_dir / "judgments"
    judgments_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    counts: dict[str, int] = {}
    for entry in manifest.get("entries", []):
        review = entry.get("review", {})
        winner = review.get("overall_winner") or "Unknown"
        counts[winner] = counts.get(winner, 0) + 1
        entries.append(
            {
                "sample_id": entry.get("sample_id"),
                "prompt_type": entry.get("prompt_type"),
                "lecture_key": entry.get("lecture_key"),
                "overall_winner": winner,
                "confidence": review.get("confidence"),
                "judge_report_path": review.get("judge_report_path"),
            }
        )
    summary = {
        "generated_at": utc_now(),
        "manifest": str(manifest_path),
        "counts": counts,
        "entries": entries,
    }
    write_json(judgments_dir / "summary.json", summary)

    lines = ["# Episode A/B Judgment Summary", "", "## Counts", ""]
    for winner in ("A", "B", "Tie", "Unknown"):
        if winner in counts:
            lines.append(f"- {winner}: {counts[winner]}")
    lines.extend(["", "## Samples", ""])
    for item in entries:
        lines.append(
            "- {sample_id}: {winner} ({confidence}) - `{prompt_type}`".format(
                sample_id=item["sample_id"],
                winner=item["overall_winner"],
                confidence=item.get("confidence") or "unknown confidence",
                prompt_type=item.get("prompt_type"),
            )
        )
    (judgments_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge before/after episode transcripts with Gemini.")
    parser.add_argument("--manifest", required=True, help="Path to episode A/B review manifest.json.")
    parser.add_argument(
        "--judge-prompt",
        default="notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/judge_prompt.md",
        help="Markdown rubric used as the base judge prompt.",
    )
    parser.add_argument("--sample-id", action="append", default=[], help="Limit to sample id. Repeatable.")
    parser.add_argument("--model", default=GEMINI_JUDGE_MODEL, help="Gemini model to use.")
    parser.add_argument("--force", action="store_true", help="Re-judge entries with existing reports.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve inputs and write prompts without API calls.")
    parser.add_argument(
        "--max-transcript-chars",
        type=int,
        default=None,
        help="Optional safety truncation per transcript. Default: no truncation.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=8192, help="Gemini output token limit.")
    parser.add_argument(
        "--request-retries",
        type=int,
        default=2,
        help="Retries for transient Gemini judge failures.",
    )
    parser.add_argument(
        "--request-backoff-seconds",
        type=float,
        default=10.0,
        help="Base exponential backoff for transient Gemini judge failures.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path)
    judge_prompt_path = (repo_root() / args.judge_prompt).resolve()
    judge_prompt_template = read_text(judge_prompt_path)
    config = load_prompt_config()
    sample_filter = set(args.sample_id)
    client = None
    genai_types = None
    if not args.dry_run:
        client, genai_types = gemini_client()

    completed = 0
    skipped = 0
    failed = 0
    for entry in manifest.get("entries", []):
        sample_id = entry.get("sample_id")
        if sample_filter and sample_id not in sample_filter:
            continue
        report_rel = entry.get("review", {}).get("judge_report_path") or f"judgments/{sample_id}.md"
        report_path = manifest_path.parent / report_rel
        if report_path.exists() and not args.force:
            print(f"{sample_id}: skipped existing judgment")
            skipped += 1
            continue
        try:
            report_rel, parsed = judge_entry(
                client=client,
                genai_types=genai_types,
                model=args.model,
                manifest_path=manifest_path,
                judge_prompt_template=judge_prompt_template,
                entry=entry,
                config=config,
                max_transcript_chars=args.max_transcript_chars,
                max_output_tokens=args.max_output_tokens,
                request_retries=args.request_retries,
                request_backoff_seconds=args.request_backoff_seconds,
                dry_run=args.dry_run,
            )
            print(
                f"{sample_id}: judged -> {report_rel} "
                f"winner={parsed.get('overall_winner') or 'unknown'}"
            )
            completed += 1
        except Exception as exc:
            failed += 1
            entry.setdefault("review", {}).update(
                {
                    "status": "judge_failed",
                    "judge_model": args.model,
                    "judge_error": str(exc),
                    "judged_at": utc_now(),
                }
            )
            print(f"FAILED {sample_id}: {exc}")
            if not sample_filter:
                continue
            raise

    manifest["status"] = "judged" if failed == 0 else "judge_partial"
    manifest["judged_at"] = utc_now()
    manifest["judge_model"] = args.model
    write_json(manifest_path, manifest)
    write_summary(manifest_path, manifest)
    print(f"Done. completed={completed} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
