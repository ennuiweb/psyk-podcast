#!/usr/bin/env python3
import argparse
import asyncio
from time import monotonic
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from notebooklm import NotebookLMClient
from notebooklm.paths import get_storage_path
from notebooklm.rpc.types import AudioFormat, AudioLength


def _parse_source_entry(entry: str) -> dict | None:
    text = entry.strip()
    if not text or text.startswith("#"):
        return None

    if text.startswith("url:"):
        return {"kind": "url", "value": text[4:].strip()}
    if text.startswith("file:"):
        return {"kind": "file", "value": text[5:].strip()}
    if text.startswith("text:"):
        payload = text[5:].strip()
        if "|" not in payload:
            raise ValueError("text: entries must be 'text:Title|Content'")
        title, content = payload.split("|", 1)
        return {"kind": "text", "title": title.strip(), "content": content.strip()}

    path = Path(text).expanduser()
    if path.exists():
        return {"kind": "file", "value": str(path)}
    return {"kind": "url", "value": text}


def _load_sources(entries: Iterable[str], sources_file: str | None) -> list[dict]:
    sources: list[dict] = []

    for entry in entries:
        parsed = _parse_source_entry(entry)
        if parsed:
            sources.append(parsed)

    if sources_file:
        path = Path(sources_file).expanduser()
        for line in path.read_text().splitlines():
            parsed = _parse_source_entry(line)
            if parsed:
                sources.append(parsed)

    return sources


def _default_profiles_paths() -> list[Path]:
    return [
        Path.cwd() / "profiles.json",
        Path(__file__).resolve().parent / "profiles.json",
    ]


def _find_profiles_path() -> Path | None:
    for candidate in _default_profiles_paths():
        if candidate.exists():
            return candidate
    return None


def _resolve_profiles_path(args: argparse.Namespace) -> Path:
    if args.profiles_file:
        profiles_path = Path(args.profiles_file).expanduser()
        if not profiles_path.exists():
            raise ValueError(f"Profiles file not found: {profiles_path}")
        return profiles_path

    profiles_path = next(
        (candidate for candidate in _default_profiles_paths() if candidate.exists()),
        None,
    )
    if profiles_path is None:
        checked = ", ".join(str(path) for path in _default_profiles_paths())
        raise ValueError(
            "Profiles file not found. Provide --profiles-file or create profiles.json "
            f"in one of: {checked}"
        )
    return profiles_path


def _load_profiles(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        raise ValueError(
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
        raise ValueError("Profiles file did not contain any valid profile entries.")
    return profiles


def _select_auto_profile(args: argparse.Namespace) -> tuple[str | None, Path | None, dict[str, str] | None]:
    if args.storage or args.profile:
        return None, None, None
    if args.profiles_file:
        profiles_path = _resolve_profiles_path(args)
    else:
        profiles_path = _find_profiles_path()
        if not profiles_path:
            return None, None, None
    try:
        profiles = _load_profiles(profiles_path)
    except ValueError as exc:
        print(f"Warning: {exc}. Falling back to default storage.")
        return None, None, None
    if "default" in profiles:
        return "default", profiles_path, profiles
    if len(profiles) == 1:
        name = next(iter(profiles))
        return name, profiles_path, profiles

    default_storage = get_storage_path().resolve()
    matches = [name for name, path in profiles.items() if Path(path).resolve() == default_storage]
    if len(matches) == 1:
        print(
            "Warning: multiple profiles found; "
            f"auto-selecting '{matches[0]}' (matches default storage path)."
        )
        return matches[0], profiles_path, profiles

    if profiles:
        name = sorted(profiles)[0]
        print(
            "Warning: multiple profiles found and no default set; "
            f"auto-selecting '{name}'. Consider adding a 'default' entry to profiles.json."
        )
        return name, profiles_path, profiles
    return None, None, None


def _resolve_auth(args: argparse.Namespace) -> tuple[str | None, dict]:
    if args.storage and args.profile:
        raise ValueError("Use either --storage or --profile, not both.")

    auth_meta: dict[str, str | None] = {
        "profile": args.profile,
        "profiles_file": None,
        "storage_path": None,
        "source": None,
    }

    if args.storage:
        storage_path = str(Path(args.storage).expanduser().resolve())
        auth_meta["storage_path"] = storage_path
        auth_meta["source"] = "storage_arg"
        return storage_path, auth_meta

    auto_profile, auto_profiles_path, auto_profiles = _select_auto_profile(args)
    if args.profile or auto_profile:
        profile_name = args.profile or auto_profile
        profiles_path = _resolve_profiles_path(args) if args.profile else auto_profiles_path
        profiles = _load_profiles(profiles_path) if args.profile else auto_profiles
        if profile_name not in profiles:
            raise ValueError(
                f"Profile '{profile_name}' not found in {profiles_path}. "
                f"Available: {', '.join(sorted(profiles))}"
            )
        storage_path = str(Path(profiles[profile_name]).expanduser().resolve())
        auth_meta["profile"] = profile_name
        auth_meta["profiles_file"] = str(profiles_path)
        auth_meta["storage_path"] = storage_path
        auth_meta["source"] = "profile" if args.profile else "auto-profile"
        return storage_path, auth_meta

    if os.environ.get("NOTEBOOKLM_AUTH_JSON"):
        auth_meta["source"] = "env"
        return None, auth_meta

    auth_meta["storage_path"] = str(get_storage_path())
    auth_meta["source"] = "default"
    return auth_meta["storage_path"], auth_meta


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "rate limit",
            "quota exceeded",
            "resource_exhausted",
            "429",
        )
    )


def _is_auth_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "authentication expired",
            "auth expired",
            "auth invalid",
            "invalid authentication",
            "not logged in",
            "run 'notebooklm login'",
            "redirected to",
        )
    )


def _order_profile_names(profiles: dict[str, str], preferred: str | None) -> list[str]:
    ordered: list[str] = []
    if preferred and preferred in profiles:
        ordered.append(preferred)
    if not preferred and "default" in profiles:
        ordered.append("default")
    for name in sorted(profiles):
        if name not in ordered:
            ordered.append(name)
    return ordered


def _parse_profile_list(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _build_auth_candidates(args: argparse.Namespace) -> list[tuple[str | None, dict]]:
    if args.storage and args.profile:
        raise ValueError("Use either --storage or --profile, not both.")

    rotate_allowed = args.rotate_on_rate_limit and not args.storage and not args.profile

    if args.storage:
        storage_path = str(Path(args.storage).expanduser().resolve())
        return [
            (
                storage_path,
                {
                    "profile": None,
                    "profiles_file": None,
                    "storage_path": storage_path,
                    "source": "storage_arg",
                },
            )
        ]

    profiles_path: Path | None = None
    profiles: dict[str, str] | None = None
    preferred: str | None = None

    if args.profile:
        profiles_path = _resolve_profiles_path(args)
        profiles = _load_profiles(profiles_path)
        if args.profile not in profiles:
            raise ValueError(
                f"Profile '{args.profile}' not found in {profiles_path}. "
                f"Available: {', '.join(sorted(profiles))}"
            )
        preferred = args.profile
    else:
        auto_profile, auto_profiles_path, auto_profiles = _select_auto_profile(args)
        if auto_profiles_path and auto_profiles:
            profiles_path = auto_profiles_path
            profiles = auto_profiles
            preferred = auto_profile

    if not profiles:
        if os.environ.get("NOTEBOOKLM_AUTH_JSON"):
            return [
                (
                    None,
                    {
                        "profile": None,
                        "profiles_file": None,
                        "storage_path": None,
                        "source": "env",
                    },
                )
            ]
        storage_path = str(get_storage_path())
        return [
            (
                storage_path,
                {
                    "profile": None,
                    "profiles_file": None,
                    "storage_path": storage_path,
                    "source": "default",
                },
            )
        ]

    exclude_profiles = _parse_profile_list(getattr(args, "exclude_profiles", None))
    if exclude_profiles:
        filtered = {name: path for name, path in profiles.items() if name not in exclude_profiles}
        if filtered:
            profiles = filtered
            if preferred in exclude_profiles:
                preferred = None
        else:
            print("Warning: all profiles excluded; ignoring --exclude-profiles.")

    if rotate_allowed:
        names = _order_profile_names(profiles, preferred)
    else:
        if preferred:
            names = [preferred]
        else:
            names = [sorted(profiles)[0]]

    candidates: list[tuple[str | None, dict]] = []
    for idx, name in enumerate(names):
        storage_path = str(Path(profiles[name]).expanduser().resolve())
        if args.profile:
            source = "profile" if idx == 0 else "profile-rotation"
        else:
            source = "auto-profile" if idx == 0 else "profile-rotation"
        candidates.append(
            (
                storage_path,
                {
                    "profile": name,
                    "profiles_file": str(profiles_path) if profiles_path else None,
                    "storage_path": storage_path,
                    "source": source,
                },
            )
        )
    return candidates


def _auth_label_from_meta(auth_meta: dict | None) -> str | None:
    if not auth_meta:
        return None
    profile = auth_meta.get("profile")
    if profile:
        return str(profile)
    storage_path = auth_meta.get("storage_path")
    if storage_path:
        return Path(str(storage_path)).stem
    return None


def _load_request_auth(output_path: Path) -> dict | None:
    log_path = output_path.with_suffix(output_path.suffix + ".request.json")
    if not log_path.exists():
        return None
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    auth = payload.get("auth")
    return auth if isinstance(auth, dict) else None


def _ensure_unique_output_path(output_path: Path, auth_meta: dict) -> Path:
    label = _auth_label_from_meta(auth_meta)
    if not output_path.exists() or not label:
        return output_path

    existing_label = _auth_label_from_meta(_load_request_auth(output_path))
    if existing_label == label:
        return output_path

    candidate = output_path.with_name(f"{output_path.stem} [{label}]{output_path.suffix}")
    if not candidate.exists():
        print(f"Output collision detected, using: {candidate}")
        return candidate
    if _auth_label_from_meta(_load_request_auth(candidate)) == label:
        return candidate

    counter = 2
    while True:
        candidate = output_path.with_name(
            f"{output_path.stem} [{label}-{counter}]{output_path.suffix}"
        )
        if not candidate.exists():
            print(f"Output collision detected, using: {candidate}")
            return candidate
        if _auth_label_from_meta(_load_request_auth(candidate)) == label:
            return candidate
        counter += 1


def _build_request_payload(
    *,
    created_at: str,
    notebook_id: str,
    notebook_title: str,
    artifact_id: str | None,
    output_path: Path,
    args: argparse.Namespace,
    sources: list[dict],
    auth_meta: dict,
) -> dict:
    return {
        "created_at": created_at,
        "notebook_id": notebook_id,
        "notebook_title": notebook_title,
        "artifact_id": artifact_id,
        "output_path": str(output_path),
        "instructions": args.instructions,
        "audio_format": args.audio_format,
        "audio_length": args.audio_length,
        "language": args.language,
        "sources": sources,
        "sources_file": args.sources_file,
        "auth": auth_meta,
    }


def _print_profiles(args: argparse.Namespace) -> None:
    profiles_path = _resolve_profiles_path(args)
    profiles = _load_profiles(profiles_path)
    print(f"Profiles file: {profiles_path}")
    for name in sorted(profiles):
        print(f"{name}: {profiles[name]}")


def _audio_format(value: str) -> AudioFormat:
    mapping = {
        "deep-dive": AudioFormat.DEEP_DIVE,
        "brief": AudioFormat.BRIEF,
        "critique": AudioFormat.CRITIQUE,
        "debate": AudioFormat.DEBATE,
    }
    return mapping[value]


def _audio_length(value: str) -> AudioLength:
    mapping = {
        "short": AudioLength.SHORT,
        "default": AudioLength.DEFAULT,
        "long": AudioLength.LONG,
    }
    return mapping[value]


async def _resolve_notebook(client: NotebookLMClient, title: str, reuse: bool):
    if reuse:
        notebooks = await client.notebooks.list()
        for nb in notebooks:
            if nb.title == title:
                print(f"Reusing notebook: {nb.title} ({nb.id})")
                return nb
    nb = await client.notebooks.create(title)
    print(f"Created notebook: {nb.title} ({nb.id})")
    return nb


def _source_key(source: dict) -> tuple[str, str] | None:
    kind = source.get("kind")
    if kind == "url":
        value = source.get("value", "").strip()
        return ("url", value) if value else None
    if kind == "file":
        value = source.get("value", "").strip()
        if not value:
            return None
        name = Path(value).name
        return ("title", name.lower()) if name else None
    if kind == "text":
        title = source.get("title", "").strip()
        return ("title", title.lower()) if title else None
    return None


async def _existing_source_keys(client: NotebookLMClient, notebook_id: str) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for src in await client.sources.list(notebook_id):
        if src.title:
            keys.add(("title", src.title.strip().lower()))
        if src.url:
            keys.add(("url", src.url.strip()))
    return keys


async def _source_index(
    client: NotebookLMClient, notebook_id: str
) -> dict[tuple[str, str], Source]:
    index: dict[tuple[str, str], Source] = {}
    for src in await client.sources.list(notebook_id):
        if src.title:
            index[("title", src.title.strip().lower())] = src
        if src.url:
            index[("url", src.url.strip())] = src
    return index


async def _ensure_sources_ready(
    client: NotebookLMClient,
    notebook_id: str,
    sources: list[dict],
    *,
    timeout: float,
    poll_interval: float = 5.0,
) -> None:
    expected_keys = {key for source in sources if (key := _source_key(source)) is not None}
    if not expected_keys:
        return

    start = monotonic()
    saw_any_source = False
    while True:
        index = await _source_index(client, notebook_id)
        if index:
            saw_any_source = True
        missing = expected_keys - set(index.keys())
        not_ready = [
            src for key, src in index.items() if key in expected_keys and not src.is_ready
        ]
        if not missing and not not_ready:
            return

        elapsed = monotonic() - start
        if elapsed >= timeout:
            break

        if missing:
            missing_labels = ", ".join(sorted(key[1] for key in missing))
            print(f"Waiting for missing sources: {missing_labels}")
        if not_ready:
            pending_labels = ", ".join(
                sorted(
                    src.title or src.url or src.id
                    for src in not_ready
                )
            )
            print(f"Waiting for sources to be ready: {pending_labels}")

        await asyncio.sleep(poll_interval)

    if missing and saw_any_source:
        print("Re-adding missing sources before generation.")
        for source in sources:
            key = _source_key(source)
            if not key or key not in missing:
                continue
            kind = source["kind"]
            if kind == "url":
                url = source["value"]
                print(f"Re-adding URL: {url}")
                await client.sources.add_url(notebook_id, url, wait=True, wait_timeout=timeout)
            elif kind == "file":
                file_path = Path(source["value"]).expanduser().resolve()
                print(f"Re-adding file: {file_path}")
                await client.sources.add_file(notebook_id, file_path, wait=True, wait_timeout=timeout)
            elif kind == "text":
                title = source["title"]
                content = source["content"]
                print(f"Re-adding text: {title}")
                await client.sources.add_text(
                    notebook_id, title, content, wait=True, wait_timeout=timeout
                )

    index = await _source_index(client, notebook_id)
    missing = expected_keys - set(index.keys())
    not_ready = [
        src for key, src in index.items() if key in expected_keys and not src.is_ready
    ]
    if missing or not_ready:
        missing_labels = ", ".join(sorted(key[1] for key in missing)) if missing else "none"
        if missing and not saw_any_source:
            raise RuntimeError(
                "Source listing returned empty while waiting for uploads. "
                "Unable to verify readiness; retry later."
            )
        raise RuntimeError(
            "Sources not ready after waiting. "
            f"Missing: {missing_labels}. "
            f"Not ready: {len(not_ready)}"
        )


async def _add_sources(
    client: NotebookLMClient,
    notebook_id: str,
    sources: list[dict],
    timeout: float,
    *,
    skip_existing: bool,
):
    if not sources:
        raise ValueError("No sources provided")

    existing_keys = await _existing_source_keys(client, notebook_id) if skip_existing else set()

    for idx, source in enumerate(sources, start=1):
        if skip_existing:
            key = _source_key(source)
            if key and key in existing_keys:
                print(f"[{idx}/{len(sources)}] Skipping existing source: {key[1]}")
                continue

        kind = source["kind"]
        if kind == "url":
            url = source["value"]
            print(f"[{idx}/{len(sources)}] Adding URL: {url}")
            await client.sources.add_url(notebook_id, url, wait=True, wait_timeout=timeout)
            if skip_existing:
                existing_keys.add(("url", url.strip()))
        elif kind == "file":
            file_path = Path(source["value"]).expanduser().resolve()
            print(f"[{idx}/{len(sources)}] Adding file: {file_path}")
            await client.sources.add_file(notebook_id, file_path, wait=True, wait_timeout=timeout)
            if skip_existing:
                existing_keys.add(("title", file_path.name.lower()))
        elif kind == "text":
            title = source["title"]
            content = source["content"]
            print(f"[{idx}/{len(sources)}] Adding text: {title}")
            await client.sources.add_text(notebook_id, title, content, wait=True, wait_timeout=timeout)
            if skip_existing:
                existing_keys.add(("title", title.strip().lower()))
        else:
            raise ValueError(f"Unknown source kind: {kind}")


async def _generate_audio_with_retry(
    client: NotebookLMClient,
    notebook_id: str,
    *,
    instructions: str,
    audio_format: AudioFormat,
    audio_length: AudioLength,
    language: str,
    retries: int,
    backoff: float,
):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            status = await client.artifacts.generate_audio(
                notebook_id,
                instructions=instructions,
                audio_format=audio_format,
                audio_length=audio_length,
                language=language,
            )
            if not status.task_id:
                if getattr(status, "error", None):
                    raise RuntimeError(status.error)
                raise RuntimeError("No artifact id returned from generate_audio")
            return status
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = backoff * (2**attempt)
            print(
                f"Generate audio failed (attempt {attempt + 1}/{retries + 1}): {exc}. "
                f"Retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    raise last_exc or RuntimeError("generate_audio failed")


async def _generate_podcast(args: argparse.Namespace) -> int:
    base_output_path = Path(args.output).expanduser()
    sources = _load_sources(args.source, args.sources_file)
    if not sources:
        raise ValueError("Provide at least one source via --source or --sources-file")

    candidates = _build_auth_candidates(args)
    rotation_attempts: list[dict] = []
    last_exc: Exception | None = None
    last_output_path: Path | None = None
    last_auth_meta: dict | None = None

    for idx, (storage_path, auth_meta) in enumerate(candidates, start=1):
        output_path = _ensure_unique_output_path(base_output_path, auth_meta)
        last_output_path = output_path
        last_auth_meta = auth_meta
        if args.skip_existing and output_path.exists() and output_path.stat().st_size > 0:
            print(f"Skipping existing output: {output_path}")
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)

        label = _auth_label_from_meta(auth_meta)
        if len(candidates) > 1:
            prefix = f"[{idx}/{len(candidates)}]"
            if label:
                print(f"{prefix} Using profile: {label}")
            else:
                print(f"{prefix} Using auth source: {auth_meta.get('source')}")

        try:
            async with await NotebookLMClient.from_storage(storage_path) as client:
                notebook_title = args.notebook_title
                if (
                    args.append_profile_to_notebook_title
                    and len(candidates) > 1
                    and label
                    and f"[{label}]" not in notebook_title
                ):
                    notebook_title = f"{notebook_title} [{label}]"

                nb = await _resolve_notebook(client, notebook_title, args.reuse_notebook)
                await _add_sources(
                    client,
                    nb.id,
                    sources,
                    args.source_timeout,
                    skip_existing=args.reuse_notebook,
                )
                if args.ensure_sources_ready:
                    await _ensure_sources_ready(
                        client,
                        nb.id,
                        sources,
                        timeout=args.source_timeout,
                    )

                print("Generating audio overview...")
                status = await _generate_audio_with_retry(
                    client,
                    nb.id,
                    instructions=args.instructions,
                    audio_format=_audio_format(args.audio_format),
                    audio_length=_audio_length(args.audio_length),
                    language=args.language,
                    retries=args.artifact_retries,
                    backoff=args.artifact_retry_backoff,
                )
        except Exception as exc:
            last_exc = exc
            retryable = args.rotate_on_rate_limit and (
                _is_rate_limit_error(exc) or _is_auth_error(exc)
            )
            if retryable and idx < len(candidates):
                rotation_attempts.append(
                    {
                        "profile": auth_meta.get("profile"),
                        "storage_path": auth_meta.get("storage_path"),
                        "source": auth_meta.get("source"),
                        "error": str(exc),
                    }
                )
                reason = "rate limit" if _is_rate_limit_error(exc) else "auth"
                print(
                    f"Generation failed due to {reason} on "
                    f"{label or auth_meta.get('source')}; trying next profile."
                )
                continue

            error_log = output_path.with_suffix(output_path.suffix + ".request.error.json")
            payload = _build_request_payload(
                created_at=datetime.now(timezone.utc).isoformat(),
                notebook_id=nb.id if "nb" in locals() else "",
                notebook_title=nb.title if "nb" in locals() else "",
                artifact_id=None,
                output_path=output_path,
                args=args,
                sources=sources,
                auth_meta=auth_meta,
            )
            if rotation_attempts:
                payload["rotation_attempts"] = rotation_attempts
            payload["error"] = str(exc)
            error_log.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Generation failed: {exc}")
            print(f"Wrote error log: {error_log}")
            return 2

        if not args.wait:
            print(
                "Generation started (non-blocking). "
                f"notebook_id={nb.id} artifact_id={status.task_id}"
            )
            print(
                "To wait later:\n"
                f"  notebooklm artifact wait {status.task_id} -n {nb.id}\n"
                f"  notebooklm download audio {output_path} -a {status.task_id} -n {nb.id}"
            )

            request_log = output_path.with_suffix(output_path.suffix + ".request.json")
            request_log.write_text(
                json.dumps(
                    _build_request_payload(
                        created_at=datetime.now(timezone.utc).isoformat(),
                        notebook_id=nb.id,
                        notebook_title=nb.title,
                        artifact_id=status.task_id,
                        output_path=output_path,
                        args=args,
                        sources=sources,
                        auth_meta=auth_meta,
                    ),
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return 0

        final = await client.artifacts.wait_for_completion(
            nb.id,
            status.task_id,
            timeout=args.generation_timeout,
            initial_interval=args.initial_interval,
        )

        if not final.is_complete:
            print(f"Generation failed: status={final.status} error={final.error}")
            return 2

        await client.artifacts.download_audio(
            nb.id,
            str(output_path),
            artifact_id=final.task_id,
        )

        request_log = output_path.with_suffix(output_path.suffix + ".request.json")
        request_log.write_text(
            json.dumps(
                _build_request_payload(
                    created_at=datetime.now(timezone.utc).isoformat(),
                    notebook_id=nb.id,
                    notebook_title=nb.title,
                    artifact_id=final.task_id,
                    output_path=output_path,
                    args=args,
                    sources=sources,
                    auth_meta=auth_meta,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print(f"Podcast saved to: {output_path}")
        return 0

    if last_exc and last_output_path and last_auth_meta:
        error_log = last_output_path.with_suffix(
            last_output_path.suffix + ".request.error.json"
        )
        payload = _build_request_payload(
            created_at=datetime.now(timezone.utc).isoformat(),
            notebook_id="",
            notebook_title="",
            artifact_id=None,
            output_path=last_output_path,
            args=args,
            sources=sources,
            auth_meta=last_auth_meta,
        )
        if rotation_attempts:
            payload["rotation_attempts"] = rotation_attempts
        payload["error"] = str(last_exc)
        error_log.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Generation failed: {last_exc}")
        print(f"Wrote error log: {error_log}")
        return 2

    return 2
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a NotebookLM podcast from sources.")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source entry (URL or file path). Can be repeated.",
    )
    parser.add_argument(
        "--sources-file",
        help="Path to a sources file (one entry per line).",
    )
    parser.add_argument(
        "--notebook-title",
        default="Auto Podcast",
        help="Notebook title to create or reuse.",
    )
    parser.add_argument(
        "--reuse-notebook",
        action="store_true",
        help="Reuse an existing notebook with the same title if found.",
    )
    parser.add_argument(
        "--instructions",
        default="make it engaging",
        help="Generation instructions passed to NotebookLM.",
    )
    parser.add_argument(
        "--audio-format",
        choices=["deep-dive", "brief", "critique", "debate"],
        default="deep-dive",
        help="Audio overview format.",
    )
    parser.add_argument(
        "--audio-length",
        choices=["short", "default", "long"],
        default="default",
        help="Audio overview length.",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Output language code.",
    )
    parser.add_argument(
        "--output",
        default="output/podcast.mp3",
        help="Output path for the MP3 file.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip generation if the output file already exists.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for generation to complete and download the audio.",
    )
    parser.add_argument(
        "--storage",
        help="Path to storage_state.json. Defaults to NotebookLM config path.",
    )
    parser.add_argument(
        "--profile",
        help="Profile name from profiles.json (use instead of --storage).",
    )
    parser.add_argument(
        "--profiles-file",
        help="Path to profiles.json (default: ./profiles.json or script directory).",
    )
    parser.add_argument(
        "--exclude-profiles",
        help="Comma-separated profile names to skip when rotating.",
    )
    parser.add_argument(
        "--no-rotate-on-rate-limit",
        dest="rotate_on_rate_limit",
        action="store_false",
        help="Disable rotating profiles on rate-limit/auth errors.",
    )
    parser.set_defaults(rotate_on_rate_limit=True)
    parser.add_argument(
        "--no-append-profile-to-notebook-title",
        dest="append_profile_to_notebook_title",
        action="store_false",
        help="Disable appending the profile label to notebook titles when rotating.",
    )
    parser.set_defaults(append_profile_to_notebook_title=True)
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit.",
    )
    parser.add_argument(
        "--source-timeout",
        type=float,
        default=300,
        help="Seconds to wait for each source to finish processing.",
    )
    parser.add_argument(
        "--no-ensure-sources-ready",
        dest="ensure_sources_ready",
        action="store_false",
        help="Disable waiting for sources to appear and become ready before generation.",
    )
    parser.set_defaults(ensure_sources_ready=True)
    parser.add_argument(
        "--generation-timeout",
        type=float,
        default=900,
        help="Seconds to wait for podcast generation.",
    )
    parser.add_argument(
        "--artifact-retries",
        type=int,
        default=0,
        help="Number of retries for artifact generation (default: 0).",
    )
    parser.add_argument(
        "--artifact-retry-backoff",
        type=float,
        default=5.0,
        help="Base backoff in seconds between artifact retries.",
    )
    parser.add_argument(
        "--initial-interval",
        type=float,
        default=5,
        help="Initial polling interval in seconds during generation.",
    )
    parser.add_argument(
        "--poll-interval",
        dest="initial_interval",
        type=float,
        help="Deprecated (use --initial-interval).",
    )

    args = parser.parse_args()
    try:
        if args.list_profiles:
            _print_profiles(args)
            return 0
        return asyncio.run(_generate_podcast(args))
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
