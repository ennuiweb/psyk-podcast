#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


APP_DATA_ATTR_RE = re.compile(
    r"<app-root\b[^>]*\bdata-app-data=\"(?P<data>.*?)\"",
    re.IGNORECASE | re.DOTALL,
)
QUIZ_TAG_RE = re.compile(r"\{[^{}]*\btype=quiz\b[^{}]*\}", re.IGNORECASE)
CFG_BLOCK_RE = re.compile(r"\{([^{}]+)\}")
CFG_PAIR_RE = re.compile(r"([a-z0-9._:+-]+)=([^{}\s]+)", re.IGNORECASE)
QUIZ_DIFFICULTY_HASH_RE = re.compile(
    r"difficulty=(easy|medium|hard)\s+download=html\s+hash=([0-9a-f]{8})",
    re.IGNORECASE,
)
WEEK_TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
LANG_SUFFIX_RE = re.compile(r"\[(?P<language>[^\[\]]+)\]\s*$")
TRAILING_CFG_BLOCKS_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+$",
    re.IGNORECASE,
)
DEFAULT_QUIZ_TITLE = "Personality Quiz"
QUIZ_HASH_REWRITE_MAP = {
    ("easy", "8b02000e"): "0aa8e6f0",
    ("medium", "137cde55"): "05f7d73e",
    ("hard", "63dc9adf"): "f06c6752",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract quiz payload JSON from NotebookLM HTML exports "
            "into {title, questions} format."
        ),
    )
    parser.add_argument(
        "--root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing quiz HTML exports.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing sibling *.json quiz extracts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without creating files.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Optional manifest output path. "
            "Default: <root>/quiz_json_manifest.json (unless --no-manifest)."
        ),
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Skip writing a manifest index file.",
    )
    return parser.parse_args()


def parse_cfg_tags(stem: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for block in CFG_BLOCK_RE.findall(stem):
        for key, value in CFG_PAIR_RE.findall(block):
            tags[key.lower()] = value
    return tags


def strip_trailing_cfg_blocks(stem: str) -> str:
    return TRAILING_CFG_BLOCKS_RE.sub("", stem).strip()


def parse_week_token(value: str) -> str | None:
    match = WEEK_TOKEN_RE.search(value)
    if not match:
        return None
    week = int(match.group("week"))
    lecture = int(match.group("lecture"))
    return f"W{week:02d}L{lecture}"


def parse_title_language(title: str) -> str | None:
    match = LANG_SUFFIX_RE.search(title)
    if not match:
        return None
    language = match.group("language").strip()
    return language or None


def find_quiz_html_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*.html"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if not QUIZ_TAG_RE.search(path.stem):
            continue
        files.append(path)
    return sorted(files)


def normalize_quiz_json_output_path(path: Path) -> Path:
    name = path.name
    match = QUIZ_DIFFICULTY_HASH_RE.search(name)
    if match:
        difficulty = match.group(1).lower()
        old_hash = match.group(2).lower()
        new_hash = QUIZ_HASH_REWRITE_MAP.get((difficulty, old_hash), old_hash)
        replacement = f"difficulty={difficulty} download=json hash={new_hash}"
        rewritten = QUIZ_DIFFICULTY_HASH_RE.sub(replacement, name, count=1)
        if rewritten != name:
            return path.with_name(rewritten)
    if "download=html" in name:
        return path.with_name(name.replace("download=html", "download=json"))
    return path


def extract_payload_from_html(path: Path) -> Any:
    content = path.read_text(encoding="utf-8")
    match = APP_DATA_ATTR_RE.search(content)
    if not match:
        raise ValueError("Missing app-root[data-app-data] attribute.")
    raw_data = html.unescape(match.group("data")).strip()
    if not raw_data:
        raise ValueError("Empty data-app-data payload.")
    return json.loads(raw_data)


def extract_questions(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list):
            return questions
        quiz = payload.get("quiz")
        if isinstance(quiz, list):
            return quiz
    if isinstance(payload, list):
        return payload
    raise ValueError("Quiz payload does not contain a questions/quiz list.")


def build_notebooklm_json(payload: Any) -> dict[str, Any]:
    title = DEFAULT_QUIZ_TITLE
    if isinstance(payload, dict):
        payload_title = payload.get("title")
        if isinstance(payload_title, str) and payload_title.strip():
            title = payload_title.strip()
    questions = extract_questions(payload)
    return {
        "title": title,
        "questions": questions,
    }


def build_manifest_meta(path: Path, root: Path, output_json: dict[str, Any]) -> dict[str, Any]:
    relative_html = path.relative_to(root).as_posix()
    stem = path.stem
    tags = parse_cfg_tags(stem)
    title = strip_trailing_cfg_blocks(stem)
    title_language = parse_title_language(title)
    week_token = parse_week_token(stem) or parse_week_token(path.parent.name)

    meta: dict[str, Any] = {
        "source_html": relative_html,
        "source_filename": path.name,
        "source_stem": stem,
        "title": title,
        "week_token": week_token,
        "difficulty": tags.get("difficulty"),
        "language": tags.get("lang") or title_language,
        "format": tags.get("download"),
        "tags": tags,
    }

    questions = output_json.get("questions")
    if isinstance(questions, list):
        meta["question_count"] = len(questions)

    return meta


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_manifest_path(args: argparse.Namespace, root: Path) -> Path | None:
    if args.no_manifest:
        return None
    if args.manifest:
        return Path(args.manifest).expanduser()
    return root / "quiz_json_manifest.json"


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser()
    if not root.exists():
        raise SystemExit(f"Root path does not exist: {root}")
    root = root.resolve()

    manifest_path = resolve_manifest_path(args, root)
    html_files = find_quiz_html_files(root)
    if not html_files:
        print(f"No quiz HTML files found under {root}")
        return 0

    writes = 0
    planned_writes = 0
    skipped_existing = 0
    failures: list[tuple[Path, str]] = []
    manifest_rows: list[dict[str, Any]] = []

    for html_path in html_files:
        output_json = normalize_quiz_json_output_path(html_path.with_suffix(".json"))
        relative_html = html_path.relative_to(root).as_posix()
        relative_json = output_json.relative_to(root).as_posix()
        try:
            payload = extract_payload_from_html(html_path)
            output_payload = build_notebooklm_json(payload)
            meta = build_manifest_meta(html_path, root, output_payload)
        except Exception as exc:  # noqa: BLE001
            failures.append((html_path, str(exc)))
            manifest_rows.append(
                {
                    "source_html": relative_html,
                    "output_json": relative_json,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            continue

        status = "written"
        if output_json.exists() and not args.overwrite:
            status = "skipped-existing"
            skipped_existing += 1
        elif args.dry_run:
            status = "planned"
            planned_writes += 1
        else:
            write_json(output_json, output_payload)
            writes += 1

        manifest_rows.append(
            {
                "source_html": relative_html,
                "output_json": relative_json,
                "status": status,
                "week_token": meta.get("week_token"),
                "difficulty": meta.get("difficulty"),
                "question_count": meta.get("question_count"),
            }
        )

    manifest_payload = {
        "root": str(root),
        "total_quiz_html": len(html_files),
        "writes": writes,
        "planned_writes": planned_writes,
        "skipped_existing": skipped_existing,
        "failures": len(failures),
        "files": manifest_rows,
    }

    if manifest_path is not None:
        if args.dry_run:
            print(f"Manifest (dry-run): {manifest_path}")
        else:
            write_json(manifest_path, manifest_payload)

    print(f"Root: {root}")
    print(f"Quiz HTML files: {len(html_files)}")
    print(f"JSON written: {writes}")
    if args.dry_run:
        print(f"JSON planned: {planned_writes}")
    print(f"Skipped existing JSON: {skipped_existing}")
    print(f"Failures: {len(failures)}")
    if failures:
        for path, error in failures[:20]:
            print(f"FAILED: {path} :: {error}")
        if len(failures) > 20:
            print(f"... and {len(failures) - 20} more failure(s).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
