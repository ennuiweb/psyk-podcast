#!/usr/bin/env python3
"""Sync quiz HTML exports to the droplet and update quiz_links.json."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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
DUPLICATE_WEEK_PREFIX_RE = re.compile(r"^(W\d{2}L\d+)\s*-\s*\1\b", re.IGNORECASE)
MISSING_TOKEN_RE = re.compile(r"\bMISSING\b", re.IGNORECASE)
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


def build_mapping_entry(links: List[Dict[str, str]]) -> Dict[str, Any] | None:
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
    src = str(output_root) + "/"
    dest = f"{user}@{host}:{remote_root.rstrip('/')}/"
    cmd = [
        "rsync",
        "-av",
        "--delete",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        "--include",
        "*/",
        "--include",
        "*.html",
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
        help="Root folder containing quiz HTML outputs.",
    )
    parser.add_argument(
        "--links-file",
        default="shows/personlighedspsykologi-en/quiz_links.json",
        help="Path to quiz_links.json to update.",
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
            "Only map quiz HTML files for this difficulty. "
            "Use 'any' to include all difficulties. Default: any."
        ),
    )
    parser.add_argument(
        "--derive-mp3-names",
        action="store_true",
        help="Derive MP3 names directly from HTML filenames (no MP3 scan).",
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

    if not output_root.exists():
        raise SystemExit(f"Output root does not exist: {output_root}")

    html_files = [
        p
        for p in find_files(output_root, ".html")
        if language_tag in p.stem and matches_quiz_difficulty(p.stem, quiz_difficulty)
    ]
    if not html_files:
        raise SystemExit(
            f"No quiz HTML files found under {output_root} "
            f"for difficulty={quiz_difficulty or 'any'}"
        )
    mapping_links: Dict[str, List[Dict[str, str]]] = {}
    unmatched: List[Path] = []
    ambiguous: List[Path] = []
    duplicate_targets: List[Path] = []
    mp3_index: Dict[str, List[Path]] = {}

    if not args.derive_mp3_names:
        mp3_files = [p for p in find_files(output_root, ".mp3") if language_tag in p.stem]
        if not mp3_files:
            raise SystemExit(f"No MP3 files found under {output_root}")
        mp3_index = build_mp3_index(mp3_files, language_tag)

    for html_file in html_files:
        difficulty = normalize_quiz_difficulty(extract_quiz_difficulty(html_file.stem))
        if args.derive_mp3_names:
            mp3_name = derive_mp3_name_from_html(html_file.stem)
        else:
            key = canonical_key(html_file.stem)
            candidates = mp3_index.get(key, [])
            if len(candidates) == 0:
                unmatched.append(html_file)
                continue
            selected_candidate = select_audio_candidate(candidates)
            if selected_candidate is None:
                ambiguous.append(html_file)
                continue
            mp3_name = selected_candidate.name
        relative_path = html_file.relative_to(output_root).as_posix()
        links = mapping_links.setdefault(mp3_name, [])
        if any(normalize_quiz_difficulty(link.get("difficulty")) == difficulty for link in links):
            duplicate_targets.append(html_file)
            continue
        links.append(
            {
                "relative_path": relative_path,
                "format": "html",
                "difficulty": difficulty,
            }
        )

    sorted_mapping: Dict[str, Dict[str, Any]] = {}
    mapped_quiz_links = 0
    for key in sorted(mapping_links):
        mapping_entry = build_mapping_entry(mapping_links[key])
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
    print(f"Quiz HTML files: {len(html_files)}")
    print(f"Mapped episode quizzes: {len(sorted_mapping)}")
    print(f"Mapped quiz links: {mapped_quiz_links}")
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

    if not args.no_upload:
        ssh_key = args.ssh_key
        if ssh_key:
            ssh_key = str(Path(ssh_key).expanduser())
        run_rsync(
            output_root=output_root,
            remote_root=args.remote_root,
            host=args.host,
            user=args.user,
            ssh_key=ssh_key,
            dry_run=args.dry_run,
        )
    else:
        print("Upload skipped (--no-upload).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
