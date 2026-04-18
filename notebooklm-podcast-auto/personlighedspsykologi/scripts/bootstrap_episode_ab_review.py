#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIG_TAG_RE = re.compile(r"\s+\{[^{}]+\}(?=\.mp3$)", re.IGNORECASE)
SHORT_PREFIX_RE = re.compile(r"^\[(?:Short|Brief)\]\s+", re.IGNORECASE)
WEEK_KEY_RE = re.compile(r"\bW\d+L\d+\b", re.IGNORECASE)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_episode_lookup_name(name: str) -> str:
    value = Path(name).name.strip()
    value = CONFIG_TAG_RE.sub("", value)
    value = SHORT_PREFIX_RE.sub("", value)
    return value.strip().lower()


def classify_episode(source_name: str) -> str | None:
    value = source_name.strip()
    if not value or value.startswith("[TTS]"):
        return None
    if value.startswith("[Short]") or value.startswith("[Brief]"):
        return "short"
    if "Alle kilder (undtagen slides)" in value:
        return "weekly_readings_only"
    if "Slide lecture:" in value or "Slide exercise:" in value:
        return "single_slide"
    return "single_reading"


def extract_lecture_key(text: str) -> str | None:
    match = WEEK_KEY_RE.search(text)
    return match.group(0).upper() if match else None


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return value.strip("_") or "sample"


def latest_first(episodes: list[dict]) -> list[dict]:
    return sorted(episodes, key=lambda item: item.get("published_at", ""), reverse=True)


def build_summary_index(summary_payload: dict) -> dict[str, dict]:
    by_name = summary_payload.get("by_name", {})
    return {
        normalize_episode_lookup_name(name): value
        for name, value in by_name.items()
    }


def build_slide_index(slides_payload: dict) -> dict[tuple[str, str, str], dict]:
    index: dict[tuple[str, str, str], dict] = {}
    for item in slides_payload.get("slides", []):
        lecture_key = str(item.get("lecture_key", "")).upper()
        subcategory = str(item.get("subcategory", "")).lower()
        title = str(item.get("title", "")).strip().lower()
        if lecture_key and subcategory and title:
            index[(lecture_key, subcategory, title)] = item
    return index


def infer_slide_context(source_name: str, slide_index: dict[tuple[str, str, str], dict]) -> dict:
    lecture_key = extract_lecture_key(source_name)
    kind_match = re.search(r"Slide\s+(lecture|exercise):\s*(.+?)\s+\[EN\]", source_name, re.IGNORECASE)
    if not lecture_key or not kind_match:
        return {"source_files": [], "catalog_match": None}
    subcategory = kind_match.group(1).lower()
    title = kind_match.group(2).strip().lower()
    match = slide_index.get((lecture_key, subcategory, title))
    if not match:
        return {"source_files": [], "catalog_match": None}
    return {
        "source_files": [match.get("relative_path") or match.get("local_relative_path") or ""],
        "catalog_match": match,
    }


def infer_source_context(
    episode: dict,
    reading_index: dict[str, dict],
    weekly_index: dict[str, dict],
    slide_index: dict[tuple[str, str, str], dict],
) -> dict:
    source_name = str(episode.get("source_name", ""))
    prompt_type = classify_episode(source_name)
    normalized = normalize_episode_lookup_name(source_name)

    if prompt_type == "weekly_readings_only":
        record = weekly_index.get(normalized, {})
        meta = record.get("meta", {})
        return {
            "source_files": meta.get("source_files_covered") or meta.get("source_files_expected") or [],
            "summary_lines": record.get("summary_lines", []),
            "key_points": record.get("key_points", []),
            "summary_meta": meta,
        }

    if prompt_type in {"single_reading", "short"}:
        record = reading_index.get(normalized, {})
        meta = record.get("meta", {})
        source_file = meta.get("source_file")
        return {
            "source_files": [source_file] if source_file else [],
            "summary_lines": record.get("summary_lines", []),
            "key_points": record.get("key_points", []),
            "summary_meta": meta,
        }

    if prompt_type == "single_slide":
        return infer_slide_context(source_name, slide_index)

    return {"source_files": []}


def choose_samples(episodes: list[dict], counts: dict[str, int]) -> list[dict]:
    chosen: list[dict] = []
    for prompt_type in ("weekly_readings_only", "single_reading", "single_slide", "short"):
        want = counts[prompt_type]
        candidates = [ep for ep in episodes if classify_episode(str(ep.get("source_name", ""))) == prompt_type]
        ordered = latest_first(candidates)
        picked: list[dict] = []
        seen_lectures: set[str] = set()
        for episode in ordered:
            lecture_key = extract_lecture_key(str(episode.get("source_name", ""))) or ""
            if lecture_key in seen_lectures:
                continue
            picked.append(episode)
            if lecture_key:
                seen_lectures.add(lecture_key)
            if len(picked) >= want:
                break
        if len(picked) < want:
            picked_names = {id(ep) for ep in picked}
            for episode in ordered:
                if id(episode) in picked_names:
                    continue
                picked.append(episode)
                if len(picked) >= want:
                    break
        chosen.extend(picked[:want])
    return chosen


def sample_id_for_episode(episode: dict) -> str:
    source_name = str(episode.get("source_name", ""))
    prompt_type = classify_episode(source_name) or "unknown"
    lecture_key = (extract_lecture_key(source_name) or "unknown").lower()
    normalized = normalize_episode_lookup_name(source_name)
    trimmed = normalized.replace(".mp3", "")
    trimmed = re.sub(r"^w\d+l\d+\s*-\s*", "", trimmed)
    trimmed = re.sub(r"^slide\s+(lecture|exercise):\s*", "", trimmed)
    trimmed = re.sub(r"^alle kilder \(undtagen slides\)$", "alle_kilder_undtagen_slides", trimmed)
    return f"{prompt_type}__{lecture_key}__{slugify(trimmed)}"


def resolve_local_audio_path(episode: dict, episode_output_root: Path | None) -> str | None:
    if episode_output_root is None:
        return None
    source_name = str(episode.get("source_name", "")).strip()
    lecture_key = extract_lecture_key(source_name)
    if not source_name or not lecture_key:
        return None
    candidate = episode_output_root / "output" / lecture_key / source_name
    return str(candidate) if candidate.exists() else None


def build_entry(
    episode: dict,
    run_dir: Path,
    episode_output_root: Path | None,
    reading_index: dict[str, dict],
    weekly_index: dict[str, dict],
    slide_index: dict[tuple[str, str, str], dict],
) -> dict:
    source_name = str(episode.get("source_name", ""))
    prompt_type = classify_episode(source_name)
    if prompt_type is None:
        raise ValueError(f"Unsupported episode in review set: {source_name}")

    sample_id = sample_id_for_episode(episode)
    lecture_key = extract_lecture_key(source_name)
    context = infer_source_context(episode, reading_index, weekly_index, slide_index)

    notes_rel = f"notes/{sample_id}.md"
    judge_rel = f"judgments/{sample_id}.md"
    before_tx_rel = f"transcripts/before/{sample_id}.txt"
    after_tx_rel = f"transcripts/after/{sample_id}.txt"
    before_prompt_rel = f"prompts/before/{sample_id}.txt"
    after_prompt_rel = f"prompts/after/{sample_id}.txt"

    note_path = run_dir / notes_rel
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        "\n".join(
            [
                f"# {sample_id}",
                "",
                f"- Prompt type: `{prompt_type}`",
                f"- Lecture key: `{lecture_key or 'unknown'}`",
                f"- Baseline source: `{source_name}`",
                "- Candidate source: `pending`",
                "",
                "## Manual listening notes",
                "",
                "- Strengths:",
                "- Weaknesses:",
                "- Missed distinctions:",
                "- Generic or overly polished passages:",
                "- Exam usefulness:",
                "- Recommendation:",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "sample_id": sample_id,
        "prompt_type": prompt_type,
        "lecture_key": lecture_key,
        "baseline": {
            "episode_key": episode.get("episode_key"),
            "title": episode.get("title"),
            "source_name": source_name,
            "published_at": episode.get("published_at"),
            "audio_url": episode.get("audio_url"),
            "local_audio_path": resolve_local_audio_path(episode, episode_output_root),
            "transcript_path": before_tx_rel,
            "prompt_capture_path": before_prompt_rel,
        },
        "candidate": {
            "episode_key": None,
            "title": None,
            "source_name": None,
            "published_at": None,
            "audio_url": None,
            "local_audio_path": None,
            "transcript_path": after_tx_rel,
            "prompt_capture_path": after_prompt_rel,
        },
        "source_context": context,
        "review": {
            "status": "pending",
            "manual_notes_path": notes_rel,
            "judge_report_path": judge_rel,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap a before/after episode review run.")
    parser.add_argument(
        "--inventory",
        default="shows/personlighedspsykologi-en/episode_inventory.json",
        help="Episode inventory JSON for the published feed.",
    )
    parser.add_argument(
        "--reading-summaries",
        default="shows/personlighedspsykologi-en/reading_summaries.json",
        help="Reading summaries JSON used to map readings to source PDFs.",
    )
    parser.add_argument(
        "--weekly-summaries",
        default="shows/personlighedspsykologi-en/weekly_overview_summaries.json",
        help="Weekly overview summaries JSON used to map lecture overviews to source PDFs.",
    )
    parser.add_argument(
        "--slides-catalog",
        default="shows/personlighedspsykologi-en/slides_catalog.json",
        help="Slides catalog JSON used to map slide episodes to slide files.",
    )
    parser.add_argument(
        "--workspace-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review",
        help="Workspace root for review runs.",
    )
    parser.add_argument(
        "--episode-output-root",
        help="Optional local podcast output root. When set, baseline local audio paths are resolved from here.",
    )
    parser.add_argument("--run-name", required=True, help="Name of the review run directory.")
    parser.add_argument("--weekly-count", type=int, default=2, help="Weekly episodes to include.")
    parser.add_argument("--reading-count", type=int, default=2, help="Single-reading episodes to include.")
    parser.add_argument("--slide-count", type=int, default=2, help="Single-slide episodes to include.")
    parser.add_argument("--short-count", type=int, default=2, help="Short episodes to include.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    inventory = read_json((repo_root / args.inventory).resolve())
    reading_summaries = read_json((repo_root / args.reading_summaries).resolve())
    weekly_summaries = read_json((repo_root / args.weekly_summaries).resolve())
    slides_catalog = read_json((repo_root / args.slides_catalog).resolve())

    workspace_root = (repo_root / args.workspace_root).resolve()
    episode_output_root = (
        Path(args.episode_output_root).expanduser().resolve()
        if args.episode_output_root
        else None
    )
    run_dir = workspace_root / "runs" / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    for rel in (
        "transcripts/before",
        "transcripts/after",
        "prompts/before",
        "prompts/after",
        "judgments",
        "notes",
    ):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)

    counts = {
        "weekly_readings_only": args.weekly_count,
        "single_reading": args.reading_count,
        "single_slide": args.slide_count,
        "short": args.short_count,
    }
    episodes = inventory.get("episodes", [])
    chosen = choose_samples(episodes, counts)

    reading_index = build_summary_index(reading_summaries)
    weekly_index = build_summary_index(weekly_summaries)
    slide_index = build_slide_index(slides_catalog)
    entries = [
        build_entry(
            episode,
            run_dir=run_dir,
            episode_output_root=episode_output_root,
            reading_index=reading_index,
            weekly_index=weekly_index,
            slide_index=slide_index,
        )
        for episode in chosen
    ]

    manifest = {
        "schema_version": 1,
        "run_name": args.run_name,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "before_only",
        "episode_output_root": str(episode_output_root) if episode_output_root else None,
        "selection": {
            "strategy": "latest_per_prompt_type",
            "counts": counts,
        },
        "entries": entries,
    }
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)

    summary_lines = [
        f"# {args.run_name}",
        "",
        f"- Manifest: `{manifest_path}`",
        f"- Samples: `{len(entries)}`",
        "",
        "## Selected episodes",
        "",
    ]
    for entry in entries:
        summary_lines.append(
            f"- `{entry['sample_id']}` | `{entry['prompt_type']}` | {entry['baseline']['source_name']}"
        )
    (run_dir / "README.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
