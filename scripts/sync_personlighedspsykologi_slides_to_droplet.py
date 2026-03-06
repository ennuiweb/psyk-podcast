#!/usr/bin/env python3
"""Sync Personlighedspsykologi slide files from OneDrive to droplet + catalog."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path


DEFAULT_READING_KEY = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_SLIDES_CATALOG_PATH = "shows/personlighedspsykologi-en/slides_catalog.json"
DEFAULT_REMOTE_ROOT = "/var/www/slides/personlighedspsykologi"
DEFAULT_HOST = "64.226.79.109"
DEFAULT_USER = "root"
DEFAULT_SSH_KEY = "~/.ssh/digitalocean_ed25519"
DEFAULT_SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_SOURCES = [
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi/Øvelseshold",
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi/Seminarhold/Slides",
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi/Forelæsningsrækken",
]

LECTURE_HEADING_RE = re.compile(
    r"^\*\*(?P<lecture_key>W\d{2}L\d+).*?\(Forel(?:æ|ae)sning\s*(?P<number>\d+)"
    r"(?:,\s*(?P<date>\d{4}-\d{2}-\d{2}))?\)\*\*$",
    re.IGNORECASE,
)
LECTURE_KEY_TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
LECTURE_NUMBER_PATTERNS = (
    re.compile(r"\bforel(?:æ|ae)sning\s*(?P<number>\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bgang\s*(?P<number>\d{1,2})\b", re.IGNORECASE),
    re.compile(r"perspsy[_\-\s]*(?P<number>\d{1,2})", re.IGNORECASE),
    re.compile(r"^\s*(?P<number>\d{1,2})[\.\-_ ]"),
)
DATE_TOKEN_RE = re.compile(r"(?<!\d)(?P<token>\d{6})(?!\d)")
SLIDE_SUFFIXES = {".pdf", ".ppt", ".pptx", ".key", ".odp"}
PATH_SEPARATORS_RE = re.compile(r"[\\/]+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
MULTISPACE_RE = re.compile(r"\s+")
IGNORE_STEM_PATTERNS = (
    re.compile(r"^\s*test\s*$", re.IGNORECASE),
    re.compile(r"\bpensum\b", re.IGNORECASE),
    re.compile(r"\bpensumliste\b", re.IGNORECASE),
    re.compile(r"\bforel(?:æ|ae)sningsplan\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class SlideSource:
    source_path: Path
    source_root: Path
    subcategory: str


@dataclass(frozen=True)
class SlideResolution:
    lecture_key: str
    slide_key: str
    subcategory: str
    title: str
    source_filename: str
    source_path: Path
    target_relative: Path
    matched_by: str


def _canonical_lecture_key(value: str) -> str | None:
    match = LECTURE_KEY_TOKEN_RE.search(str(value or "").strip())
    if not match:
        return None
    week = int(match.group("week"))
    lecture = int(match.group("lecture"))
    return f"W{week:02d}L{lecture}"


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower().replace("&", " and ")
    normalized = normalized.replace("–", "-").replace("—", "-").replace("_", " ").replace("/", " ")
    normalized = NON_ALNUM_RE.sub(" ", normalized)
    normalized = MULTISPACE_RE.sub(" ", normalized).strip()
    return normalized


def _clean_filename(value: str) -> str:
    return PATH_SEPARATORS_RE.sub("-", str(value or "").strip())


def _human_title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    title = MULTISPACE_RE.sub(" ", stem.replace("_", " ").strip()).strip()
    return title or filename


def _subcategory_from_source_path(path: Path) -> str:
    normalized = _normalize_title(str(path))
    if "ovelseshold" in normalized or "øvelseshold" in str(path).lower():
        return "exercise"
    if "seminarhold" in normalized or "seminar" in normalized:
        return "seminar"
    return "lecture"


def _lecture_maps_from_reading_key(path: Path) -> tuple[dict[int, str], dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Reading key not found: {path}")
    number_to_key: dict[int, str] = {}
    date_to_key: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LECTURE_HEADING_RE.match(line)
        if not match:
            continue
        lecture_key = _canonical_lecture_key(match.group("lecture_key"))
        if not lecture_key:
            continue
        number = int(match.group("number"))
        number_to_key[number] = lecture_key
        date_text = str(match.group("date") or "").strip()
        if date_text:
            date_to_key[date_text] = lecture_key
    return number_to_key, date_to_key


def _lecture_key_from_number(
    text: str,
    *,
    number_to_key: dict[int, str],
) -> tuple[str | None, str]:
    for pattern in LECTURE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        number = int(match.group("number"))
        lecture_key = number_to_key.get(number)
        if lecture_key:
            return lecture_key, f"lecture_number:{number}"
    return None, ""


def _date_key_from_token(token: str) -> str | None:
    if not token or len(token) != 6 or not token.isdigit():
        return None
    year = int(token[0:2])
    month = int(token[2:4])
    day = int(token[4:6])
    full_year = 2000 + year
    try:
        parsed = dt.date(full_year, month, day)
    except ValueError:
        return None
    return parsed.isoformat()


def _lecture_key_from_date(
    text: str,
    *,
    date_to_key: dict[str, str],
) -> tuple[str | None, str]:
    for match in DATE_TOKEN_RE.finditer(text):
        date_key = _date_key_from_token(str(match.group("token") or ""))
        if not date_key:
            continue
        lecture_key = date_to_key.get(date_key)
        if lecture_key:
            return lecture_key, f"date_token:{match.group('token')}"
    return None, ""


def _is_slide_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.startswith("."):
        return False
    if path.suffix.lower() not in SLIDE_SUFFIXES:
        return False
    stem = Path(path.name).stem
    for pattern in IGNORE_STEM_PATTERNS:
        if pattern.search(stem):
            return False
    return True


def _collect_sources(roots: list[Path]) -> list[SlideSource]:
    sources: list[SlideSource] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            raise SystemExit(f"Source root not found: {root}")
        subcategory = _subcategory_from_source_path(root)
        for file_path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
            if not _is_slide_file(file_path):
                continue
            sources.append(
                SlideSource(
                    source_path=file_path.resolve(),
                    source_root=root.resolve(),
                    subcategory=subcategory,
                )
            )
    return sources


def _slide_key(*, lecture_key: str, subcategory: str, source_filename: str, title: str) -> str:
    normalized_title = _normalize_title(title)
    slug = NON_ALNUM_RE.sub("-", normalized_title).strip("-")[:48] or "slide"
    digest = hashlib.sha1(
        f"{lecture_key}|{subcategory}|{source_filename}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{lecture_key.lower()}-{subcategory}-{slug}-{digest}"


def _resolve_sources(
    sources: list[SlideSource],
    *,
    number_to_key: dict[int, str],
    date_to_key: dict[str, str],
) -> tuple[list[SlideResolution], list[str]]:
    resolved: list[SlideResolution] = []
    unresolved: list[str] = []
    target_registry: dict[Path, Path] = {}

    for source in sources:
        relative_to_root = source.source_path.relative_to(source.source_root)
        path_text = str(relative_to_root)
        filename = _clean_filename(source.source_path.name)
        if not filename:
            unresolved.append(f"{path_text} | invalid filename")
            continue

        lecture_key = _canonical_lecture_key(path_text)
        matched_by = "lecture_key_token"
        if not lecture_key:
            lecture_key, matched_by = _lecture_key_from_number(
                path_text,
                number_to_key=number_to_key,
            )
        if not lecture_key:
            lecture_key, matched_by = _lecture_key_from_date(
                path_text,
                date_to_key=date_to_key,
            )
        if not lecture_key:
            unresolved.append(f"{path_text} | no lecture mapping")
            continue

        title = _human_title_from_filename(filename)
        slide_key = _slide_key(
            lecture_key=lecture_key,
            subcategory=source.subcategory,
            source_filename=filename,
            title=title,
        )
        target_relative = Path(lecture_key) / source.subcategory / filename
        existing_source = target_registry.get(target_relative)
        if existing_source is not None and existing_source != source.source_path:
            unresolved.append(
                f"{path_text} | duplicate target collision for {target_relative}"
            )
            continue
        target_registry[target_relative] = source.source_path

        resolved.append(
            SlideResolution(
                lecture_key=lecture_key,
                slide_key=slide_key,
                subcategory=source.subcategory,
                title=title,
                source_filename=filename,
                source_path=source.source_path,
                target_relative=target_relative,
                matched_by=matched_by,
            )
        )

    resolved.sort(
        key=lambda item: (
            item.lecture_key,
            item.subcategory,
            item.title.casefold(),
            item.source_filename.casefold(),
        )
    )
    return resolved, unresolved


def _run(cmd: list[str], *, dry_run: bool) -> None:
    print("Running:", " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")


def _sync_to_droplet(
    resolutions: list[SlideResolution],
    *,
    host: str,
    user: str,
    ssh_key: str | None,
    remote_root: str,
    dry_run: bool,
) -> None:
    if not resolutions:
        raise SystemExit("No resolved slides to sync; aborting to avoid destructive rsync.")

    with tempfile.TemporaryDirectory(prefix="slide-sync-") as tmpdir:
        stage_root = Path(tmpdir)
        for item in resolutions:
            destination = stage_root / item.target_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, destination)

        remote_clean = remote_root.rstrip("/") or "/"
        ssh_cmd = ["ssh"]
        if ssh_key:
            ssh_cmd.extend(["-i", ssh_key])
        ssh_cmd.extend([f"{user}@{host}", f"mkdir -p {shlex.quote(remote_clean)}"])
        _run(ssh_cmd, dry_run=dry_run)

        rsync_cmd = [
            "rsync",
            "-av",
            "--delete",
            "--no-owner",
            "--no-group",
            "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        ]
        if ssh_key:
            rsync_cmd.extend(["-e", f"ssh -i {ssh_key}"])
        rsync_cmd.extend([f"{stage_root}/", f"{user}@{host}:{remote_clean}/"])
        _run(rsync_cmd, dry_run=dry_run)

        perm_cmd = ["ssh"]
        if ssh_key:
            perm_cmd.extend(["-i", ssh_key])
        remote_quoted = shlex.quote(remote_clean)
        perm_cmd.extend(
            [
                f"{user}@{host}",
                (
                    f"chmod 755 {remote_quoted} && "
                    f"find {remote_quoted} -type d -exec chmod 755 {{}} + && "
                    f"find {remote_quoted} -type f -exec chmod 644 {{}} +"
                ),
            ]
        )
        _run(perm_cmd, dry_run=dry_run)


def _write_catalog(
    resolutions: list[SlideResolution],
    unresolved: list[str],
    *,
    destination: Path,
    subject_slug: str,
    dry_run: bool,
) -> None:
    catalog = {
        "version": 1,
        "subject_slug": str(subject_slug or "").strip().lower(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "slides": [
            {
                "slide_key": item.slide_key,
                "lecture_key": item.lecture_key,
                "subcategory": item.subcategory,
                "title": item.title,
                "source_filename": item.source_filename,
                "relative_path": str(item.target_relative),
                "matched_by": item.matched_by,
            }
            for item in resolutions
        ],
        "unresolved": unresolved,
    }
    if dry_run:
        print(f"DRY_RUN_ONLY: would write catalog to {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CATALOG_WRITTEN={destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reading-key", default=DEFAULT_READING_KEY, help="Path to reading-file-key markdown.")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Slide source root directory. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--catalog-path",
        default=DEFAULT_SLIDES_CATALOG_PATH,
        help="Destination path for slides catalog JSON.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Droplet host.")
    parser.add_argument("--user", default=DEFAULT_USER, help="Droplet SSH user.")
    parser.add_argument("--ssh-key", default=DEFAULT_SSH_KEY, help="SSH private key path.")
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT, help="Remote destination root.")
    parser.add_argument("--subject-slug", default=DEFAULT_SUBJECT_SLUG, help="Subject slug for catalog payload.")
    parser.add_argument("--allow-unresolved", action="store_true", help="Continue when some files are unresolved.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and commands without writing/copying.")
    parser.add_argument("--no-upload", action="store_true", help="Write catalog only; skip droplet rsync.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    reading_key_path = Path(args.reading_key).expanduser()
    if not reading_key_path.is_absolute():
        reading_key_path = (repo_root / reading_key_path).resolve()
    else:
        reading_key_path = reading_key_path.resolve()

    catalog_path = Path(args.catalog_path).expanduser()
    if not catalog_path.is_absolute():
        catalog_path = (repo_root / catalog_path).resolve()
    else:
        catalog_path = catalog_path.resolve()

    sources_raw = list(args.source) if args.source else list(DEFAULT_SOURCES)
    source_roots = [Path(item).expanduser().resolve() for item in sources_raw]
    ssh_key = str(Path(args.ssh_key).expanduser()) if args.ssh_key else None

    number_to_key, date_to_key = _lecture_maps_from_reading_key(reading_key_path)
    sources = _collect_sources(source_roots)
    resolutions, unresolved = _resolve_sources(
        sources,
        number_to_key=number_to_key,
        date_to_key=date_to_key,
    )

    print(f"Sources: {len(source_roots)}")
    print(f"Slide files discovered: {len(sources)}")
    print(f"Lecture mappings from reading key: {len(number_to_key)} numbers, {len(date_to_key)} dates")
    print(f"Resolved: {len(resolutions)}")
    print(f"Unresolved: {len(unresolved)}")
    if unresolved:
        for item in unresolved[:80]:
            print(f"- {item}")
        if len(unresolved) > 80:
            print(f"... and {len(unresolved) - 80} more")

    if unresolved and not args.allow_unresolved:
        raise SystemExit("Unresolved slides found; rerun with --allow-unresolved to sync only resolved files.")

    _write_catalog(
        resolutions,
        unresolved,
        destination=catalog_path,
        subject_slug=args.subject_slug,
        dry_run=args.dry_run,
    )

    if args.no_upload:
        print("Upload skipped (--no-upload).")
        return 0

    _sync_to_droplet(
        resolutions,
        host=args.host,
        user=args.user,
        ssh_key=ssh_key,
        remote_root=args.remote_root,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
