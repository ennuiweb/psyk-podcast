#!/usr/bin/env python3
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from notebooklm import NotebookLMClient
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
    output_path = Path(args.output).expanduser()
    if args.skip_existing and output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing output: {output_path}")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    sources = _load_sources(args.source, args.sources_file)
    if not sources:
        raise ValueError("Provide at least one source via --source or --sources-file")

    async with await NotebookLMClient.from_storage(args.storage) as client:
        nb = await _resolve_notebook(client, args.notebook_title, args.reuse_notebook)
        await _add_sources(
            client,
            nb.id,
            sources,
            args.source_timeout,
            skip_existing=args.reuse_notebook,
        )

        print("Generating audio overview...")
        try:
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
            error_log = output_path.with_suffix(output_path.suffix + ".request.error.json")
            error_log.write_text(
                json.dumps(
                    {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "notebook_id": nb.id,
                        "notebook_title": nb.title,
                        "output_path": str(output_path),
                        "error": str(exc),
                        "instructions": args.instructions,
                        "audio_format": args.audio_format,
                        "audio_length": args.audio_length,
                        "language": args.language,
                        "sources": sources,
                        "sources_file": args.sources_file,
                    },
                    indent=2,
                )
                + "\n",
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
                    {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "notebook_id": nb.id,
                        "notebook_title": nb.title,
                        "artifact_id": status.task_id,
                        "output_path": str(output_path),
                        "instructions": args.instructions,
                        "audio_format": args.audio_format,
                        "audio_length": args.audio_length,
                        "language": args.language,
                        "sources": sources,
                        "sources_file": args.sources_file,
                    },
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

    print(f"Podcast saved to: {output_path}")
    return 0


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
        "--source-timeout",
        type=float,
        default=300,
        help="Seconds to wait for each source to finish processing.",
    )
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
        return asyncio.run(_generate_podcast(args))
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
