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
ENGLISH_MARKER_RE = re.compile(
    r"\b("
    r"what|which|why|how|according|context|personality|psychology|concept|term|"
    r"does|do|is|are|the|and|of|in|to|from|between|following"
    r")\b",
    re.IGNORECASE,
)
DANISH_MARKER_RE = re.compile(
    r"\b("
    r"hvad|hvilken|hvilket|hvilke|hvorfor|hvordan|hvor|er|som|og|ikke|"
    r"begreb|begrebet|forstås|forstår|personlighed|psykologi|mellem|ifølge|"
    r"teori|teorien|tradition|traditionen|svarmulighed|forklaring"
    r")\b|[æøå]",
    re.IGNORECASE,
)
ENGLISH_QUESTION_START_RE = re.compile(
    r"^\s*(what|which|why|how|in the context|according to|two people|a student|when)\b",
    re.IGNORECASE,
)
PROVENANCE_RE = re.compile(
    r"\bmatrix(?:en)?\b|"
    r"\bifølge\s+(?:matrixen|kilden|kilderne|noterne|materialet|dokumentet)\b|"
    r"\b(?:dette|det)\s+dokument\b|"
    r"\bkildepakke(?:n)?\b|"
    r"\bnoterne\b|"
    r"\bprovenance\b|"
    r"\baccording\s+to\s+(?:the\s+)?(?:source|sources|matrix|material)\b|"
    r"\bsource\s+material\b|"
    r"\bprovided\s+material\b",
    re.IGNORECASE,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _quiz_payload_is_valid(payload: Any) -> bool:
    return _question_count(payload) > 0


def _iter_text(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_iter_text(item))
        return texts
    if isinstance(value, dict):
        texts = []
        for item in value.values():
            texts.extend(_iter_text(item))
        return texts
    return []


def _question_texts(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list):
            return [str(item.get("question") or "").strip() for item in questions if isinstance(item, dict)]
        quiz = payload.get("quiz")
        if isinstance(quiz, list):
            return [str(item.get("question") or "").strip() for item in quiz if isinstance(item, dict)]
    if isinstance(payload, list):
        return [str(item.get("question") or "").strip() for item in payload if isinstance(item, dict)]
    return []


def _quiz_payload_validation_errors(payload: Any) -> list[str]:
    errors: list[str] = []
    if _question_count(payload) <= 0:
        errors.append("empty quiz payload")

    texts = _iter_text(payload)
    combined = "\n".join(texts)
    provenance_match = PROVENANCE_RE.search(combined)
    if provenance_match:
        errors.append(f"provenance/source wording leaked: {provenance_match.group(0)!r}")

    english_markers = len(ENGLISH_MARKER_RE.findall(combined))
    danish_markers = len(DANISH_MARKER_RE.findall(combined))
    question_starts = [text for text in _question_texts(payload) if text]
    english_question_starts = sum(1 for text in question_starts if ENGLISH_QUESTION_START_RE.search(text))
    if english_markers >= 6 and danish_markers < max(6, english_markers // 2):
        errors.append(
            "quiz text appears to be English "
            f"(english_markers={english_markers}, danish_markers={danish_markers})"
        )
    elif question_starts and english_question_starts >= max(2, len(question_starts) // 2):
        errors.append(
            "quiz questions appear to be English "
            f"(english_question_starts={english_question_starts}/{len(question_starts)})"
        )

    return errors


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


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _find_quiz_file(output_root: Path, lecture_key: str) -> Path | None:
    lecture_dir = output_root / lecture_key
    candidates: list[Path] = []
    if lecture_dir.exists():
        candidates.extend(path for path in lecture_dir.glob("*.json") if path.is_file())
    candidates.extend(path for path in output_root.glob(f"{lecture_key}*/**/*.json") if path.is_file())
    valid: list[Path] = []
    for path in sorted(set(candidates), key=lambda item: item.name.casefold()):
        name = path.name.lower()
        if ".request" in name or "manifest" in name:
            continue
        try:
            payload = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if _quiz_payload_is_valid(payload) and _difficulty_from_name(path) == "medium":
            valid.append(path)
    if len(valid) > 1:
        valid.sort(
            key=lambda item: ("type=quiz" in item.name.lower(), item.stat().st_mtime_ns, item.name.casefold()),
            reverse=True,
        )
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
        validation_errors = _quiz_payload_validation_errors(payload)
        if validation_errors:
            raise SystemExit(
                "Rejected generated concept quiz JSON "
                f"{_display_path(source)}: {'; '.join(validation_errors)}"
            )
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
            "source_output_path": _display_path(source),
            "repo_quiz_path": _display_path(destination),
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
        "manifest_path": _display_path(CONCEPT_MANIFEST_PATH),
        "quiz_files_root": _display_path(QUIZ_FILES_ROOT),
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
