#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CFG_TAG_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_audio_key(value: str) -> str:
    name = Path(str(value)).name.strip()
    stem = Path(name).stem if name.lower().endswith(".mp3") else name
    stem = CFG_TAG_RE.sub("", stem).strip()
    stem = re.sub(r"\s+", " ", stem)
    return stem.casefold()


def candidate_week_dirs(output_root: Path, lecture_key: str) -> list[Path]:
    roots = [output_root]
    if (output_root / "output").is_dir():
        roots.append(output_root / "output")
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        for path in (root / lecture_key).glob("*") if (root / lecture_key).is_dir() else []:
            if path.parent in seen:
                continue
            seen.add(path.parent)
            result.append(path.parent)
    return result


def find_candidate_audio(output_root: Path, lecture_key: str, baseline_source_name: str) -> Path | None:
    target_key = normalize_audio_key(baseline_source_name)
    matches: list[Path] = []
    for week_dir in candidate_week_dirs(output_root, lecture_key):
        for path in week_dir.glob("*.mp3"):
            if normalize_audio_key(path.name) == target_key:
                matches.append(path)
    if not matches:
        return None
    return sorted(matches, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)[0]


def ensure_candidate_paths(entry: dict) -> None:
    sample_id = entry["sample_id"]
    candidate = entry.setdefault("candidate", {})
    candidate.setdefault("transcript_path", f"transcripts/after/{sample_id}.txt")
    candidate.setdefault("transcript_json_path", f"transcripts/after/{sample_id}.json")
    candidate.setdefault("plain_transcript_path", f"transcripts/after/{sample_id}.plain.txt")
    candidate.setdefault("speaker_transcript_path", f"transcripts/after/{sample_id}.txt")
    candidate.setdefault("stt_prompt_path", f"stt_prompts/after/{sample_id}.txt")
    candidate.setdefault("prompt_capture_path", f"prompts/after/{sample_id}.txt")
    candidate.setdefault("transcription_status", "pending")


def sync_manifest(manifest_path: Path, candidate_output_root: Path) -> tuple[dict, list[str]]:
    manifest = read_json(manifest_path)
    run_dir = manifest_path.parent
    lines: list[str] = []
    completed = 0
    missing = 0
    for entry in manifest.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        ensure_candidate_paths(entry)
        lecture_key = str(entry.get("lecture_key") or "").strip()
        baseline = entry.get("baseline") or {}
        baseline_source_name = str(baseline.get("source_name") or "").strip()
        if not lecture_key or not baseline_source_name:
            missing += 1
            lines.append(f"missing metadata: {entry.get('sample_id', 'unknown')}")
            continue
        candidate_audio = find_candidate_audio(candidate_output_root, lecture_key, baseline_source_name)
        candidate = entry["candidate"]
        if not candidate_audio:
            missing += 1
            candidate["transcription_status"] = candidate.get("transcription_status") or "pending"
            lines.append(f"missing candidate audio: {entry['sample_id']}")
            continue
        candidate["source_name"] = candidate_audio.name
        candidate["local_audio_path"] = str(candidate_audio.resolve())
        candidate["title"] = baseline.get("title")
        candidate["audio_url"] = None
        candidate["published_at"] = None
        candidate["transcription_status"] = (
            "completed"
            if (run_dir / candidate["transcript_path"]).exists()
            else "pending"
        )
        completed += 1
        lines.append(f"matched candidate audio: {entry['sample_id']} -> {candidate_audio.name}")

    manifest["candidate_output_root"] = str(candidate_output_root.resolve())
    if completed and not missing:
        manifest["status"] = "candidate_audio_ready"
    elif completed:
        manifest["status"] = "candidate_audio_partial"
    lines.append(f"summary: matched {completed}, missing {missing}")
    return manifest, lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync generated candidate audio paths into an episode A/B review manifest."
    )
    parser.add_argument("--manifest", required=True, help="Review manifest JSON.")
    parser.add_argument(
        "--candidate-output-root",
        required=True,
        help="Output root used for candidate generation.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned updates without writing.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    candidate_output_root = Path(args.candidate_output_root).expanduser().resolve()
    manifest, lines = sync_manifest(manifest_path, candidate_output_root)
    for line in lines:
        print(line)
    if not args.dry_run:
        write_json(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
