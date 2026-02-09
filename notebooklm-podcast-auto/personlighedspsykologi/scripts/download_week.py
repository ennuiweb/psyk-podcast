#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def parse_weeks(week: str | None, weeks: str | None) -> list[str]:
    if not week and not weeks:
        raise SystemExit("Provide --week or --weeks.")
    items: list[str] = []
    if week:
        items.append(week)
    if weeks:
        items.extend(part.strip() for part in weeks.split(",") if part.strip())
    if not items:
        raise SystemExit("No valid weeks provided.")
    return items


def parse_content_types(value: str | None) -> list[str]:
    if not value:
        return ["audio"]
    allowed = {"audio", "infographic"}
    items: list[str] = []
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if item not in allowed:
            raise SystemExit(
                f"Unknown content type '{item}'. Allowed: {', '.join(sorted(allowed))}."
            )
        if item not in items:
            items.append(item)
    if not items:
        raise SystemExit("No valid content types provided.")
    return items


def find_week_dirs(root: Path, week: str) -> list[Path]:
    week_upper = week.upper()
    if not root.exists():
        return []
    exact: list[Path] = []
    prefix: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.upper() == week_upper:
            exact.append(entry)
            continue
        if entry.name.upper().startswith(week_upper):
            prefix.append(entry)
        for child in entry.iterdir():
            if child.is_dir() and child.name.upper() == week_upper:
                exact.append(child)
    if exact:
        return exact
    return sorted(prefix, key=lambda path: path.name)


def default_profiles_paths(repo_root: Path) -> list[Path]:
    return [
        Path.cwd() / "profiles.json",
        repo_root / "notebooklm-podcast-auto" / "profiles.json",
    ]


def resolve_profiles_path(repo_root: Path, profiles_file: str | None) -> Path | None:
    if profiles_file:
        path = Path(profiles_file).expanduser()
        if not path.exists():
            raise SystemExit(f"Profiles file not found: {path}")
        return path

    for candidate in default_profiles_paths(repo_root):
        if candidate.exists():
            return candidate
    return None


def load_profiles(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Warning: invalid profiles file {path}: {exc}")
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        raise SystemExit(
            "Profiles file must be a JSON object of {profile_name: storage_path} "
            "or {\"profiles\": {...}}"
        )

    profiles: dict[str, str] = {}
    base_dir = path.parent
    for name, value in raw.items():
        if not isinstance(name, str):
            continue
        if value is None:
            continue
        raw_path = Path(str(value)).expanduser()
        if not raw_path.is_absolute():
            raw_path = (base_dir / raw_path).resolve()
        else:
            raw_path = raw_path.resolve()
        profiles[name] = str(raw_path)

    if not profiles:
        raise SystemExit("Profiles file did not contain any valid profile entries.")
    return profiles


def resolve_storage_path(
    repo_root: Path,
    *,
    storage: str | None,
    profile: str | None,
    profiles_file: str | None,
    log_auth: dict | None,
) -> tuple[str | None, str]:
    if storage and profile:
        raise SystemExit("Use either --storage or --profile, not both.")

    if storage:
        return str(Path(storage).expanduser()), "cli:storage"

    if profile:
        profiles_path = resolve_profiles_path(repo_root, profiles_file)
        if not profiles_path:
            raise SystemExit("Profiles file not found. Provide --profiles-file.")
        profiles = load_profiles(profiles_path)
        if profile not in profiles:
            raise SystemExit(
                f"Profile '{profile}' not found in {profiles_path}. "
                f"Available: {', '.join(sorted(profiles))}"
            )
        return profiles[profile], "cli:profile"

    if log_auth:
        storage_path = log_auth.get("storage_path")
        if storage_path:
            return str(Path(str(storage_path)).expanduser()), "log:storage"
        profile_name = log_auth.get("profile")
        profiles_path = log_auth.get("profiles_file")
        if profile_name and profiles_path:
            profiles_path = Path(str(profiles_path)).expanduser()
            if profiles_path.exists():
                profiles = load_profiles(profiles_path)
                if profile_name in profiles:
                    return profiles[profile_name], "log:profile"

    return None, "default"


def resolve_profile_slug(profile: str | None, storage: str | None) -> str | None:
    if profile:
        return profile
    if storage:
        return Path(storage).stem
    return None


def apply_profile_subdir(output_root: Path, slug: str | None, enabled: bool) -> Path:
    if not enabled or not slug:
        return output_root
    safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("_")
    return output_root / (safe_slug or slug)


def default_storage_path() -> Path:
    home_override = os.environ.get("NOTEBOOKLM_HOME")
    if home_override:
        return Path(home_override).expanduser() / "storage_state.json"
    return Path.home() / ".notebooklm" / "storage_state.json"


def collect_storage_candidates(
    repo_root: Path,
    *,
    storage: str | None,
    profile: str | None,
    profiles_file: str | None,
    log_auth: dict | None,
) -> list[tuple[str | None, str]]:
    candidates: list[tuple[str | None, str]] = []
    seen: set[str | None] = set()

    def add(path: str | None, source: str) -> None:
        if path in seen:
            return
        if path and not Path(path).expanduser().exists():
            return
        seen.add(path)
        candidates.append((path, source))

    if storage or profile:
        path, source = resolve_storage_path(
            repo_root,
            storage=storage,
            profile=profile,
            profiles_file=profiles_file,
            log_auth=None,
        )
        add(path, source)

    if log_auth:
        path, source = resolve_storage_path(
            repo_root,
            storage=None,
            profile=None,
            profiles_file=None,
            log_auth=log_auth,
        )
        add(path, source)

    profiles_path = resolve_profiles_path(repo_root, profiles_file)
    if profiles_path:
        for name, path in load_profiles(profiles_path).items():
            add(path, f"profiles:{name}")

    fallback_path = default_storage_path()
    if fallback_path.exists():
        add(str(fallback_path), "default")

    return candidates


def run_cmd(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        output = (result.stdout or "") + (result.stderr or "")
        return True, output
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(cmd)}")
        output = (exc.stdout or "") + (exc.stderr or "")
        if output.strip():
            print(output.strip())
        else:
            print(f"Error: {exc}")
        return False, output


def build_cli_cmd(notebooklm: Path, storage_path: str | None, args: list[str]) -> list[str]:
    cmd = [str(notebooklm)]
    if storage_path:
        cmd.extend(["--storage", storage_path])
    cmd.extend(args)
    return cmd


def archive_request_log(log_path: Path) -> None:
    name = log_path.name
    if name.endswith(".request.json"):
        archived = log_path.with_name(name[: -len(".request.json")] + ".request.done.json")
    else:
        archived = log_path.with_suffix(log_path.suffix + ".done")
    if archived.exists():
        archived.unlink()
        print(f"Deleted existing archive: {archived}")
    if log_path.exists():
        log_path.unlink()
        print(f"Deleted request log: {log_path}")


def is_auth_error(output: str) -> bool:
    lowered = output.lower()
    return "authentication expired" in lowered or "received html instead of media file" in lowered


def is_timeout_error(output: str) -> bool:
    lowered = output.lower()
    return "timeout" in lowered or "timed out" in lowered


def parse_artifact_list(output: str) -> dict[str, dict]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {}
    items = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    by_id: dict[str, dict] = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item
    return by_id


def fetch_artifact_status(
    notebooklm: Path,
    storage_path: str | None,
    notebook_id: str,
    artifact_id: str,
) -> tuple[bool, str | None]:
    cmd = build_cli_cmd(
        notebooklm,
        storage_path,
        ["artifact", "list", "-n", notebook_id, "--json"],
    )
    ok, output = run_cmd(cmd)
    if not ok:
        return False, None
    artifacts = parse_artifact_list(output)
    item = artifacts.get(artifact_id)
    if not item:
        return True, None
    status = item.get("status") or item.get("state")
    return True, str(status) if status is not None else None


def wait_and_download(
    notebooklm: Path,
    artifact_id: str,
    notebook_id: str,
    artifact_type: str,
    output_path: Path,
    timeout: int | None,
    interval: int | None,
    storage_path: str | None,
) -> tuple[bool, str]:
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing: {output_path}")
        return True, "skipped"

    wait_cmd = build_cli_cmd(
        notebooklm,
        storage_path,
        ["artifact", "wait", artifact_id, "-n", notebook_id],
    )
    if timeout is not None:
        wait_cmd.extend(["--timeout", str(timeout)])
    if interval is not None:
        wait_cmd.extend(["--interval", str(interval)])

    ok, output = run_cmd(wait_cmd)
    if not ok:
        return False, "wait"

    download_cmd = build_cli_cmd(
        notebooklm,
        storage_path,
        [
            "download",
            artifact_type,
            str(output_path),
            "-a",
            artifact_id,
            "-n",
            notebook_id,
        ],
    )
    ok, output = run_cmd(download_cmd)
    if not ok:
        if is_auth_error(output):
            return False, "auth"
        return False, "download"
    return True, "ok"


def find_repo_root(start: Path) -> Path:
    for candidate in [start] + list(start.parents):
        if (candidate / "requirements.txt").exists() and (candidate / "shows").exists():
            return candidate
    return start


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait and download NotebookLM artifacts for a week from request logs."
    )
    parser.add_argument(
        "--week",
        help="Single week label, e.g. W01L1 (or W01 to include all W01L* folders).",
    )
    parser.add_argument(
        "--weeks",
        help="Comma-separated week labels, e.g. W01,W02 (expands to W01L*, W02L*).",
    )
    parser.add_argument(
        "--content-types",
        help="Comma-separated content types to download (audio, infographic). Default: audio.",
    )
    parser.add_argument(
        "--output-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing W## output folders.",
    )
    parser.add_argument(
        "--output-profile-subdir",
        action="store_true",
        help="If set, read outputs from a profile-based subdirectory.",
    )
    parser.add_argument(
        "--notebooklm",
        default="notebooklm-podcast-auto/.venv/bin/notebooklm",
        help="Path to the notebooklm CLI.",
    )
    parser.add_argument(
        "--storage",
        help="Path to storage_state.json (overrides per-log auth).",
    )
    parser.add_argument(
        "--profile",
        help="Profile name from profiles.json (overrides per-log auth).",
    )
    parser.add_argument(
        "--profiles-file",
        help="Path to profiles.json (used with --profile).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Seconds to wait for completion (default: 1800).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Polling interval in seconds (default: 15).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without waiting/downloading.",
    )
    parser.add_argument(
        "--archive-requests",
        dest="archive_requests",
        action="store_true",
        default=True,
        help="Delete request logs after successful download (default).",
    )
    parser.add_argument(
        "--no-archive-requests",
        dest="archive_requests",
        action="store_false",
        help="Keep request logs after successful download.",
    )
    args = parser.parse_args()
    content_types = parse_content_types(args.content_types)

    repo_root = find_repo_root(Path(__file__).resolve())
    output_root = repo_root / args.output_root
    if args.output_profile_subdir:
        profile_slug = resolve_profile_slug(args.profile, args.storage)
        if not profile_slug:
            raise SystemExit("--output-profile-subdir requires --profile or --storage.")
        output_root = apply_profile_subdir(output_root, profile_slug, True)
    notebooklm = repo_root / args.notebooklm

    week_inputs = parse_weeks(args.week, args.weeks)
    extra_roots = [
        repo_root / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output",
        repo_root / "shows" / "personlighedspsykologi" / "output",
    ]
    roots = []
    seen_roots: set[Path] = set()
    for root in [output_root, *extra_roots]:
        if root not in seen_roots:
            seen_roots.add(root)
            roots.append(root)

    for week_input in week_inputs:
        week_dirs: list[Path] = []
        for root in roots:
            week_dirs.extend(find_week_dirs(root, week_input))
        if not week_dirs:
            print(f"No output folder found for {week_input} under: {', '.join(str(r) for r in roots)}")
            continue

        request_logs_set: set[Path] = set()
        error_logs_set: set[Path] = set()
        for week_dir in week_dirs:
            request_logs_set.update(week_dir.glob("*.request.json"))
            error_logs_set.update(week_dir.glob("*.request.error.json"))
        request_logs = sorted(request_logs_set)
        error_logs = sorted(error_logs_set)

        if not request_logs:
            if error_logs:
                print(f"No request logs found for {week_input} (found error logs).")
                for log_path in error_logs:
                    print(f"- {log_path}")
            else:
                print(f"No request logs found for {week_input}")
            continue

        print(f"## {week_input.upper()}")
        for log_path in request_logs:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            notebook_id = payload.get("notebook_id")
            artifact_id = payload.get("artifact_id")
            output_path = payload.get("output_path")
            artifact_type = payload.get("artifact_type") or "audio"
            log_auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else None
            if not (notebook_id and artifact_id and output_path):
                print(f"Skipping malformed log: {log_path}")
                continue
            if artifact_type not in content_types:
                continue
            if artifact_type not in {"audio", "infographic"}:
                print(f"Skipping unsupported artifact type '{artifact_type}' in {log_path}")
                continue

            output_file = Path(output_path)
            candidates = collect_storage_candidates(
                repo_root,
                storage=args.storage,
                profile=args.profile,
                profiles_file=args.profiles_file,
                log_auth=log_auth,
            )
            if not candidates:
                print("No storage candidates found. Run 'notebooklm login' first.")
                continue
            if args.dry_run:
                print(f"WAIT: {artifact_id} (notebook {notebook_id})")
                print(f"DOWNLOAD ({artifact_type}): {output_file}")
                for storage_path, auth_source in candidates:
                    print(f"AUTH: {auth_source} -> {storage_path or 'default'}")
                continue

            success = False
            archive_ok = False
            for storage_path, auth_source in candidates:
                if storage_path and not Path(storage_path).expanduser().exists():
                    print(f"Warning: storage file not found: {storage_path}")
                    continue
                print(
                    f"Waiting for {artifact_id} (notebook {notebook_id}) "
                    f"using {auth_source}..."
                )
                status_ok, status = fetch_artifact_status(
                    notebooklm,
                    storage_path,
                    notebook_id,
                    artifact_id,
                )
                if status_ok and status is None:
                    print("Warning: artifact not found in list; proceeding to wait anyway.")
                if status_ok and status is not None:
                    print(f"Artifact status before wait: {status}")
                    if status.upper() in {"FAILED", "ERROR"}:
                        print("Artifact already failed; skipping download.")
                        success = True
                        archive_ok = False
                        break
                ok, reason = wait_and_download(
                    notebooklm,
                    artifact_id,
                    notebook_id,
                    artifact_type,
                    output_file,
                    args.timeout,
                    args.interval,
                    storage_path,
                )
                if ok:
                    success = True
                    archive_ok = reason in {"ok", "skipped"}
                    break
                if reason == "wait":
                    print("Wait failed; skipping remaining auth candidates for this artifact.")
                    break
                if reason != "auth":
                    break
                print(f"Auth failed with {auth_source}, trying next profile...")

            if not success:
                print(f"Failed to download after trying {len(candidates)} auth option(s).")
            elif args.archive_requests and archive_ok:
                archive_request_log(log_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
