#!/usr/bin/env python3
"""Import generated NotebookLM concept quizzes into Freudd."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_MANIFEST_PATH = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/manifest.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/output"
QUIZ_FILES_ROOT = REPO_ROOT / "freudd_portal/quiz_files/personlighedspsykologi"
CONCEPT_MANIFEST_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/concept_quizzes/concept_quiz_manifest.json"
QUIZ_LINKS_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/quiz_links.json"
CFG_TAG_RE = re.compile(r"\{[^{}]*\btype=quiz\b[^{}]*\bdifficulty=(?P<difficulty>[a-z0-9._:+-]+)\b[^{}]*\}", re.IGNORECASE)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _quiz_payload_is_valid(payload: Any) -> bool:
    if isinstance(payload, list):
        return True
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("questions"), list) or isinstance(payload.get("quiz"), list)


def _question_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    questions = payload.get("questions")
    if isinstance(questions, list):
        return len(questions)
    quiz = payload.get("quiz")
    if isinstance(quiz, list):
        return len(quiz)
    return 0


def _difficulty_from_name(path: Path) -> str:
    match = CFG_TAG_RE.search(path.stem)
    if not match:
        return "medium"
    difficulty = match.group("difficulty").strip().lower()
    return difficulty or "medium"


def _stable_quiz_id(*, slug: str, difficulty: str) -> str:
    seed = f"personlighedspsykologi|concept-quiz|{slug}|{difficulty}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def _find_quiz_file(output_root: Path, lecture_key: str) -> Path | None:
    lecture_dir = output_root / lecture_key
    candidates: list[Path] = []
    if lecture_dir.exists():
        candidates.extend(path for path in lecture_dir.glob("*.json") if path.is_file())
    candidates.extend(path for path in output_root.glob(f"{lecture_key}*/**/*.json") if path.is_file())
    valid: list[Path] = []
    for path in sorted(set(candidates), key=lambda item: item.name.casefold()):
        name = path.name.lower()
        if ".request" in name or "manifest" in name or "type=quiz" not in name:
            continue
        try:
            payload = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if _quiz_payload_is_valid(payload):
            valid.append(path)
    if len(valid) > 1:
        valid.sort(key=lambda item: (item.stat().st_mtime_ns, item.name.casefold()), reverse=True)
    return valid[0] if valid else None


def _load_lab_packs(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    packs = payload.get("packs") if isinstance(payload, dict) else None
    if not isinstance(packs, list):
        raise SystemExit(f"Invalid concept quiz lab manifest: {path}")
    return [pack for pack in packs if isinstance(pack, dict)]


def _merge_quiz_links(entries: list[dict[str, Any]], quiz_links_path: Path) -> dict[str, Any]:
    if quiz_links_path.exists():
        payload = _load_json(quiz_links_path)
        if not isinstance(payload, dict):
            payload = {}
    else:
        payload = {}
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        by_name = {}
    else:
        by_name = dict(by_name)

    for entry in entries:
        title = str(entry["title"])
        by_name[title] = {
            "relative_path": f"{entry['quiz_id']}.html",
            "format": "html",
            "difficulty": entry["difficulty"],
            "subject_slug": "personlighedspsykologi",
            "links": [
                {
                    "relative_path": f"{entry['quiz_id']}.html",
                    "format": "html",
                    "difficulty": entry["difficulty"],
                    "subject_slug": "personlighedspsykologi",
                }
            ],
        }

    payload["by_name"] = {key: by_name[key] for key in sorted(by_name)}
    return payload


def import_quizzes(*, output_root: Path, dry_run: bool = False) -> dict[str, Any]:
    packs = _load_lab_packs(LAB_MANIFEST_PATH)
    entries: list[dict[str, Any]] = []
    missing: list[str] = []

    for pack in packs:
        lecture_key = str(pack.get("lecture_key") or "").strip().upper()
        slug = str(pack.get("slug") or "").strip()
        title = str(pack.get("title") or slug).strip()
        if not lecture_key or not slug:
            continue
        source = _find_quiz_file(output_root, lecture_key)
        if source is None:
            missing.append(lecture_key)
            continue
        payload = _load_json(source)
        difficulty = _difficulty_from_name(source)
        if difficulty != "medium":
            continue
        quiz_id = _stable_quiz_id(slug=slug, difficulty=difficulty)
        destination = QUIZ_FILES_ROOT / f"{quiz_id}.json"
        entry = {
            "quiz_id": quiz_id,
            "quiz_url": f"/q/{quiz_id}.html",
            "difficulty": difficulty,
            "difficulty_label": "Normal",
            "title": title,
            "slug": slug,
            "lecture_key": lecture_key,
            "source_output_path": source.relative_to(REPO_ROOT).as_posix(),
            "repo_quiz_path": destination.relative_to(REPO_ROOT).as_posix(),
            "question_count": _question_count(payload),
        }
        entries.append(entry)
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    if missing:
        raise SystemExit(f"Missing generated quiz JSON for concept pack(s): {', '.join(missing)}")
    if not entries:
        raise SystemExit(f"No generated medium concept quiz JSON files found under {output_root}")

    manifest = {
        "version": 1,
        "subject_slug": "personlighedspsykologi",
        "title": "Begrebsquizzer",
        "difficulty_label": "Normal",
        "entries": sorted(entries, key=lambda item: str(item["lecture_key"])),
    }
    quiz_links = _merge_quiz_links(manifest["entries"], QUIZ_LINKS_PATH)
    if not dry_run:
        _write_json(CONCEPT_MANIFEST_PATH, manifest)
        _write_json(QUIZ_LINKS_PATH, quiz_links)
    return {
        "imported": len(entries),
        "manifest_path": CONCEPT_MANIFEST_PATH.relative_to(REPO_ROOT).as_posix(),
        "quiz_files_root": QUIZ_FILES_ROOT.relative_to(REPO_ROOT).as_posix(),
        "quiz_ids": [entry["quiz_id"] for entry in manifest["entries"]],
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = (REPO_ROOT / output_root).resolve()
    result = import_quizzes(output_root=output_root, dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
