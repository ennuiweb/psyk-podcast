#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
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


def ensure_elevenlabs_api_key() -> str:
    key = str(os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set.")
    return key


def ensure_backend_client(backend: str) -> object:
    if backend == "openai":
        return ensure_openai_client()
    if backend == "elevenlabs":
        return ensure_elevenlabs_api_key()
    raise SystemExit(f"Unsupported STT backend: {backend}")


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


def build_elevenlabs_keyterms(entry: dict, limit: int) -> list[str]:
    fixed_terms = [
        "personality psychology",
        "subjectivity",
        "subject formation",
        "subjectivation",
        "power relations",
        "domination",
        "freedom practices",
        "social constructionism",
        "poststructuralism",
        "narrative identity",
        "historicity",
        "theory method",
    ]
    source_context = entry.get("source_context", {})
    candidates: list[str] = list(fixed_terms)
    for value in source_context.get("source_files") or []:
        stem = Path(str(value)).stem
        stem = re.sub(r"^W\d+L\d+\s+", "", stem, flags=re.IGNORECASE)
        candidates.extend(part.strip(" -_") for part in re.split(r"[.;:]", stem))
    for field in ("key_points", "summary_lines"):
        for value in source_context.get(field) or []:
            text = str(value)
            candidates.extend(part.strip(" -_") for part in re.split(r"[.;:]", text))

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = re.sub(r"\s+", " ", str(candidate).strip())
        if not value:
            continue
        words = value.split()
        if len(words) > 5 or len(value) >= 50:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
        if len(normalized) >= limit:
            break
    return normalized


def append_transcript_token(current: str, token: str) -> str:
    if not current:
        return token
    if re.match(r"^[.,!?;:%)]", token):
        return current + token
    if current.endswith("("):
        return current + token
    return current + " " + token


def speaker_labeled_text_from_words(words: list[dict]) -> str:
    turns: list[tuple[str, str]] = []
    current_speaker = ""
    current_text = ""
    for word in words:
        token = str(word.get("text") or "").strip()
        if not token:
            continue
        speaker = str(word.get("speaker_id") or "speaker_unknown").strip() or "speaker_unknown"
        if current_speaker and speaker != current_speaker and current_text:
            turns.append((current_speaker, current_text.strip()))
            current_text = ""
        current_speaker = speaker
        current_text = append_transcript_token(current_text, token)
    if current_speaker and current_text:
        turns.append((current_speaker, current_text.strip()))
    return "\n\n".join(f"{speaker}: {text}" for speaker, text in turns).strip()


def transcribe_elevenlabs_scribe(
    *,
    api_key: str,
    audio_path: Path,
    model: str,
    entry: dict,
    num_speakers: int,
    keyterms_limit: int,
    language_code: str | None,
    tag_audio_events: bool,
    timeout_seconds: int,
    request_retries: int,
    request_backoff_seconds: float,
) -> tuple[str, str, dict, list[str]]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests package not installed — pip install requests") from exc

    keyterms = build_elevenlabs_keyterms(entry, limit=keyterms_limit)
    data: list[tuple[str, str]] = [
        ("model_id", model),
        ("diarize", "true"),
        ("num_speakers", str(num_speakers)),
        ("timestamps_granularity", "word"),
        ("tag_audio_events", "true" if tag_audio_events else "false"),
        ("no_verbatim", "false"),
        ("file_format", "other"),
    ]
    if language_code:
        data.append(("language_code", language_code))
    for term in keyterms:
        data.append(("keyterms", term))

    last_exc: Exception | None = None
    for attempt in range(request_retries + 1):
        try:
            with audio_path.open("rb") as handle:
                response = requests.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={"xi-api-key": api_key},
                    data=data,
                    files={"file": (audio_path.name, handle, "audio/mpeg")},
                    timeout=timeout_seconds,
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ElevenLabs STT failed with HTTP {response.status_code}: {response.text[:1000]}"
                )
            payload = response.json()
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= request_retries:
                raise RuntimeError(
                    f"ElevenLabs STT request failed for {audio_path.name}: {exc}"
                ) from exc
            delay = request_backoff_seconds * (2**attempt)
            print(
                f"Retrying ElevenLabs STT for {audio_path.name} "
                f"(attempt {attempt + 2}/{request_retries + 1}) in {delay:.1f}s: {exc}"
            )
            time.sleep(delay)
    else:
        raise RuntimeError(
            f"ElevenLabs STT request failed for {audio_path.name}: {last_exc or 'unknown error'}"
        )

    plain_text = str(payload.get("text") or "").strip()
    words = payload.get("words") or []
    speaker_text = speaker_labeled_text_from_words(words) if isinstance(words, list) else ""
    if not speaker_text:
        speaker_text = plain_text
    if not plain_text and not speaker_text:
        raise RuntimeError(f"Empty ElevenLabs transcription response for {audio_path.name}")
    return speaker_text.strip(), plain_text.strip(), payload, keyterms


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
    plain_transcript = transcript_txt.with_suffix(".plain.txt")
    stt_prompt = run_dir / "stt_prompts" / side_label / f"{entry['sample_id']}.txt"
    normalized_audio = run_dir / ".cache" / side_label / f"{entry['sample_id']}{NORMALIZED_AUDIO_SUFFIX}"
    segment_dir = run_dir / ".cache" / side_label / f"{entry['sample_id']}_segments"
    return {
        "run_dir": run_dir,
        "transcript_txt": transcript_txt,
        "transcript_json": transcript_json,
        "plain_transcript": plain_transcript,
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
    backend: str,
    model: str,
    bitrate_kbps: int,
    sample_rate_hz: int,
    max_upload_bytes: int,
    num_speakers: int,
    keyterms_limit: int,
    language_code: str | None,
    tag_audio_events: bool,
    request_timeout_seconds: int,
    request_retries: int,
    request_backoff_seconds: float,
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
    plain_transcript = paths["plain_transcript"]
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
        return "planned", f"{entry['sample_id']}: would transcribe {source_audio.name} with {backend}/{model}"

    stt_prompt.parent.mkdir(parents=True, exist_ok=True)
    transcript_txt.parent.mkdir(parents=True, exist_ok=True)
    stt_prompt.write_text(prompt + "\n", encoding="utf-8")

    if backend == "elevenlabs":
        speaker_text, plain_text, payload, keyterms = transcribe_elevenlabs_scribe(
            api_key=str(client),
            audio_path=source_audio,
            model=model,
            entry=entry,
            num_speakers=num_speakers,
            keyterms_limit=keyterms_limit,
            language_code=language_code,
            tag_audio_events=tag_audio_events,
            timeout_seconds=request_timeout_seconds,
            request_retries=request_retries,
            request_backoff_seconds=request_backoff_seconds,
        )
        transcript_txt.write_text(speaker_text.rstrip() + "\n", encoding="utf-8")
        plain_transcript.write_text((plain_text or speaker_text).rstrip() + "\n", encoding="utf-8")
        transcript_payload = {
            "schema_version": 1,
            "sample_id": entry["sample_id"],
            "side": side,
            "created_at": utc_now(),
            "backend": "elevenlabs",
            "model": model,
            "source_audio_path": str(source_audio),
            "source_audio_sha256": sha256_for_path(source_audio),
            "stt_prompt_path": relpath_or_absolute(stt_prompt, run_dir),
            "speaker_transcript_path": relpath_or_absolute(transcript_txt, run_dir),
            "plain_transcript_path": relpath_or_absolute(plain_transcript, run_dir),
            "num_speakers": num_speakers,
            "diarize": True,
            "language_code": language_code,
            "tag_audio_events": tag_audio_events,
            "keyterms": keyterms,
            "text": speaker_text,
            "plain_text": plain_text,
            "response": payload,
        }
        write_json(transcript_json, transcript_payload)
        side_obj["transcription_status"] = "completed"
        side_obj["transcription_backend"] = "elevenlabs"
        side_obj["transcription_model"] = model
        side_obj["transcribed_at"] = transcript_payload["created_at"]
        side_obj["transcript_json_path"] = relpath_or_absolute(transcript_json, run_dir)
        side_obj["stt_prompt_path"] = relpath_or_absolute(stt_prompt, run_dir)
        side_obj["speaker_transcript_path"] = relpath_or_absolute(transcript_txt, run_dir)
        side_obj["plain_transcript_path"] = relpath_or_absolute(plain_transcript, run_dir)
        side_obj["source_audio_sha256"] = transcript_payload["source_audio_sha256"]
        side_obj["num_speakers"] = num_speakers
        return "completed", f"{entry['sample_id']}: transcribed with ElevenLabs Scribe ({num_speakers} speakers)"

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
    parser = argparse.ArgumentParser(description="Transcribe before/after episode review audio.")
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
        "--backend",
        choices=("elevenlabs", "openai"),
        default="elevenlabs",
        help="STT backend. ElevenLabs is the default because it supports speaker diarization.",
    )
    parser.add_argument(
        "--model",
        help="Transcription model. Defaults to scribe_v2 for ElevenLabs and gpt-4o-transcribe for OpenAI.",
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
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=2,
        help="Expected speaker count for ElevenLabs diarization.",
    )
    parser.add_argument(
        "--keyterms-limit",
        type=int,
        default=100,
        help="Maximum keyterms sent to ElevenLabs Scribe v2.",
    )
    parser.add_argument(
        "--language-code",
        default="eng",
        help="Optional ElevenLabs language code. Use '' to let ElevenLabs auto-detect.",
    )
    parser.add_argument(
        "--tag-audio-events",
        action="store_true",
        help="Include non-speech event tags in ElevenLabs transcripts.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=1800,
        help="HTTP request timeout for ElevenLabs transcription.",
    )
    parser.add_argument(
        "--request-retries",
        type=int,
        default=3,
        help="Retries for ElevenLabs request failures such as connection resets.",
    )
    parser.add_argument(
        "--request-backoff-seconds",
        type=float,
        default=5.0,
        help="Base backoff in seconds for ElevenLabs retries.",
    )
    parser.add_argument("--force", action="store_true", help="Re-transcribe even when outputs already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Plan the transcription run without API calls or writes.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path)
    model = args.model or ("scribe_v2" if args.backend == "elevenlabs" else "gpt-4o-transcribe")
    if args.backend == "openai":
        ensure_ffmpeg()
    client = None if args.dry_run else ensure_backend_client(args.backend)
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
                backend=args.backend,
                model=model,
                bitrate_kbps=args.bitrate_kbps,
                sample_rate_hz=args.sample_rate_hz,
                max_upload_bytes=max_upload_bytes,
                num_speakers=args.num_speakers,
                keyterms_limit=args.keyterms_limit,
                language_code=args.language_code.strip() or None,
                tag_audio_events=args.tag_audio_events,
                request_timeout_seconds=args.request_timeout_seconds,
                request_retries=args.request_retries,
                request_backoff_seconds=args.request_backoff_seconds,
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
