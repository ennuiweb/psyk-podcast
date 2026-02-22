#!/usr/bin/env python3
"""Sync quiz JSON exports to the droplet and update quiz_links.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


WEEK_TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
CFG_TAG_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
QUIZ_DIFFICULTY_RE = re.compile(
    r"\{[^{}]*\btype=quiz\b[^{}]*\bdifficulty=(?P<difficulty>[a-z0-9._:+-]+)\b[^{}]*\}",
    re.IGNORECASE,
)
QUIZ_TYPE_RE = re.compile(r"\{[^{}]*\btype=quiz\b[^{}]*\}", re.IGNORECASE)
DUPLICATE_WEEK_PREFIX_RE = re.compile(r"^(W\d{2}L\d+)\s*-\s*\1\b", re.IGNORECASE)
MISSING_TOKEN_RE = re.compile(r"\bMISSING\b", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
QUIZ_DIFFICULTY_SORT_ORDER = {"easy": 0, "medium": 1, "hard": 2}
QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER = {"medium": 0, "easy": 1, "hard": 2}


def normalize_week_tokens(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        week = match.group("week").zfill(2)
        lecture = match.group("lecture")
        return f"W{week}L{lecture}"

    return WEEK_TOKEN_RE.sub(repl, text)


def strip_cfg_tag_suffix(text: str) -> str:
    return CFG_TAG_RE.sub("", text).strip()


def extract_quiz_difficulty(value: str) -> str | None:
    match = QUIZ_DIFFICULTY_RE.search(value)
    if not match:
        return None
    difficulty = match.group("difficulty").strip().lower()
    return difficulty or None


def matches_quiz_difficulty(value: str, expected: str | None) -> bool:
    if not expected:
        return True
    actual = extract_quiz_difficulty(value)
    if actual is None:
        # Backward-compatibility: historical quiz exports were implicitly medium.
        return expected == "medium"
    return actual == expected


def has_quiz_cfg_tag(value: str) -> bool:
    return QUIZ_TYPE_RE.search(value) is not None


def is_excluded_quiz_json_name(name: str) -> bool:
    normalized = name.strip().lower()
    if ".html.request" in normalized and normalized.endswith(".json"):
        return True
    if normalized == "quiz_json_manifest.json":
        return True
    return normalized.endswith(("-manifest.json", "_manifest.json"))


def is_valid_quiz_payload(payload: Any) -> bool:
    if isinstance(payload, list):
        return True
    if not isinstance(payload, dict):
        return False
    questions = payload.get("questions")
    if isinstance(questions, list):
        return True
    quiz = payload.get("quiz")
    return isinstance(quiz, list)


def load_quiz_json_payload(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def to_public_quiz_relative_path(source_relative_path: str) -> str:
    return str(Path(source_relative_path).with_suffix(".html")).replace("\\", "/")


def to_source_quiz_json_relative_path(public_relative_path: str) -> str:
    return str(Path(public_relative_path).with_suffix(".json")).replace("\\", "/")


def canonical_key(stem: str) -> str:
    name = stem.replace("–", "-").replace("—", "-")
    name = strip_cfg_tag_suffix(name)
    name = normalize_week_tokens(name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", ".", name)
    prefix = ""
    if name.lower().startswith("[brief]"):
        prefix = "[Brief] "
        name = name[len("[brief]") :].lstrip()
    match = re.match(r"^(W\d{2}L\d+)\b(?:\s*-\s*)?(.*)$", name, re.IGNORECASE)
    if not match:
        return f"{prefix}{name}".strip()
    week = match.group(1).upper()
    rest = match.group(2).strip()
    if rest:
        rest = re.sub(
            rf"^{re.escape(week)}\b(?:\s*-\s*)?",
            "",
            rest,
            flags=re.IGNORECASE,
        ).strip()
    if rest:
        return f"{prefix}{week} - {rest}".strip()
    return f"{prefix}{week}".strip()


def audio_candidate_rank(stem: str) -> tuple[int, int, int, str]:
    name = stem.replace("–", "-").replace("—", "-")
    name = strip_cfg_tag_suffix(name)
    name = normalize_week_tokens(name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", ".", name)
    if name.lower().startswith("[brief]"):
        name = name[len("[brief]") :].lstrip()
    duplicate_week_prefix = 1 if DUPLICATE_WEEK_PREFIX_RE.match(name) else 0
    has_missing_token = 1 if MISSING_TOKEN_RE.search(name) else 0
    return (duplicate_week_prefix, has_missing_token, len(name), name.casefold())


def select_audio_candidate(candidates: List[Path]) -> Path | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    ranked = [(audio_candidate_rank(candidate.stem), candidate) for candidate in candidates]
    ranked.sort(key=lambda item: (item[0], item[1].name.casefold()))
    best_rank = ranked[0][0]
    best = [candidate for rank, candidate in ranked if rank == best_rank]
    if len(best) == 1:
        return best[0]
    return None


def normalize_quiz_difficulty(value: str | None) -> str:
    difficulty = (value or "").strip().lower()
    return difficulty or "medium"


def build_flat_quiz_relative_path(
    audio_name: str,
    difficulty: str | None,
    flat_id_len: int,
) -> tuple[str, str]:
    if flat_id_len < 1:
        raise ValueError("--flat-id-len must be >= 1.")
    normalized_difficulty = normalize_quiz_difficulty(difficulty)
    seed = f"{canonical_key(Path(audio_name).stem)}|{normalized_difficulty}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"{digest[:flat_id_len]}.html", seed


def ensure_unique_flat_quiz_relative_path(
    registry: Dict[str, str],
    relative_path: str,
    seed: str,
    *,
    context: str,
) -> None:
    existing = registry.get(relative_path)
    if existing is None:
        registry[relative_path] = seed
        return
    if existing != seed:
        raise ValueError(
            f"Short quiz ID collision for '{relative_path}' while mapping '{context}'. "
            "Increase --flat-id-len."
        )


def quiz_link_sort_key(link: Dict[str, str]) -> tuple[int, str, str]:
    difficulty = normalize_quiz_difficulty(link.get("difficulty"))
    rel_path = str(link.get("relative_path") or "")
    return (QUIZ_DIFFICULTY_SORT_ORDER.get(difficulty, 99), difficulty, rel_path)


def select_primary_quiz_link(links: List[Dict[str, str]]) -> Dict[str, str] | None:
    if not links:
        return None
    ranked = sorted(
        links,
        key=lambda link: (
            QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER.get(
                normalize_quiz_difficulty(link.get("difficulty")),
                99,
            ),
            quiz_link_sort_key(link),
        ),
    )
    return ranked[0] if ranked else None


def build_mapping_entry(links: List[Dict[str, str]], subject_slug: str) -> Dict[str, Any] | None:
    if not links:
        return None
    normalized_links: List[Dict[str, str]] = []
    seen_difficulties: set[str] = set()
    for raw_link in sorted(links, key=quiz_link_sort_key):
        rel_path = str(raw_link.get("relative_path") or "").strip()
        if not rel_path:
            continue
        difficulty = normalize_quiz_difficulty(raw_link.get("difficulty"))
        if difficulty in seen_difficulties:
            continue
        seen_difficulties.add(difficulty)
        normalized_links.append(
            {
                "relative_path": rel_path,
                "format": str(raw_link.get("format") or "html"),
                "difficulty": difficulty,
                "subject_slug": subject_slug,
            }
        )
    if not normalized_links:
        return None
    primary = select_primary_quiz_link(normalized_links)
    if not primary:
        return None
    mapping_entry: Dict[str, Any] = {
        "relative_path": primary["relative_path"],
        "format": primary["format"],
        "difficulty": primary["difficulty"],
        "subject_slug": subject_slug,
    }
    if len(normalized_links) > 1:
        mapping_entry["links"] = normalized_links
    return mapping_entry


def derive_mp3_name_from_html(stem: str) -> str:
    name = stem.replace("–", "-").replace("—", "-")
    name = strip_cfg_tag_suffix(name)
    name = normalize_week_tokens(name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", ".", name)
    prefix = ""
    if name.lower().startswith("[brief]"):
        prefix = "[Brief] "
        name = name[len("[brief]") :].lstrip()
    match = re.match(r"^(W\d{2}L\d+)\s*-\s*(.*)$", name, re.IGNORECASE)
    if not match:
        return f"{prefix}{name}.mp3".strip()
    week = match.group(1).upper()
    rest = match.group(2).strip()
    if rest:
        rest = re.sub(
            rf"^{re.escape(week)}\b\s*-?\s*",
            "",
            rest,
            flags=re.IGNORECASE,
        ).strip()
    if rest:
        if rest.startswith("X "):
            base = f"{prefix}{week} {rest}"
        else:
            base = f"{prefix}{week} - {rest}"
    else:
        base = f"{prefix}{week}"
    return f"{base}.mp3".strip()


def resolve_path(path_str: str, repo_root: Path) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def find_files(root: Path, suffix: str) -> List[Path]:
    if not root.exists():
        return []
    return sorted(
        [
            path
            for path in root.rglob(f"*{suffix}")
            if path.is_file() and not path.name.startswith(".")
        ]
    )


def build_mp3_index(mp3_files: List[Path], language_tag: str) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}
    for path in mp3_files:
        if language_tag and language_tag not in path.stem:
            continue
        key = canonical_key(path.stem)
        index.setdefault(key, []).append(path)
    return index


def write_mapping(path: Path, mapping: Dict[str, Dict[str, Any]], dry_run: bool) -> None:
    payload = {"by_name": mapping}
    if dry_run:
        print(f"Dry run: skipping write to {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def run_rsync(
    output_root: Path,
    remote_root: str,
    host: str,
    user: str,
    ssh_key: str | None,
    dry_run: bool,
) -> None:
    remote_root_clean = remote_root.rstrip("/") or "/"
    remote_prepare_cmd = [
        "ssh",
    ]
    if ssh_key:
        remote_prepare_cmd.extend(["-i", ssh_key])
    remote_prepare_cmd.extend(
        [
            f"{user}@{host}",
            f"mkdir -p {shlex.quote(remote_root_clean)} && chmod 755 {shlex.quote(remote_root_clean)}",
        ]
    )
    print("Running:", " ".join(remote_prepare_cmd))
    if not dry_run:
        prepare_result = subprocess.run(remote_prepare_cmd, text=True)
        if prepare_result.returncode != 0:
            raise SystemExit(f"remote directory prep failed with exit code {prepare_result.returncode}")

    src = str(output_root) + "/"
    dest = f"{user}@{host}:{remote_root_clean}/"
    cmd = [
        "rsync",
        "-av",
        "--delete",
        "--no-owner",
        "--no-group",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        "--include",
        "*/",
        "--include",
        "*.html",
        "--include",
        "*.json",
        "--exclude",
        "*",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if ssh_key:
        cmd.extend(["-e", f"ssh -i {ssh_key}"])
    cmd.extend([src, dest])
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"rsync failed with exit code {result.returncode}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing quiz JSON outputs.",
    )
    parser.add_argument(
        "--links-file",
        default="shows/personlighedspsykologi-en/quiz_links.json",
        help="Path to quiz_links.json to update.",
    )
    parser.add_argument(
        "--subject-slug",
        required=True,
        help="Subject slug to assign on every quiz mapping entry.",
    )
    parser.add_argument(
        "--language-tag",
        default="[EN]",
        help="Only consider files containing this tag in the filename.",
    )
    parser.add_argument(
        "--quiz-difficulty",
        default="any",
        choices=("easy", "medium", "hard", "any"),
        help=(
            "Only map quiz JSON files for this difficulty. "
            "Use 'any' to include all difficulties. Default: any."
        ),
    )
    parser.add_argument(
        "--quiz-path-mode",
        default="flat-id",
        choices=("legacy", "flat-id"),
        help=(
            "Quiz relative path mode. "
            "'legacy' keeps folder/filename paths; 'flat-id' maps to deterministic IDs."
        ),
    )
    parser.add_argument(
        "--flat-id-len",
        type=int,
        default=8,
        help="Hex length for deterministic flat quiz IDs in flat-id mode (default: 8).",
    )
    parser.add_argument(
        "--derive-mp3-names",
        action="store_true",
        help="Derive MP3 names directly from quiz JSON filenames (no MP3 scan).",
    )
    parser.add_argument(
        "--remote-root",
        default="/var/www/quizzes/personlighedspsykologi",
        help="Remote quiz root directory.",
    )
    parser.add_argument(
        "--host",
        default="64.226.79.109",
        help="Droplet host.",
    )
    parser.add_argument(
        "--user",
        default="root",
        help="Droplet SSH user.",
    )
    parser.add_argument(
        "--ssh-key",
        default="~/.ssh/digitalocean_ed25519",
        help="SSH key for the droplet.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing or uploading.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip rsync upload (still writes mapping unless --dry-run).",
    )
    args = parser.parse_args()

    output_root = resolve_path(args.output_root, repo_root)
    links_file = resolve_path(args.links_file, repo_root)
    language_tag = args.language_tag
    quiz_difficulty = None if args.quiz_difficulty == "any" else args.quiz_difficulty
    subject_slug = str(args.subject_slug).strip().lower()
    if not SUBJECT_SLUG_RE.match(subject_slug):
        raise SystemExit("--subject-slug must match ^[a-z0-9-]+$")
    if args.flat_id_len < 1:
        raise SystemExit("--flat-id-len must be >= 1.")

    if not output_root.exists():
        raise SystemExit(f"Output root does not exist: {output_root}")

    all_json_files = find_files(output_root, ".json")
    candidate_json_files: List[Path] = []
    invalid_json_files: List[Path] = []
    invalid_payload_files: List[Path] = []
    for path in all_json_files:
        if is_excluded_quiz_json_name(path.name):
            continue
        if language_tag and language_tag not in path.stem:
            continue
        if not has_quiz_cfg_tag(path.stem):
            continue
        if not matches_quiz_difficulty(path.stem, quiz_difficulty):
            continue
        payload = load_quiz_json_payload(path)
        if payload is None:
            invalid_json_files.append(path)
            continue
        if not is_valid_quiz_payload(payload):
            invalid_payload_files.append(path)
            continue
        candidate_json_files.append(path)

    if not candidate_json_files:
        raise SystemExit(
            f"No valid quiz JSON files found under {output_root} "
            f"for difficulty={quiz_difficulty or 'any'}"
        )
    mapping_links: Dict[str, List[Dict[str, str]]] = {}
    unmatched: List[Path] = []
    ambiguous: List[Path] = []
    duplicate_targets: List[Path] = []
    mp3_index: Dict[str, List[Path]] = {}
    flat_id_registry: Dict[str, str] = {}
    upload_sources: Dict[str, Path] = {}
    mapped_source_json_files = 0

    if not args.derive_mp3_names:
        mp3_files = [p for p in find_files(output_root, ".mp3") if language_tag in p.stem]
        if not mp3_files:
            raise SystemExit(f"No MP3 files found under {output_root}")
        mp3_index = build_mp3_index(mp3_files, language_tag)

    for json_file in candidate_json_files:
        difficulty = normalize_quiz_difficulty(extract_quiz_difficulty(json_file.stem))
        if args.derive_mp3_names:
            mp3_name = derive_mp3_name_from_html(json_file.stem)
        else:
            key = canonical_key(json_file.stem)
            candidates = mp3_index.get(key, [])
            if len(candidates) == 0:
                unmatched.append(json_file)
                continue
            selected_candidate = select_audio_candidate(candidates)
            if selected_candidate is None:
                ambiguous.append(json_file)
                continue
            mp3_name = selected_candidate.name
        if args.quiz_path_mode == "flat-id":
            try:
                relative_path, flat_seed = build_flat_quiz_relative_path(
                    mp3_name,
                    difficulty,
                    args.flat_id_len,
                )
                ensure_unique_flat_quiz_relative_path(
                    flat_id_registry,
                    relative_path,
                    flat_seed,
                    context=str(json_file),
                )
            except ValueError as exc:
                raise SystemExit(str(exc))
        else:
            source_relative_path = json_file.relative_to(output_root).as_posix()
            relative_path = to_public_quiz_relative_path(source_relative_path)
        links = mapping_links.setdefault(mp3_name, [])
        if any(normalize_quiz_difficulty(link.get("difficulty")) == difficulty for link in links):
            duplicate_targets.append(json_file)
            continue
        links.append(
            {
                "relative_path": relative_path,
                "format": "html",
                "difficulty": difficulty,
            }
        )
        upload_relative_path = to_source_quiz_json_relative_path(relative_path)
        existing_source = upload_sources.get(upload_relative_path)
        if existing_source is not None and existing_source != json_file:
            raise SystemExit(
                f"Multiple source files map to '{upload_relative_path}' "
                f"({existing_source} vs {json_file})."
            )
        upload_sources[upload_relative_path] = json_file
        mapped_source_json_files += 1

    sorted_mapping: Dict[str, Dict[str, Any]] = {}
    mapped_quiz_links = 0
    for key in sorted(mapping_links):
        mapping_entry = build_mapping_entry(mapping_links[key], subject_slug)
        if not mapping_entry:
            continue
        sorted_mapping[key] = mapping_entry
        links = mapping_entry.get("links")
        if isinstance(links, list):
            mapped_quiz_links += len(links)
        else:
            mapped_quiz_links += 1
    write_mapping(links_file, sorted_mapping, args.dry_run)

    print(f"Quiz difficulty filter: {quiz_difficulty or 'any'}")
    print(f"Quiz JSON files: {len(candidate_json_files)}")
    print(f"Mapped source quiz JSON files: {mapped_source_json_files}")
    print(f"Mapped episode quizzes: {len(sorted_mapping)}")
    print(f"Mapped quiz links: {mapped_quiz_links}")
    if invalid_json_files:
        print(f"Unreadable quiz JSON files: {len(invalid_json_files)}")
        for path in invalid_json_files[:20]:
            print(f"- {path}")
        if len(invalid_json_files) > 20:
            print(f"... and {len(invalid_json_files) - 20} more")
    if invalid_payload_files:
        print(f"Invalid quiz JSON payload files: {len(invalid_payload_files)}")
        for path in invalid_payload_files[:20]:
            print(f"- {path}")
        if len(invalid_payload_files) > 20:
            print(f"... and {len(invalid_payload_files) - 20} more")
    if unmatched:
        print(f"Unmatched quizzes: {len(unmatched)}")
        for path in unmatched[:20]:
            print(f"- {path}")
        if len(unmatched) > 20:
            print(f"... and {len(unmatched) - 20} more")
    if ambiguous:
        print(f"Ambiguous quizzes: {len(ambiguous)}")
        for path in ambiguous[:20]:
            print(f"- {path}")
        if len(ambiguous) > 20:
            print(f"... and {len(ambiguous) - 20} more")
    if duplicate_targets:
        print(f"Duplicate quiz difficulty mappings: {len(duplicate_targets)}")
        for path in duplicate_targets[:20]:
            print(f"- {path}")
        if len(duplicate_targets) > 20:
            print(f"... and {len(duplicate_targets) - 20} more")

    staging_dir = None
    try:
        if not args.no_upload:
            upload_root = output_root
            if args.quiz_path_mode == "flat-id":
                if not upload_sources:
                    raise SystemExit(
                        "No mapped quiz files to upload in flat-id mode; aborting upload to avoid deleting remote content."
                    )
                staging_dir = tempfile.TemporaryDirectory(prefix="quiz-flat-id-")
                upload_root = Path(staging_dir.name)
                for relative_path in sorted(upload_sources):
                    source_path = upload_sources[relative_path]
                    destination = upload_root / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination)
            ssh_key = args.ssh_key
            if ssh_key:
                ssh_key = str(Path(ssh_key).expanduser())
            run_rsync(
                output_root=upload_root,
                remote_root=args.remote_root,
                host=args.host,
                user=args.user,
                ssh_key=ssh_key,
                dry_run=args.dry_run,
            )
        else:
            print("Upload skipped (--no-upload).")
    finally:
        if staging_dir is not None:
            staging_dir.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
