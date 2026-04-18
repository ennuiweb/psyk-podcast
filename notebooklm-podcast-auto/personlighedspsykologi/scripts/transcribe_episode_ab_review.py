#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_UPLOAD_BYTES_DEFAULT = 24 * 1024 * 1024
NORMALIZED_AUDIO_SUFFIX = ".stt.mp3"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_openai_client():
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("openai package not installed — pip install openai") from exc
    return OpenAI()


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        text=True,
        capture_output=True,
    )


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        result = subprocess.run(["/usr/bin/env", "bash", "-lc", f"command -v {shlex.quote(binary)}"], capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"{binary} is required but not available on PATH.")


def ffprobe_duration_seconds(path: Path) -> float:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Unable to parse ffprobe duration for {path}") from exc


def normalize_audio(input_path: Path, output_path: Path, bitrate_kbps: int, sample_rate_hz: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate_hz),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(output_path),
        ]
    )


def segment_time_for_size(path: Path, max_upload_bytes: int) -> int:
    size_bytes = path.stat().st_size
    if size_bytes <= max_upload_bytes:
        return 0
    duration = ffprobe_duration_seconds(path)
    if duration <= 0:
        raise RuntimeError(f"Audio duration is not positive for {path}")
    raw_seconds = duration * (max_upload_bytes / size_bytes) * 0.9
    return max(300, int(math.floor(raw_seconds)))


def split_audio(input_path: Path, output_dir: Path, segment_seconds: int) -> list[Path]:
    if segment_seconds <= 0:
        return [input_path]
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "segment-%03d.mp3"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-c",
            "copy",
            str(pattern),
        ]
    )
    segments = sorted(output_dir.glob("segment-*.mp3"))
    if not segments:
        raise RuntimeError(f"No segments were created for {input_path}")
    return segments


def relpath_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def build_stt_prompt(entry: dict) -> str:
    source_context = entry.get("source_context", {})
    source_files = source_context.get("source_files") or []
    key_points = source_context.get("key_points") or []
    summary_lines = source_context.get("summary_lines") or []

    source_labels = []
    for value in source_files[:5]:
        label = Path(str(value)).stem.strip()
        if label:
            source_labels.append(label)

    lines = [
        "Transcribe this audio faithfully in the language spoken.",
        "This is an English university podcast episode for a personality psychology course.",
        "Preserve academic names, technical terms, punctuation, and capitalization when clear from the audio.",
        "Do not summarize, translate, or clean up the content beyond normal transcription punctuation.",
        f"Episode type: {entry.get('prompt_type', 'unknown')}.",
    ]
    lecture_key = entry.get("lecture_key")
    if lecture_key:
        lines.append(f"Lecture key: {lecture_key}.")
    if source_labels:
        lines.append("Relevant source labels: " + "; ".join(source_labels) + ".")
    if key_points:
        lines.append("Important concepts: " + "; ".join(str(point).strip() for point in key_points[:5] if str(point).strip()) + ".")
    elif summary_lines:
        lines.append("Topic cues: " + "; ".join(str(line).strip() for line in summary_lines[:4] if str(line).strip()) + ".")
    return "\n".join(lines)


def response_to_dict(response: object) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    payload = {"text": getattr(response, "text", "")}
    logprobs = getattr(response, "logprobs", None)
    if logprobs is not None:
        payload["logprobs"] = logprobs
    return payload


def transcribe_segment(
    *,
    client: object,
    audio_path: Path,
    model: str,
    prompt: str,
) -> tuple[str, dict]:
    with audio_path.open("rb") as handle:
        response = client.audio.transcriptions.create(
            model=model,
            file=handle,
            response_format="json",
            prompt=prompt,
            include=["logprobs"],
        )
    payload = response_to_dict(response)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError(f"Empty transcription response for {audio_path.name}")
    return text, payload


def resolve_paths(manifest_path: Path, entry: dict, side: str) -> dict[str, Path]:
    run_dir = manifest_path.parent
    side_obj = entry[side]
    side_label = "before" if side == "baseline" else "after"
    transcript_txt = run_dir / side_obj["transcript_path"]
    transcript_json = transcript_txt.with_suffix(".json")
    stt_prompt = run_dir / "stt_prompts" / side_label / f"{entry['sample_id']}.txt"
    normalized_audio = run_dir / ".cache" / side_label / f"{entry['sample_id']}{NORMALIZED_AUDIO_SUFFIX}"
    segment_dir = run_dir / ".cache" / side_label / f"{entry['sample_id']}_segments"
    return {
        "run_dir": run_dir,
        "transcript_txt": transcript_txt,
        "transcript_json": transcript_json,
        "stt_prompt": stt_prompt,
        "normalized_audio": normalized_audio,
        "segment_dir": segment_dir,
    }


def transcribe_entry(
    *,
    client: object,
    manifest_path: Path,
    entry: dict,
    side: str,
    model: str,
    bitrate_kbps: int,
    sample_rate_hz: int,
    max_upload_bytes: int,
    force: bool,
    dry_run: bool,
) -> tuple[str, str]:
    side_obj = entry[side]
    local_audio_path = str(side_obj.get("local_audio_path") or "").strip()
    if not local_audio_path:
        return "skipped", f"{entry['sample_id']}: no local audio path for {side}"

    source_audio = Path(local_audio_path).expanduser().resolve()
    if not source_audio.exists():
        return "skipped", f"{entry['sample_id']}: local audio file missing: {source_audio}"

    paths = resolve_paths(manifest_path, entry, side)
    transcript_txt = paths["transcript_txt"]
    transcript_json = paths["transcript_json"]
    stt_prompt = paths["stt_prompt"]
    normalized_audio = paths["normalized_audio"]
    segment_dir = paths["segment_dir"]
    run_dir = paths["run_dir"]

    if not force and transcript_txt.exists() and transcript_json.exists():
        side_obj["transcription_status"] = "completed"
        side_obj["transcript_json_path"] = relpath_or_absolute(transcript_json, run_dir)
        side_obj["stt_prompt_path"] = relpath_or_absolute(stt_prompt, run_dir)
        return "skipped", f"{entry['sample_id']}: transcript already exists"

    prompt = build_stt_prompt(entry)
    if dry_run:
        return "planned", f"{entry['sample_id']}: would transcribe {source_audio.name}"

    stt_prompt.parent.mkdir(parents=True, exist_ok=True)
    transcript_txt.parent.mkdir(parents=True, exist_ok=True)
    stt_prompt.write_text(prompt + "\n", encoding="utf-8")

    normalize_audio(source_audio, normalized_audio, bitrate_kbps=bitrate_kbps, sample_rate_hz=sample_rate_hz)
    segment_seconds = segment_time_for_size(normalized_audio, max_upload_bytes)
    if segment_seconds > 0:
        segments = split_audio(normalized_audio, segment_dir, segment_seconds=segment_seconds)
    else:
        segments = [normalized_audio]

    segment_results: list[dict] = []
    full_text_parts: list[str] = []
    carry_prompt = prompt
    for index, segment_path in enumerate(segments, start=1):
        text, payload = transcribe_segment(
            client=client,
            audio_path=segment_path,
            model=model,
            prompt=carry_prompt,
        )
        full_text_parts.append(text)
        carry_prompt = prompt + "\nPrevious transcript tail:\n" + text[-1200:]
        segment_results.append(
            {
                "index": index,
                "path": relpath_or_absolute(segment_path, run_dir),
                "size_bytes": segment_path.stat().st_size,
                "sha256": sha256_for_path(segment_path),
                "text": text,
                "response": payload,
            }
        )

    full_text = "\n\n".join(part.strip() for part in full_text_parts if part.strip()).strip() + "\n"
    transcript_txt.write_text(full_text, encoding="utf-8")

    transcript_payload = {
        "schema_version": 1,
        "sample_id": entry["sample_id"],
        "side": side,
        "created_at": utc_now(),
        "backend": "openai",
        "model": model,
        "source_audio_path": str(source_audio),
        "source_audio_sha256": sha256_for_path(source_audio),
        "normalized_audio_path": relpath_or_absolute(normalized_audio, run_dir),
        "normalized_audio_sha256": sha256_for_path(normalized_audio),
        "normalized_audio_size_bytes": normalized_audio.stat().st_size,
        "stt_prompt_path": relpath_or_absolute(stt_prompt, run_dir),
        "segment_count": len(segment_results),
        "segments": segment_results,
        "text": full_text.rstrip("\n"),
    }
    write_json(transcript_json, transcript_payload)

    side_obj["transcription_status"] = "completed"
    side_obj["transcription_backend"] = "openai"
    side_obj["transcription_model"] = model
    side_obj["transcribed_at"] = transcript_payload["created_at"]
    side_obj["transcript_json_path"] = relpath_or_absolute(transcript_json, run_dir)
    side_obj["stt_prompt_path"] = relpath_or_absolute(stt_prompt, run_dir)
    side_obj["normalized_audio_path"] = relpath_or_absolute(normalized_audio, run_dir)
    side_obj["segment_count"] = len(segment_results)
    return "completed", f"{entry['sample_id']}: transcribed {len(segment_results)} segment(s)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe before/after episode review audio with OpenAI STT.")
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the episode A/B review manifest.json.",
    )
    parser.add_argument(
        "--side",
        required=True,
        choices=("baseline", "candidate"),
        help="Which side of the review manifest to transcribe.",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        default=[],
        help="Optional sample id to limit transcription. Repeat as needed.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-transcribe",
        help="OpenAI transcription model.",
    )
    parser.add_argument(
        "--bitrate-kbps",
        type=int,
        default=32,
        help="Bitrate used when normalizing audio before upload.",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        default=16000,
        help="Sample rate used when normalizing audio before upload.",
    )
    parser.add_argument(
        "--max-upload-mib",
        type=int,
        default=24,
        help="Safety ceiling per upload chunk in MiB.",
    )
    parser.add_argument("--force", action="store_true", help="Re-transcribe even when outputs already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Plan the transcription run without API calls or writes.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path)
    ensure_ffmpeg()
    client = None if args.dry_run else ensure_openai_client()
    side = "baseline" if args.side == "baseline" else "candidate"
    sample_filter = set(args.sample_id)
    max_upload_bytes = args.max_upload_mib * 1024 * 1024

    processed = 0
    skipped = 0
    for entry in manifest.get("entries", []):
        if sample_filter and entry.get("sample_id") not in sample_filter:
            continue
        try:
            status, message = transcribe_entry(
                client=client,
                manifest_path=manifest_path,
                entry=entry,
                side=side,
                model=args.model,
                bitrate_kbps=args.bitrate_kbps,
                sample_rate_hz=args.sample_rate_hz,
                max_upload_bytes=max_upload_bytes,
                force=args.force,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            entry[side]["transcription_status"] = "failed"
            entry[side]["transcription_error"] = str(exc)
            print(f"FAILED {entry['sample_id']}: {exc}", file=sys.stderr)
            continue
        if status == "completed":
            processed += 1
        else:
            skipped += 1
        print(message)

    manifest["updated_at"] = utc_now()
    if not args.dry_run:
        write_json(manifest_path, manifest)
    print(f"Done. completed={processed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
