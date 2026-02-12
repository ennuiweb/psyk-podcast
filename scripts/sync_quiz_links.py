#!/usr/bin/env python3
"""Sync quiz HTML exports to the droplet and update quiz_links.json."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


WEEK_TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
CFG_TAG_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)


def normalize_week_tokens(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        week = match.group("week").zfill(2)
        lecture = match.group("lecture")
        return f"W{week}L{lecture}"

    return WEEK_TOKEN_RE.sub(repl, text)


def strip_cfg_tag_suffix(text: str) -> str:
    return CFG_TAG_RE.sub("", text).strip()


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


def write_mapping(path: Path, mapping: Dict[str, Dict[str, str]], dry_run: bool) -> None:
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

    if not output_root.exists():
        raise SystemExit(f"Output root does not exist: {output_root}")

    html_files = [p for p in find_files(output_root, ".html") if language_tag in p.stem]
    if not html_files:
        raise SystemExit(f"No quiz HTML files found under {output_root}")
    mapping: Dict[str, Dict[str, str]] = {}
    unmatched: List[Path] = []
    ambiguous: List[Path] = []
    duplicate_targets: List[Path] = []

    for html_file in html_files:
        if args.derive_mp3_names:
            mp3_name = derive_mp3_name_from_html(html_file.stem)
            if mp3_name in mapping:
                duplicate_targets.append(html_file)
                continue
        else:
            mp3_files = [p for p in find_files(output_root, ".mp3") if language_tag in p.stem]
            if not mp3_files:
                raise SystemExit(f"No MP3 files found under {output_root}")
            mp3_index = build_mp3_index(mp3_files, language_tag)
            key = canonical_key(html_file.stem)
            candidates = mp3_index.get(key, [])
            if len(candidates) == 0:
                unmatched.append(html_file)
                continue
            if len(candidates) > 1:
                ambiguous.append(html_file)
                continue
            mp3_name = candidates[0].name
        relative_path = html_file.relative_to(output_root).as_posix()
        mapping[mp3_name] = {
            "relative_path": relative_path,
            "format": "html",
        }

    sorted_mapping = {key: mapping[key] for key in sorted(mapping)}
    write_mapping(links_file, sorted_mapping, args.dry_run)

    print(f"Quiz HTML files: {len(html_files)}")
    print(f"Mapped quizzes: {len(sorted_mapping)}")
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
        print(f"Duplicate mappings: {len(duplicate_targets)}")
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
