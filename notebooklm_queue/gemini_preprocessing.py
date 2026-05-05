"""Gemini JSON generation helpers for Source Intelligence preprocessing."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_GEMINI_PREPROCESSING_MODEL = "gemini-3.1-pro-preview"
GEMINI_FILE_POLL_INTERVAL_SECONDS = 2
GEMINI_FILE_POLL_TIMEOUT_SECONDS = 180
GEMINI_RATE_LIMIT_RETRY_SECONDS = 60
DEFAULT_MAX_INLINE_SOURCE_CHARS = 16000
DEFAULT_MAX_OUTPUT_TOKENS = 8192


class GeminiPreprocessingError(RuntimeError):
    """Base error for Gemini preprocessing failures."""


class GeminiPreprocessingInputError(GeminiPreprocessingError):
    """Raised for invalid local inputs or file upload problems."""


class GeminiPreprocessingGenerationError(GeminiPreprocessingError):
    """Raised when Gemini returns an unusable response."""


@dataclass(frozen=True)
class GeminiUploadedFile:
    name: str
    uri: str
    mime_type: str


@dataclass(frozen=True)
class GeminiPreprocessingBackend:
    provider: str
    client: object
    support: object
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL


def gemini_api_key() -> str:
    env_key = str(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if env_key:
        return env_key
    return _gemini_api_key_from_local_secret_store()


def _secret_store_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = str(os.environ.get("OSKAR_MEMORY_BRIDGE_SECRETS_FILE") or "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path.home() / ".config" / "oskar-memory-bridge" / "secrets.json",
            Path("/etc/oskar-memory-bridge-secrets.json"),
            Path("/etc/oskar-memory-bridge/secrets.json"),
        ]
    )
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def _gemini_api_key_from_local_secret_store() -> str:
    for path in _secret_store_candidates():
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        google = payload.get("google")
        gemini = google.get("gemini") if isinstance(google, dict) else None
        if not isinstance(gemini, dict):
            continue
        api_key = str(gemini.get("api_key") or "").strip()
        if api_key:
            return api_key
    return ""


def has_gemini_api_key() -> bool:
    return bool(gemini_api_key())


def make_gemini_backend(*, model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL) -> GeminiPreprocessingBackend:
    api_key = gemini_api_key()
    if not api_key:
        raise GeminiPreprocessingInputError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise GeminiPreprocessingInputError("google-genai package not installed - pip install google-genai") from exc
    return GeminiPreprocessingBackend(
        provider="gemini",
        client=genai.Client(api_key=api_key),
        support=genai_types,
        model=model,
    )


def _infer_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".txt", ".md"}:
        return "text/plain"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


def stage_upload_path(path: Path) -> tuple[Path, Path]:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "source"
    staged_dir = Path(tempfile.mkdtemp(prefix="gemini-preprocess-upload-"))
    staged_path = staged_dir / f"{safe_stem}{path.suffix.lower() or '.bin'}"
    shutil.copy2(path, staged_path)
    return staged_path, staged_dir


def wait_for_gemini_file_ready(client: object, uploaded: object, path: Path) -> GeminiUploadedFile:
    file_name = str(getattr(uploaded, "name", "") or "").strip()
    if not file_name:
        raise GeminiPreprocessingInputError(f"Gemini upload returned no file name for {path.name}")

    def ready_file(file_obj: object) -> GeminiUploadedFile:
        file_uri = str(getattr(file_obj, "uri", "") or "").strip()
        mime_type = str(getattr(file_obj, "mime_type", "") or "").strip() or _infer_mime_type(path)
        if not file_uri:
            raise GeminiPreprocessingInputError(f"Gemini upload returned no URI for {path.name}")
        return GeminiUploadedFile(name=file_name, uri=file_uri, mime_type=mime_type)

    state = getattr(uploaded, "state", None)
    if state is None:
        return ready_file(uploaded)

    deadline = time.time() + GEMINI_FILE_POLL_TIMEOUT_SECONDS
    latest = uploaded
    while True:
        state = getattr(latest, "state", None)
        if state is None:
            return ready_file(latest)
        if str(state).endswith("ACTIVE"):
            return ready_file(latest)
        if str(state).endswith("FAILED"):
            error = getattr(latest, "error", None)
            detail = f": {error}" if error else ""
            raise GeminiPreprocessingInputError(f"Gemini could not process {path.name}{detail}")
        if time.time() >= deadline:
            raise GeminiPreprocessingInputError(f"Gemini timed out while preparing {path.name}")
        time.sleep(GEMINI_FILE_POLL_INTERVAL_SECONDS)
        try:
            latest = client.files.get(name=file_name)
        except Exception as exc:
            raise GeminiPreprocessingInputError(f"failed to poll Gemini file state for {path.name}: {exc}") from exc


def delete_gemini_uploaded_files(client: object, uploaded_files: list[GeminiUploadedFile]) -> None:
    for uploaded in uploaded_files:
        try:
            client.files.delete(name=uploaded.name)
        except Exception as exc:  # pragma: no cover - cleanup warnings are best-effort
            print(
                f"warning: could not delete Gemini upload {uploaded.name}: {exc}",
                file=sys.stderr,
            )


def extract_gemini_text(response: object) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", "")
            if value:
                parts.append(str(value))
    return "\n".join(parts).strip()


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def parse_json_response(text: str) -> dict[str, Any]:
    stripped = strip_json_fence(text)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise GeminiPreprocessingGenerationError("Gemini response did not contain a JSON object")
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GeminiPreprocessingGenerationError(f"Gemini response was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GeminiPreprocessingGenerationError("Gemini response JSON must be an object")
    return payload


def _inline_source_payload(path: Path, *, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GeminiPreprocessingInputError(f"failed to read source file {path}: {exc}") from exc
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[...truncated...]"
    return "\n".join([f"### Source file: {path.name}", text])


def _build_contents(
    *,
    backend: GeminiPreprocessingBackend,
    user_prompt: str,
    source_paths: list[Path],
    max_inline_source_chars: int,
) -> tuple[list[object], list[GeminiUploadedFile]]:
    contents: list[object] = [backend.support.Part.from_text(text=user_prompt)]
    uploaded_files: list[GeminiUploadedFile] = []
    for path in source_paths:
        if not path.exists() or not path.is_file():
            raise GeminiPreprocessingInputError(f"source file does not exist: {path}")
        if path.suffix.lower() == ".pdf":
            try:
                staged_path, staged_dir = stage_upload_path(path)
            except OSError as exc:
                raise GeminiPreprocessingInputError(f"failed to stage {path.name} for Gemini upload: {exc}") from exc
            try:
                uploaded = backend.client.files.upload(
                    file=str(staged_path),
                    config={"mime_type": "application/pdf"},
                )
            except Exception as exc:
                raise GeminiPreprocessingInputError(f"failed to upload {path.name} to Gemini: {exc}") from exc
            finally:
                shutil.rmtree(staged_dir, ignore_errors=True)
            ready_file = wait_for_gemini_file_ready(backend.client, uploaded, path)
            uploaded_files.append(ready_file)
            contents.append(backend.support.Part.from_text(text=f"Attached source file: {path.name}"))
            contents.append(
                backend.support.Part.from_uri(file_uri=ready_file.uri, mime_type=ready_file.mime_type)
            )
        else:
            contents.append(
                backend.support.Part.from_text(
                    text=_inline_source_payload(path, max_chars=max_inline_source_chars)
                )
            )
    return contents, uploaded_files


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return any(
        token in text
        for token in (
            "rate limit",
            "resource_exhausted",
            "resource exhausted",
            "quota",
            "too many requests",
            "429",
        )
    )


def _is_non_retryable_quota_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return (
        "resource_exhausted" in text
        and "free_tier" in text
        and "limit: 0" in text
    )


def _quota_error_summary(exc: Exception) -> str:
    text = str(exc).strip()
    if "limit: 0" in text and "free_tier" in text:
        return (
            "Gemini quota is unavailable for this key/project: the API reports "
            "free-tier limit 0 for the requested model. Enable billing/quota on "
            "the Google project or choose an explicitly approved fallback model."
        )
    return f"Gemini quota/rate limit error: {exc}"


def generate_json(
    *,
    backend: GeminiPreprocessingBackend,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path] | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_inline_source_chars: int = DEFAULT_MAX_INLINE_SOURCE_CHARS,
    retry_count: int = 1,
    retry_sleep_seconds: int = GEMINI_RATE_LIMIT_RETRY_SECONDS,
) -> dict[str, Any]:
    if backend.provider != "gemini":
        raise GeminiPreprocessingInputError(f"unsupported preprocessing provider: {backend.provider}")
    source_paths = source_paths or []

    for attempt in range(retry_count + 1):
        uploaded_files: list[GeminiUploadedFile] = []
        try:
            contents, uploaded_files = _build_contents(
                backend=backend,
                user_prompt=user_prompt,
                source_paths=source_paths,
                max_inline_source_chars=max_inline_source_chars,
            )
            response = backend.client.models.generate_content(
                model=backend.model,
                contents=contents,
                config=backend.support.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                ),
            )
            text = extract_gemini_text(response)
            if not text:
                raise GeminiPreprocessingGenerationError("Gemini returned an empty response")
            return parse_json_response(text)
        except Exception as exc:
            if _is_non_retryable_quota_error(exc):
                raise GeminiPreprocessingGenerationError(_quota_error_summary(exc)) from exc
            if _is_rate_limit_error(exc) and attempt < retry_count:
                print(
                    "Gemini preprocessing hit a rate limit; waiting before retrying.",
                    file=sys.stderr,
                )
                time.sleep(retry_sleep_seconds)
                continue
            if isinstance(exc, GeminiPreprocessingError):
                raise
            raise GeminiPreprocessingGenerationError(f"Gemini preprocessing failed: {exc}") from exc
        finally:
            if uploaded_files:
                delete_gemini_uploaded_files(backend.client, uploaded_files)

    raise GeminiPreprocessingGenerationError("Gemini preprocessing failed after retries")
