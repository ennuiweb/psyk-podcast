#!/usr/bin/env python3
"""rollout_week.py - Generate, download, upload, and publish B-variant episodes.

Full pipeline for A→B rollout of one or more lecture weeks. Designed to run
unattended in the background and handle all failure modes gracefully.

Pipeline phases:
  1. generate  — queue NotebookLM audio generation (with retry on rate limits)
  2. download  — pull completed MP3s
  3. upload    — copy new MP3s to Google Drive File Stream mount
  4. register  — resolve Drive file IDs via service account API, update
                 regeneration_registry.json (active_variant→B, b_active)
  5. exclude   — add A-variant name_regex exclude rules to config.github.json;
                 sync config.local.json to match (invariant requirement)
  6. publish   — git commit + pull --rebase + push + trigger generate-feed.yml

All phases are idempotent. The script can be safely re-run at any point.

Usage:
  ./rollout_week.py --week W11L1 --dry-run
  ./rollout_week.py --week W11L1
  ./rollout_week.py --weeks W11L1,W11L2
  ./rollout_week.py --week W11L1 --skip-generate
  ./rollout_week.py --week W11L1 --skip-publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import (  # noqa: E402
    canonical_source_name,
    classify_episode,
    extract_lecture_key,
    logical_episode_id,
    parse_config_tags,
    strip_leading_variant_prefix,
    strip_cfg_tag_from_filename,
)

VENV_PYTHON = REPO_ROOT / "notebooklm-podcast-auto/.venv/bin/python"
GENERATE_SCRIPT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py"
DOWNLOAD_SCRIPT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py"
OUTPUT_ROOT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/output"
REGISTRY_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/regeneration_registry.json"
CONFIG_GITHUB = REPO_ROOT / "shows/personlighedspsykologi-en/config.github.json"
CONFIG_LOCAL = REPO_ROOT / "shows/personlighedspsykologi-en/config.local.json"
SA_FILE = REPO_ROOT / "shows/personlighedspsykologi-en/service-account.json"
VALIDATE_SCRIPT = REPO_ROOT / "scripts/validate_regeneration_inventory.py"
DRIVE_MOUNT = Path(
    "~/Library/CloudStorage/GoogleDrive-psykku2025@gmail.com/My Drive/Personlighedspsykologi-en"
).expanduser()
AUDIO_URL_TEMPLATE = "https://drive.google.com/uc?export=download&id={file_id}"
DRIVE_MAIN_FOLDER_ID = "1lJD1TPU_Re7feq99Wj98RnWKbDjsi3qm"

# How many times to retry generation when all profiles are rate-limited.
# Each retry sleeps GENERATE_RETRY_SLEEP seconds (awake time) before re-running.
GENERATE_MAX_RETRIES = 8
GENERATE_RETRY_SLEEP = 14400  # 4 h — long enough for per-account quotas to reset

# Seconds to wait (total) for Drive File Stream to sync before querying service account.
DRIVE_SYNC_TIMEOUT = 90
DRIVE_SYNC_POLL = 10

# Max attempts to push before giving up.
PUSH_MAX_RETRIES = 3
ACTIVATABLE_ROLLOUT_STATES = {"b_registered", "b_feed_verified", "b_active"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log(phase: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{phase}] {msg}", flush=True)


def sleep_awake(total_seconds: float, phase: str = "generate", log_interval: float = 600.0) -> None:
    """Sleep for *total_seconds* of system-awake time.

    Uses time.monotonic() which is suspended during macOS system sleep
    (macOS monotonic clock stops when the machine sleeps), so the timer
    naturally pauses on sleep and resumes on wake without any extra
    signal handling.

    Logs remaining time every log_interval awake-seconds.
    """
    deadline = time.monotonic() + total_seconds
    last_log = time.monotonic() - log_interval  # log immediately on entry
    POLL = 30.0  # poll granularity — short enough to react to wake quickly

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        now_m = time.monotonic()
        if now_m - last_log >= log_interval:
            log(phase, f"sleeping… {remaining / 3600:.2f}h remaining (awake time)")
            last_log = now_m
        time.sleep(min(POLL, remaining))

    log(phase, "sleep complete — resuming")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "sample"

# ── Drive service ─────────────────────────────────────────────────────────────

def _drive_service() -> Any:
    try:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
    except ImportError:
        raise SystemExit(
            "google-api-python-client not available in venv. "
            "Run: pip install google-api-python-client google-auth"
        )
    creds = service_account.Credentials.from_service_account_file(
        str(SA_FILE),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def resolve_drive_subfolder(svc: Any, week_key: str) -> str | None:
    """Return Drive folder ID for a week key, or None if not found."""
    result = svc.files().list(
        q=(
            f"'{DRIVE_MAIN_FOLDER_ID}' in parents"
            " and mimeType = 'application/vnd.google-apps.folder'"
            " and trashed = false"
        ),
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    for f in result.get("files", []):
        if f["name"].upper() == week_key.upper():
            return f["id"]
    return None


def list_drive_mp3s(svc: Any, folder_id: str) -> dict[str, list[dict[str, str | int | None]]]:
    """Return {filename: [candidate metadata]} for all MP3s in a Drive folder."""
    result = svc.files().list(
        q=f"'{folder_id}' in parents and mimeType = 'audio/mpeg' and trashed = false",
        fields="files(id, name, size, md5Checksum, modifiedTime, createdTime)",
        pageSize=500,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    payload: dict[str, list[dict[str, str | int | None]]] = {}
    for item in result.get("files", []):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        raw_size = item.get("size")
        try:
            size = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError):
            size = None
        payload.setdefault(name, []).append(
            {
                "id": str(item.get("id") or "").strip(),
                "name": name,
                "size": size,
                "md5Checksum": str(item.get("md5Checksum") or "").strip() or None,
                "modifiedTime": str(item.get("modifiedTime") or "").strip() or None,
                "createdTime": str(item.get("createdTime") or "").strip() or None,
            }
        )
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── Exclude regex builder ─────────────────────────────────────────────────────

def build_exclude_regex(a_source_name: str) -> str | None:
    """Build a name_regex pattern that uniquely identifies an A-variant file.

    Patterns are evaluated case-insensitively by the feed builder, so we don't
    need explicit case handling. Patterns match against filename only (not path).
    """
    tags = parse_config_tags(a_source_name)
    a_hash = tags.get("hash")
    if not a_hash:
        return None
    week_key = extract_lecture_key(a_source_name)
    if not week_key:
        return None
    prompt_type = classify_episode(a_source_name)

    # Build a title fragment from the canonical (tag-stripped) name.
    canonical = strip_cfg_tag_from_filename(a_source_name).strip().replace(".mp3", "").strip()
    title = strip_leading_variant_prefix(canonical)
    title = re.sub(r"^W\d+L\d+\s*-\s*", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+\[.*\]$", "", title).strip()  # strip [EN] suffix

    if prompt_type == "weekly_readings_only":
        # One Alle kilder per week — week key + hash is sufficient.
        return rf"{re.escape(week_key)}.*Alle kilder.*{re.escape(a_hash)}"

    if prompt_type == "short":
        fragment = title[:40].strip()
        return rf"\[Short\].*{re.escape(week_key)}.*{re.escape(fragment)}.*{re.escape(a_hash)}"

    if prompt_type == "single_reading":
        # Include length and hash to pin to the exact file.
        length = tags.get("length", "long")
        # Use first ~20 chars of title as a discriminating fragment.
        fragment = title[:20].strip()
        return (
            rf"{re.escape(week_key)}.*{re.escape(fragment)}"
            rf".*length={length}.*{re.escape(a_hash)}"
        )

    # Slides, TTS, unknown — fall back to hash only (unlikely path in this pipeline).
    return rf"{re.escape(week_key)}.*{re.escape(a_hash)}"


def validate_regex(pattern: str) -> bool:
    """Return True if pattern compiles cleanly with IGNORECASE."""
    try:
        re.compile(pattern, re.IGNORECASE)
        return True
    except re.error as exc:
        log("exclude", f"WARNING: pattern rejected (invalid regex): {pattern!r} — {exc}")
        return False


# ── JSON helpers ──────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_b_variant(existing_b: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing_b)
    for key, value in updates.items():
        if value is None and key in {
            "transcribed_at",
            "judged_at",
            "review_outcome",
            "staging_drive_id",
            "local_audio_path",
        }:
            continue
        merged[key] = value
    history = list(merged.get("history") or [])
    if existing_b:
        old_episode_key = str(existing_b.get("episode_key") or "").strip()
        new_episode_key = str(updates.get("episode_key") or "").strip()
        if old_episode_key and new_episode_key and old_episode_key != new_episode_key:
            history.append(
                {
                    "episode_key": old_episode_key,
                    "source_name": existing_b.get("source_name"),
                    "review_outcome": existing_b.get("review_outcome"),
                    "judged_at": existing_b.get("judged_at"),
                    "transcribed_at": existing_b.get("transcribed_at"),
                    "replaced_at": utc_now(),
                }
            )
    if history:
        merged["history"] = history
    return merged


def stage_rollout_state(entry: dict[str, Any], state: str, *, active_variant: str | None = None) -> None:
    if active_variant in {"A", "B"}:
        entry["active_variant"] = active_variant
    rollout = entry.get("rollout") if isinstance(entry.get("rollout"), dict) else {}
    rollout["state"] = state
    if state == "b_active":
        rollout["activated_at"] = utc_now()
    entry["rollout"] = rollout


# ── Output directory scanning ─────────────────────────────────────────────────

def scan_week_output(week_key: str) -> dict[str, str]:
    """Return a dict describing the state of each planned output for a week.

    Keys are output filenames (basename). Values are one of:
      "mp3"     — file exists (fully downloaded)
      "queued"  — .request.json exists (generation queued, not yet downloaded)
      "error"   — .request.error.json exists (last attempt failed)
      "missing" — nothing (never attempted or cleaned up)
    """
    week_dir = OUTPUT_ROOT / week_key
    if not week_dir.exists():
        return {}

    status: dict[str, str] = {}
    for p in week_dir.iterdir():
        name = p.name
        if name.endswith(".request.error.json"):
            base = name[: -len(".request.error.json")]
            # Only record error if no better status already known.
            status.setdefault(base, "error")
        elif name.endswith(".request.json"):
            base = name[: -len(".request.json")]
            # request.json beats error.json.
            status[base] = "queued"
        elif name.endswith(".mp3"):
            # mp3 beats everything.
            status[name] = "mp3"

    return status


def planned_mp3_count(week_key: str) -> int:
    """Return the number of audio outputs generate_week.py would plan for this week."""
    result = subprocess.run(
        [str(VENV_PYTHON), str(GENERATE_SCRIPT), "--week", week_key,
         "--content-types", "audio", "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    # Output line: "W11L1: read N sources (M readings, K slides), found X missing outputs"
    m = re.search(r"found (\d+) missing outputs", result.stdout + result.stderr)
    if m:
        return int(m.group(1))
    # Fall back: count lines starting with known output type labels.
    count = sum(
        1 for line in (result.stdout + result.stderr).splitlines()
        if re.match(r"\s*(WEEKLY|READING|SHORT|SLIDE)\s+AUDIO", line, re.IGNORECASE)
    )
    return count


# ── Phase 1: Generate ─────────────────────────────────────────────────────────

def phase_generate(week_keys: list[str], dry_run: bool) -> tuple[int, int, int]:
    """Run ONE generation attempt. The wave loop in main() handles retries.

    Returns (queued, already_mp3, errors):
      queued      — outputs with a fresh request.json this run
      already_mp3 — outputs already downloaded as MP3
      errors      — outputs where generation failed (request.error.json)

    (queued=0, already_mp3=0, errors=0) means pure rate-limit exhaustion —
    no profiles were able to create a notebook at all.
    """
    if dry_run:
        cmd = [str(VENV_PYTHON), str(GENERATE_SCRIPT),
               "--weeks", ",".join(week_keys), "--content-types", "audio", "--dry-run"]
        log("generate", "dry-run: " + " ".join(cmd))
        subprocess.call(cmd, cwd=str(REPO_ROOT))
        return 0, 0, 0

    rc = subprocess.call(
        [str(VENV_PYTHON), str(GENERATE_SCRIPT),
         "--weeks", ",".join(week_keys), "--content-types", "audio"],
        cwd=str(REPO_ROOT),
    )
    log("generate", f"generate_week.py exited with code {rc}")

    queued = sum(
        sum(1 for v in scan_week_output(wk).values() if v == "queued")
        for wk in week_keys
    )
    mp3s = sum(
        sum(1 for v in scan_week_output(wk).values() if v == "mp3")
        for wk in week_keys
    )
    errors = sum(
        sum(1 for v in scan_week_output(wk).values() if v == "error")
        for wk in week_keys
    )
    log("generate", f"queued={queued}  already_mp3={mp3s}  errors={errors}")
    return queued, mp3s, errors


# ── Phase 2: Download ─────────────────────────────────────────────────────────

def phase_download(week_keys: list[str], dry_run: bool, allow_failure: bool = False) -> bool:
    """Download completed artifacts. Returns True if all expected MP3s are present."""
    if dry_run:
        log("download", "dry-run: would run download_week.py")
        return True

    rc = subprocess.call(
        [str(VENV_PYTHON), str(DOWNLOAD_SCRIPT),
         "--weeks", ",".join(week_keys), "--content-types", "audio"],
        cwd=str(REPO_ROOT),
    )
    # download_week.py always exits 0 — check MP3s directly.
    _ = rc
    missing = []
    for wk in week_keys:
        for name, status in scan_week_output(wk).items():
            if name.endswith(".mp3") and status != "mp3":
                missing.append(f"{wk}/{name}")
    if missing:
        log("download", f"{len(missing)} MP3(s) not yet downloaded")
        if not allow_failure:
            log("download", "WARNING: proceeding with partial set")
        return False
    log("download", "all expected MP3s present")
    return True


# ── Phase 3: Upload ───────────────────────────────────────────────────────────

def phase_upload(week_keys: list[str], dry_run: bool) -> dict[str, list[Path]]:
    """Copy new MP3s to Drive File Stream mount.

    Returns {week_key: [list of uploaded local Path objects]}.
    Only copies files not already present in Drive mount.
    """
    if not dry_run and not DRIVE_MOUNT.exists():
        log("upload", f"ERROR: Drive File Stream mount not found: {DRIVE_MOUNT}")
        log("upload", "Is Google Drive File Stream running and signed in as psykku2025@gmail.com?")
        return {}

    uploaded: dict[str, list[Path]] = {}
    for wk in week_keys:
        week_dir = OUTPUT_ROOT / wk
        if not week_dir.exists():
            log("upload", f"{wk}: no output directory — skipping")
            continue

        mp3s = sorted(p for p in week_dir.glob("*.mp3"))
        if not mp3s:
            log("upload", f"{wk}: no MP3s in output directory — skipping")
            continue

        dest_dir = DRIVE_MOUNT / wk
        if not dry_run and not dest_dir.exists():
            log("upload", f"{wk}: creating Drive subfolder: {dest_dir}")
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log("upload", f"ERROR: could not create Drive subfolder: {exc}")
                continue

        copied: list[Path] = []
        for src in mp3s:
            dest = dest_dir / src.name
            if not dry_run and dest.exists():
                log("upload", f"{wk}: already in Drive — {src.name}")
                copied.append(src)  # still track as "uploaded" for ID resolution
                continue
            if dry_run:
                log("upload", f"{wk}: dry-run: would copy {src.name}")
                copied.append(src)
            else:
                log("upload", f"{wk}: copying {src.name}")
                try:
                    shutil.copy2(src, dest)
                    copied.append(src)
                except OSError as exc:
                    log("upload", f"ERROR: failed to copy {src.name}: {exc}")

        if copied:
            uploaded[wk] = copied

    return uploaded


# ── Phase 4: Register ─────────────────────────────────────────────────────────

def resolve_drive_candidate(
    local_path: Path,
    candidates: list[dict[str, str | int | None]],
) -> dict[str, str | int | None] | None:
    local_size = local_path.stat().st_size if local_path.exists() else None
    if local_size is not None:
        sized = [candidate for candidate in candidates if candidate.get("size") == local_size]
        if len(sized) == 1:
            return sized[0]
        if len(sized) > 1:
            log(
                "register",
                f"ERROR: ambiguous Drive candidates for {local_path.name} at size {local_size}: "
                + ", ".join(str(candidate.get("id")) for candidate in sized),
            )
            return None
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    log(
        "register",
        f"ERROR: ambiguous Drive candidates for {local_path.name}: "
        + ", ".join(str(candidate.get("id")) for candidate in candidates),
    )
    return None


def wait_for_drive_sync(
    svc: Any,
    week_key: str,
    expected_paths: list[Path],
) -> dict[str, dict[str, str | int | None]]:
    """Poll Drive API until all expected files are visible, or timeout.

    Returns {filename: drive candidate metadata} for all unambiguous matches.
    """
    folder_id = resolve_drive_subfolder(svc, week_key)
    if not folder_id:
        log("register", f"ERROR: Drive subfolder '{week_key}' not found in main folder")
        return {}

    expected_names = [path.name for path in expected_paths]
    local_by_name = {path.name: path for path in expected_paths}
    deadline = time.time() + DRIVE_SYNC_TIMEOUT
    found: dict[str, dict[str, str | int | None]] = {}
    while time.time() < deadline:
        drive_files = list_drive_mp3s(svc, folder_id)
        found = {}
        missing = []
        for name in expected_names:
            local_path = local_by_name[name]
            candidate = resolve_drive_candidate(local_path, drive_files.get(name, []))
            if candidate is None:
                if name not in drive_files:
                    missing.append(name)
                continue
            found[name] = candidate
        missing = [name for name in expected_names if name not in found]
        if not missing:
            log("register", f"{week_key}: all {len(expected_names)} file(s) visible in Drive")
            return found
        log("register",
            f"{week_key}: waiting for Drive sync… {len(found)}/{len(expected_names)} visible "
            f"({len(missing)} pending)")
        time.sleep(DRIVE_SYNC_POLL)

    log("register",
        f"WARNING: Drive sync timeout after {DRIVE_SYNC_TIMEOUT}s; "
        f"proceeding with {len(found)}/{len(expected_names)} resolved")
    return found


def recompute_registry_summary(entries: list[dict]) -> dict:
    prompt_type_counts: dict[str, int] = {}
    rollout_state_counts: dict[str, int] = {}
    active_variant_counts: dict[str, int] = {}
    in_scope = 0
    out_of_scope = 0
    for entry in entries:
        pt = str(entry.get("prompt_type") or "unknown")
        prompt_type_counts[pt] = prompt_type_counts.get(pt, 0) + 1
        av = str(entry.get("active_variant") or "A")
        active_variant_counts[av] = active_variant_counts.get(av, 0) + 1
        rollout = entry.get("rollout") if isinstance(entry.get("rollout"), dict) else {}
        state = str(rollout.get("state") or "unknown")
        rollout_state_counts[state] = rollout_state_counts.get(state, 0) + 1
        if rollout.get("in_scope"):
            in_scope += 1
        else:
            out_of_scope += 1
    return {
        "total_entries": len(entries),
        "in_scope_entries": in_scope,
        "out_of_scope_entries": out_of_scope,
        "prompt_type_counts": dict(sorted(prompt_type_counts.items())),
        "rollout_state_counts": dict(sorted(rollout_state_counts.items())),
        "active_variant_counts": dict(sorted(active_variant_counts.items())),
    }


def phase_register(
    uploaded: dict[str, list[Path]],
    dry_run: bool,
) -> list[dict]:
    """Resolve Drive IDs and update regeneration_registry.json.

    Returns the list of registry entries staged for B activation.
    """
    if not uploaded:
        log("register", "nothing to register")
        return []

    registry = read_json(REGISTRY_PATH)
    entries_by_lid = {
        str(e.get("logical_episode_id")): e
        for e in registry["entries"]
        if isinstance(e, dict) and e.get("logical_episode_id")
    }

    if dry_run:
        log("register", "dry-run: validating LID→registry mapping for planned outputs")
        ok = 0
        bad = 0
        for wk, mp3_paths in uploaded.items():
            for p in mp3_paths:
                lid = logical_episode_id(p.name)
                if lid in entries_by_lid:
                    log("register", f"  ✓ {p.name[:60]}…  lid={lid}")
                    ok += 1
                else:
                    log("register", f"  ✗ NO MATCH: {p.name[:60]}…  lid={lid}")
                    bad += 1
        log("register", f"dry-run: {ok} matched, {bad} unmatched")
        log("register", "dry-run: would wait for Drive sync and update registry")
        return []

    svc = _drive_service()
    now = utc_now()
    updated_entries: list[dict] = []

    for wk, mp3_paths in uploaded.items():
        drive_candidates = wait_for_drive_sync(svc, wk, mp3_paths)

        for mp3_path in mp3_paths:
            fname = mp3_path.name
            candidate = drive_candidates.get(fname)
            if not candidate:
                log("register", f"WARNING: no Drive ID for {fname} — skipping entry")
                continue
            drive_id = str(candidate.get("id") or "").strip()
            if not drive_id:
                log("register", f"WARNING: candidate for {fname} is missing a Drive ID — skipping entry")
                continue

            lid = logical_episode_id(fname)
            entry = entries_by_lid.get(lid)
            if entry is None:
                log("register", f"WARNING: no registry entry for lid={lid} ({fname})")
                continue

            # Skip if already B-active with the same file.
            existing_b = (entry.get("variants") or {}).get("B") or {}
            if (
                entry.get("active_variant") == "B"
                and (entry.get("rollout") or {}).get("state") in ACTIVATABLE_ROLLOUT_STATES
                and existing_b.get("episode_key") == drive_id
            ):
                log("register", f"already staged/active B: {lid}")
                updated_entries.append(entry)
                continue

            tags = parse_config_tags(fname)
            b_variant = {
                "status": "published",
                "source_name": fname,
                "canonical_source_name": canonical_source_name(fname),
                "config_tags": tags,
                "config_hash": tags.get("hash"),
                "episode_key": drive_id,
                "audio_url": AUDIO_URL_TEMPLATE.format(file_id=drive_id),
                "published_at": now,
                "title": entry.get("title"),
                "local_audio_path": str(mp3_path),
                "staging_drive_id": None,
                "audio_sha256": file_sha256(mp3_path),
                "generated_at": existing_b.get("generated_at") or now,
                "uploaded_at": now,
                "registered_at": now,
                "transcribed_at": None,
                "judged_at": None,
                "review_outcome": None,
                "size_bytes": mp3_path.stat().st_size if mp3_path.exists() else None,
                "drive_md5": candidate.get("md5Checksum"),
            }

            merged_b = merge_b_variant(existing_b, b_variant)

            if not isinstance(entry.get("variants"), dict):
                entry["variants"] = {}
            entry["variants"]["B"] = merged_b
            stage_rollout_state(entry, "b_registered", active_variant="B")

            log("register", f"B-registered: {lid}  drive_id={drive_id}")
            updated_entries.append(entry)

    if updated_entries:
        registry["summary"] = recompute_registry_summary(registry["entries"])
        write_json(REGISTRY_PATH, registry)
        log("register", f"wrote registry: {len(updated_entries)} entries updated")

    return updated_entries


# ── Phase 5: Exclude ──────────────────────────────────────────────────────────

def phase_exclude(updated_entries: list[dict], dry_run: bool) -> None:
    """Deprecated compatibility phase.

    Feed generation now reads the regeneration registry directly and chooses the
    active variant per logical episode, so rollout must not widen regex-based
    excludes anymore.
    """
    _ = updated_entries
    if dry_run:
        log("exclude", "dry-run: no config exclude changes (registry-driven selection)")
        return
    log("exclude", "skipped: registry-driven feed selection is active")


# ── Phase 6: Publish ──────────────────────────────────────────────────────────

def _git_path_has_changes(path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def _stage_and_commit(paths: list[str], commit_msg: str) -> int:
    changed_paths = [path for path in paths if _git_path_has_changes(path)]
    if not changed_paths:
        log("publish", "nothing changed — skipping commit")
        return 0
    rc = subprocess.call(["git", "-C", str(REPO_ROOT), "add"] + changed_paths)
    if rc != 0:
        log("publish", f"ERROR: git add failed (exit {rc})")
        return rc
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--quiet"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        log("publish", "nothing staged — skipping commit")
        return 0
    rc = subprocess.call(["git", "-C", str(REPO_ROOT), "commit", "-m", commit_msg])
    if rc != 0:
        log("publish", f"ERROR: git commit failed (exit {rc})")
        return rc
    log("publish", f"committed: {commit_msg}")
    return 0


def _push_main_with_rebase() -> int:
    for attempt in range(1, PUSH_MAX_RETRIES + 1):
        log("publish", f"push attempt {attempt}/{PUSH_MAX_RETRIES}")
        rc = subprocess.call(["git", "-C", str(REPO_ROOT), "push", "origin", "main"])
        if rc == 0:
            log("publish", "pushed successfully")
            return 0
        log("publish", f"push failed (exit {rc}) — pulling with rebase")
        rebase_rc = subprocess.call(
            ["git", "-C", str(REPO_ROOT), "pull", "--rebase", "origin", "main"]
        )
        if rebase_rc != 0:
            log(
                "publish",
                f"ERROR: git pull --rebase failed (exit {rebase_rc}); manual conflict resolution required",
            )
            return rebase_rc
    log("publish", f"ERROR: push failed after {PUSH_MAX_RETRIES} attempts")
    return 1


def _latest_head_sha() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _find_workflow_run_id(head_sha: str) -> str | None:
    for _ in range(12):
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "generate-feed.yml",
                "--limit",
                "10",
                "--json",
                "databaseId,headSha,event,status,conclusion,createdAt",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                runs = json.loads(result.stdout or "[]")
            except json.JSONDecodeError:
                runs = []
            for run in runs:
                if (
                    str(run.get("headSha") or "").strip() == head_sha
                    and str(run.get("event") or "").strip() == "workflow_dispatch"
                ):
                    run_id = str(run.get("databaseId") or "").strip()
                    if run_id:
                        return run_id
        time.sleep(5)
    return None


def _watch_feed_workflow(head_sha: str) -> int:
    run_id = _find_workflow_run_id(head_sha)
    if not run_id:
        log("publish", "ERROR: could not find generate-feed workflow run for pushed commit")
        return 1
    log("publish", f"watching generate-feed.yml run {run_id}")
    return subprocess.call(["gh", "run", "watch", run_id, "--exit-status"], cwd=str(REPO_ROOT))


def _pull_origin_main() -> int:
    return subprocess.call(["git", "-C", str(REPO_ROOT), "pull", "--ff-only", "origin", "main"])


def _validate_regeneration_inventory(week_keys: list[str]) -> int:
    cmd = [
        str(VENV_PYTHON),
        str(VALIDATE_SCRIPT),
        "--show-slug",
        "personlighedspsykologi-en",
        "--weeks",
        ",".join(week_keys),
    ]
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def phase_publish(week_keys: list[str], dry_run: bool) -> int:
    changed_files = [
        "shows/personlighedspsykologi-en/regeneration_registry.json",
        "shows/personlighedspsykologi-en/config.github.json",
        "shows/personlighedspsykologi-en/config.local.json",
    ]
    weeks_str = "+".join(week_keys)
    commit_msg = f"Rollout B-variant episodes for {weeks_str}"

    if dry_run:
        for f in changed_files:
            log("publish", f"dry-run: would stage {f}")
        log("publish", f"dry-run: would commit: {commit_msg.splitlines()[0]!r}")
        log("publish", "dry-run: would push, watch generate-feed.yml, pull, and validate inventory")
        return 0

    rc = _stage_and_commit(changed_files, commit_msg)
    if rc != 0:
        return rc

    rc = _push_main_with_rebase()
    if rc != 0:
        return rc
    pushed_sha = _latest_head_sha()

    rc = subprocess.call(
        ["gh", "workflow", "run", "generate-feed.yml", "--ref", "main"],
        cwd=str(REPO_ROOT),
    )
    if rc != 0:
        log("publish", f"ERROR: gh workflow run exited {rc}")
        return rc
    log("publish", "generate-feed.yml triggered")

    rc = _watch_feed_workflow(pushed_sha)
    if rc != 0:
        log("publish", f"ERROR: generate-feed workflow failed for {pushed_sha}")
        return rc

    rc = _pull_origin_main()
    if rc != 0:
        log("publish", f"ERROR: failed to pull generated feed commit from origin/main (exit {rc})")
        return rc

    rc = _validate_regeneration_inventory(week_keys)
    if rc != 0:
        log("publish", f"ERROR: registry/inventory validation failed (exit {rc})")
        return rc

    return 0


def phase_finalize_activation(week_keys: list[str], dry_run: bool) -> int:
    if dry_run:
        log("activate", "dry-run: would mark b_registered entries as b_active")
        return 0
    registry = read_json(REGISTRY_PATH)
    changed = 0
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("lecture_key") or "") not in week_keys:
            continue
        rollout = entry.get("rollout") if isinstance(entry.get("rollout"), dict) else {}
        if str(entry.get("active_variant") or "") != "B":
            continue
        if str(rollout.get("state") or "") != "b_registered":
            continue
        stage_rollout_state(entry, "b_active", active_variant="B")
        changed += 1
    if not changed:
        log("activate", "no b_registered entries to finalize")
        return 0
    registry["summary"] = recompute_registry_summary(registry["entries"])
    write_json(REGISTRY_PATH, registry)
    log("activate", f"marked {changed} entries as b_active")

    rc = _stage_and_commit(
        ["shows/personlighedspsykologi-en/regeneration_registry.json"],
        f"Finalize B-variant activation for {'+'.join(week_keys)}",
    )
    if rc != 0:
        return rc
    return _push_main_with_rebase()


# ── Completion check ─────────────────────────────────────────────────────────

def all_registered(week_keys: list[str]) -> bool:
    """Return True if every in-scope registry entry for the given weeks is B-active."""
    registry = read_json(REGISTRY_PATH)
    for entry in registry["entries"]:
        if str(entry.get("lecture_key") or "") not in week_keys:
            continue
        if not (entry.get("rollout") or {}).get("in_scope"):
            continue
        if (
            entry.get("active_variant") != "B"
            or (entry.get("rollout") or {}).get("state") != "b_active"
        ):
            return False
    return True


def pending_count(week_keys: list[str]) -> int:
    """Return number of in-scope entries not yet B-active."""
    registry = read_json(REGISTRY_PATH)
    return sum(
        1
        for entry in registry["entries"]
        if str(entry.get("lecture_key") or "") in week_keys
        and (entry.get("rollout") or {}).get("in_scope")
        and entry.get("active_variant") != "B"
    )


# ── Dry-run summary ───────────────────────────────────────────────────────────

def print_dry_run_plan(week_keys: list[str]) -> None:
    registry = read_json(REGISTRY_PATH)
    entries_by_lk: dict[str, list[dict]] = {}
    for e in registry["entries"]:
        lk = str(e.get("lecture_key") or "")
        if lk in week_keys:
            entries_by_lk.setdefault(lk, []).append(e)

    for wk in week_keys:
        entries = entries_by_lk.get(wk, [])
        in_scope = [e for e in entries if (e.get("rollout") or {}).get("in_scope")]
        already_b = [e for e in in_scope if e.get("active_variant") == "B"]
        to_roll = [e for e in in_scope if e.get("active_variant") != "B"]

        log("plan", f"{wk}: {len(in_scope)} in-scope entries")
        log("plan", f"  already B-active: {len(already_b)}")
        log("plan", f"  to roll out:      {len(to_roll)}")
        for e in to_roll:
            log("plan", f"  → {e['logical_episode_id']}")
            a_src = (e.get("variants") or {}).get("A", {}).get("source_name") or ""
            if a_src:
                log("plan", f"    active A now: {a_src}")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Full A→B rollout for personlighedspsykologi episodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--week", help="Single week selector, e.g. W11L1")
    p.add_argument("--weeks", help="Comma-separated week selectors, e.g. W11L1,W11L2")
    p.add_argument("--dry-run", action="store_true",
                   help="Print planned actions without executing anything")
    p.add_argument("--skip-generate", action="store_true",
                   help="Skip generation phase (assume request logs or MP3s already present)")
    p.add_argument("--skip-download", action="store_true",
                   help="Skip download phase (assume MP3s already in output dir)")
    p.add_argument("--skip-upload", action="store_true",
                   help="Skip Drive upload phase (assume files already in Drive)")
    p.add_argument("--skip-publish", action="store_true",
                   help="Skip git commit/push and feed workflow trigger")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    week_keys: list[str] = []
    if args.week:
        week_keys.append(args.week.upper())
    if args.weeks:
        week_keys.extend(w.strip().upper() for w in args.weeks.split(",") if w.strip())
    if not week_keys:
        raise SystemExit("Provide --week or --weeks")

    dry = args.dry_run
    prefix = "[DRY RUN] " if dry else ""
    log("rollout", f"{prefix}weeks: {', '.join(week_keys)}")

    if dry:
        print_dry_run_plan(week_keys)
        print()
        phase_generate(week_keys, dry_run=True)
        print()
        phase_download(week_keys, dry_run=True)
        print()
        # Upload dry-run: lists each MP3 that would be copied (uses real output dir).
        uploaded_dry = phase_upload(week_keys, dry_run=True)
        print()
        # Register dry-run: validates LID→registry mapping for planned outputs.
        phase_register(uploaded_dry, dry_run=True)
        print()
        phase_exclude([], dry_run=True)
        print()
        phase_publish(week_keys, dry_run=True)
        print()
        phase_finalize_activation(week_keys, dry_run=True)
        return 0

    # ── Wave loop: each wave generates what it can, then immediately downloads,
    #    uploads, registers, excludes, and publishes — no waiting for the full batch.
    for attempt in range(1, GENERATE_MAX_RETRIES + 1):
        log("rollout", f"── wave {attempt}/{GENERATE_MAX_RETRIES} ──")

        # 1. Generate ─────────────────────────────────────────────────────────
        if not args.skip_generate:
            queued, mp3s_now, errors = phase_generate(week_keys, dry_run=False)
            if queued == 0 and mp3s_now == 0 and errors == 0:
                # Pure rate-limit exhaustion — no profiles available at all.
                if attempt < GENERATE_MAX_RETRIES:
                    log("rollout",
                        f"all profiles rate-limited; sleeping {GENERATE_RETRY_SLEEP/3600:.1f}h "
                        f"before wave {attempt + 1}")
                    sleep_awake(GENERATE_RETRY_SLEEP, "rollout")
                continue
        else:
            log("generate", "skipped")

        # 2. Download whatever got queued this wave ────────────────────────────
        if not args.skip_download:
            phase_download(week_keys, dry_run=False, allow_failure=True)
        else:
            log("download", "skipped")

        # 3. Collect available MP3s ───────────────────────────────────────────
        mp3s_present = {
            wk: sorted((OUTPUT_ROOT / wk).glob("*.mp3"))
            for wk in week_keys
            if (OUTPUT_ROOT / wk).exists()
        }
        total_mp3s = sum(len(v) for v in mp3s_present.values())

        if total_mp3s == 0:
            log("rollout", "wave produced no MP3s yet")
        else:
            log("rollout", f"{total_mp3s} MP3(s) available — uploading/registering/publishing")

            # 4. Upload ───────────────────────────────────────────────────────
            if not args.skip_upload:
                uploaded = phase_upload(week_keys, dry_run=False)
            else:
                log("upload", "skipped — treating local MP3s as already in Drive")
                uploaded = mp3s_present

            # 5. Register + Exclude ───────────────────────────────────────────
            updated_entries = phase_register(uploaded, dry_run=False)
            phase_exclude(updated_entries, dry_run=False)

            # 6. Publish what's new ───────────────────────────────────────────
            if updated_entries:
                if not args.skip_publish:
                    rc = phase_publish(week_keys, dry_run=False)
                    if rc != 0:
                        log("rollout", f"WARNING: publish failed (exit {rc}); will retry next wave")
                    else:
                        rc = phase_finalize_activation(week_keys, dry_run=False)
                        if rc != 0:
                            log("rollout", f"WARNING: activation finalize failed (exit {rc}); will retry next wave")
                else:
                    log("publish", "skipped")
            else:
                log("rollout", "no new registry updates this wave — skipping publish")

        # Check if everything is done ─────────────────────────────────────────
        if all_registered(week_keys):
            log("rollout", "all in-scope episodes are B-active — complete")
            break

        if args.skip_generate:
            break  # no retry loop when generation is skipped

        remaining = pending_count(week_keys)
        if attempt < GENERATE_MAX_RETRIES:
            log("rollout",
                f"{remaining} episode(s) still pending; sleeping {GENERATE_RETRY_SLEEP/3600:.1f}h "
                f"before wave {attempt + 1}")
            sleep_awake(GENERATE_RETRY_SLEEP, "rollout")
    else:
        log("rollout", "WARNING: max waves reached; some episodes may still be pending")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
