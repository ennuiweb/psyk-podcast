"""OpenAI JSON generation helpers for review-style preprocessing."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFAULT_OPENAI_PREPROCESSING_MODEL = "gpt-5.5"
DEFAULT_OPENAI_REASONING_EFFORT = "medium"
DEFAULT_MAX_INLINE_SOURCE_CHARS = 180000
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS = 180
DEFAULT_OPENAI_OCR_TIMEOUT_SECONDS = 600
OPENAI_PREPROCESSING_GENERATION_CONFIG_VERSION = "openai-preprocessing-generation-config-v1"
OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS = (5, 15, 30)
OPENAI_BITWARDEN_SECRET_KEYS = (
    "local.codex.openai_api_key",
    "hetzner.librechat.openai_api_key",
)
OPENAI_TRANSIENT_ERROR_PATTERNS = (
    "connection reset by peer",
    "connection reset",
    "broken pipe",
    "timed out",
    "timeout",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
    "remote end closed connection",
    "ssl",
    "transport",
    "connection error",
    "network is unreachable",
    "server disconnected",
    "rate limit",
    "too many requests",
    "429",
    "500",
    "502",
    "503",
    "504",
)


class OpenAIPreprocessingError(RuntimeError):
    """Base error for OpenAI preprocessing failures."""


class OpenAIPreprocessingInputError(OpenAIPreprocessingError):
    """Raised for invalid local inputs or local setup issues."""


class OpenAIPreprocessingGenerationError(OpenAIPreprocessingError):
    """Raised when OpenAI returns an unusable response."""


@dataclass(frozen=True)
class OpenAIPreprocessingBackend:
    provider: str
    client: object
    model: str = DEFAULT_OPENAI_PREPROCESSING_MODEL


ProgressLogger = Callable[[str], None]


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


def _openai_api_key_from_local_secret_store() -> str:
    for path in _secret_store_candidates():
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        openai = payload.get("openai")
        if not isinstance(openai, dict):
            continue
        api_key = str(openai.get("api_key") or "").strip()
        if api_key:
            return api_key
    return ""


def _bitwarden_secret_value(secret_key: str) -> str:
    binary = shutil.which("bws")
    if not binary:
        return ""
    try:
        list_result = subprocess.run(
            [binary, "secret", "list", "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if list_result.returncode != 0:
        return ""
    try:
        secrets = json.loads(list_result.stdout or "[]")
    except json.JSONDecodeError:
        return ""
    secret_id = ""
    for item in secrets:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "").strip() == secret_key:
            secret_id = str(item.get("id") or "").strip()
            break
    if not secret_id:
        return ""
    try:
        get_result = subprocess.run(
            [binary, "secret", "get", secret_id, "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if get_result.returncode != 0:
        return ""
    try:
        payload = json.loads(get_result.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    return str(payload.get("value") or "").strip()


def openai_api_key() -> str:
    env_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key
    secret_store_key = _openai_api_key_from_local_secret_store()
    if secret_store_key:
        return secret_store_key
    for secret_key in OPENAI_BITWARDEN_SECRET_KEYS:
        value = _bitwarden_secret_value(secret_key)
        if value:
            return value
    return ""


def has_openai_api_key() -> bool:
    return bool(openai_api_key())


def make_openai_backend(*, model: str = DEFAULT_OPENAI_PREPROCESSING_MODEL) -> OpenAIPreprocessingBackend:
    api_key = openai_api_key()
    if not api_key:
        raise OpenAIPreprocessingInputError("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise OpenAIPreprocessingInputError("openai package not installed - pip install openai") from exc
    return OpenAIPreprocessingBackend(
        provider="openai",
        client=OpenAI(api_key=api_key, max_retries=0),
        model=model,
    )


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
            raise OpenAIPreprocessingGenerationError("OpenAI response did not contain a JSON object")
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OpenAIPreprocessingGenerationError(f"OpenAI response was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenAIPreprocessingGenerationError("OpenAI response JSON must be an object")
    return payload


def _emit_progress(progress_logger: ProgressLogger | None, message: str) -> None:
    if progress_logger is None:
        return
    try:
        progress_logger(message)
    except Exception:
        return


def _read_source_text(path: Path, *, progress_logger: ProgressLogger | None = None) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise OpenAIPreprocessingInputError("pypdf package not installed - pip install pypdf") from exc
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise OpenAIPreprocessingInputError(f"failed to open PDF source file {path}: {exc}") from exc
        page_chunks: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                extracted = page.extract_text() or ""
            except Exception:
                extracted = ""
            extracted = extracted.strip()
            if extracted:
                page_chunks.append(f"### Page {index}\n{extracted}")
        if page_chunks:
            return "\n\n".join(page_chunks)
        _emit_progress(
            progress_logger,
            f"[openai_preprocessing] no extractable PDF text in {path.name}; falling back to OCR",
        )
        return _ocr_pdf_text(path, progress_logger=progress_logger)
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise OpenAIPreprocessingInputError(f"failed to read source file {path}: {exc}") from exc


def _ocr_pdf_text(path: Path, *, progress_logger: ProgressLogger | None = None) -> str:
    if shutil.which("ocrmypdf") is None:
        raise OpenAIPreprocessingInputError(
            f"failed to extract text from PDF source file {path} and ocrmypdf is not available"
        )
    with tempfile.TemporaryDirectory(prefix="openai-preprocessing-ocr-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        sidecar_path = temp_dir / "ocr.txt"
        output_pdf_path = temp_dir / "ocr.pdf"
        try:
            _emit_progress(progress_logger, f"[openai_preprocessing] OCR starting for {path.name}")
            result = subprocess.run(
                [
                    "ocrmypdf",
                    "--skip-text",
                    "--sidecar",
                    str(sidecar_path),
                    str(path),
                    str(output_pdf_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=DEFAULT_OPENAI_OCR_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenAIPreprocessingInputError(
                f"OCR timed out for PDF source file {path} after {DEFAULT_OPENAI_OCR_TIMEOUT_SECONDS}s"
            ) from exc
        except OSError as exc:
            raise OpenAIPreprocessingInputError(f"failed to OCR PDF source file {path}: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise OpenAIPreprocessingInputError(
                f"failed to OCR PDF source file {path}: {detail or f'exit code {result.returncode}'}"
            )
        try:
            text = sidecar_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            raise OpenAIPreprocessingInputError(f"failed to read OCR sidecar for {path}: {exc}") from exc
        if not text:
            raise OpenAIPreprocessingInputError(f"OCR produced no text for PDF source file {path}")
        _emit_progress(progress_logger, f"[openai_preprocessing] OCR finished for {path.name} ({len(text)} chars)")
        return text


def _inline_source_payload(path: Path, *, max_chars: int) -> str:
    text = _read_source_text(path)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[...truncated...]"
    return "\n".join([f"### Source file: {path.name}", text])


def _build_user_prompt_with_sources(
    *,
    user_prompt: str,
    source_paths: list[Path],
    max_inline_source_chars: int,
    progress_logger: ProgressLogger | None = None,
) -> str:
    parts = [user_prompt.strip()]
    for path in source_paths:
        if not path.exists() or not path.is_file():
            raise OpenAIPreprocessingInputError(f"source file does not exist: {path}")
        parts.append(
            _inline_source_payload_with_progress(
                path,
                max_chars=max_inline_source_chars,
                progress_logger=progress_logger,
            )
        )
    return "\n\n".join(part for part in parts if part)


def _inline_source_payload_with_progress(
    path: Path,
    *,
    max_chars: int,
    progress_logger: ProgressLogger | None = None,
) -> str:
    text = _read_source_text(path, progress_logger=progress_logger)
    if len(text) > max_chars:
        _emit_progress(
            progress_logger,
            f"[openai_preprocessing] truncating {path.name} from {len(text)} to {max_chars} chars",
        )
        text = text[:max_chars].rstrip() + "\n[...truncated...]"
    return "\n".join([f"### Source file: {path.name}", text])


def _response_text(response: Any) -> str:
    output_text = str(getattr(response, "output_text", "") or "").strip()
    if output_text:
        return output_text
    output_items = getattr(response, "output", None)
    if isinstance(output_items, list):
        fragments: list[str] = []
        for item in output_items:
            content_items = getattr(item, "content", None)
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                text_value = getattr(content, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    fragments.append(text_value.strip())
        if fragments:
            return "\n".join(fragments).strip()
    return ""


def _exception_names(exc: Exception) -> set[str]:
    names = {cls.__name__.casefold() for cls in type(exc).mro()}
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, Exception):
        names |= {cls.__name__.casefold() for cls in type(cause).mro()}
    context = getattr(exc, "__context__", None)
    if isinstance(context, Exception):
        names |= {cls.__name__.casefold() for cls in type(context).mro()}
    return names


def _exception_summary(exc: Exception) -> str:
    text = str(exc or "").strip()
    if text:
        return text[:240]
    return type(exc).__name__


def _is_retryable_openai_error(exc: Exception) -> bool:
    text = str(exc or "").strip().casefold()
    names = _exception_names(exc)
    retryable_name_tokens = (
        "apitimeouterror",
        "apiconnectionerror",
        "ratelimiterror",
        "internalservererror",
        "timeout",
        "readtimeout",
        "connecttimeout",
    )
    if any(any(token in name for token in retryable_name_tokens) for name in names):
        return True
    if any(
        token in text
        for token in (
            "response was not valid json",
            "response json must be an object",
            "did not contain a json object",
            "returned an empty response",
        )
    ):
        return False
    if not text:
        return False
    return any(token in text for token in OPENAI_TRANSIENT_ERROR_PATTERNS)


def generation_config_metadata() -> dict[str, Any]:
    return {
        "version": OPENAI_PREPROCESSING_GENERATION_CONFIG_VERSION,
        "reasoning_effort": DEFAULT_OPENAI_REASONING_EFFORT,
        "text_format": "json_object_or_json_schema",
        "response_json_schema": "stage_specific",
        "request_timeout_seconds": DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS,
    }


def generate_json(
    *,
    backend: OpenAIPreprocessingBackend,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path] | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_inline_source_chars: int = DEFAULT_MAX_INLINE_SOURCE_CHARS,
    response_json_schema: dict[str, Any] | None = None,
    progress_logger: ProgressLogger | None = None,
) -> dict[str, Any]:
    if backend.provider != "openai":
        raise OpenAIPreprocessingInputError(f"unsupported preprocessing provider: {backend.provider}")
    source_paths = source_paths or []
    combined_user_prompt = _build_user_prompt_with_sources(
        user_prompt=user_prompt,
        source_paths=source_paths,
        max_inline_source_chars=max_inline_source_chars,
        progress_logger=progress_logger,
    )
    text_config: dict[str, Any]
    if response_json_schema is not None:
        text_config = {
            "format": {
                "type": "json_schema",
                "name": "printout_payload",
                "schema": response_json_schema,
                "strict": True,
            }
        }
    else:
        text_config = {"format": {"type": "json_object"}}

    last_exc: Exception | None = None
    total_attempts = len(OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS) + 1
    for attempt, delay_seconds in enumerate((0, *OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS), start=1):
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            _emit_progress(
                progress_logger,
                (
                    f"[openai_preprocessing] OpenAI request attempt {attempt}/{total_attempts} "
                    f"({backend.model}, timeout={DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS}s)"
                ),
            )
            response = backend.client.responses.create(
                model=backend.model,
                input=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": combined_user_prompt},
                ],
                max_output_tokens=max_output_tokens,
                text=text_config,
                reasoning={"effort": DEFAULT_OPENAI_REASONING_EFFORT},
                timeout=DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS,
            )
            text = _response_text(response)
            if not text:
                raise OpenAIPreprocessingGenerationError("OpenAI returned an empty response")
            _emit_progress(progress_logger, f"[openai_preprocessing] OpenAI request succeeded on attempt {attempt}/{total_attempts}")
            return parse_json_response(text)
        except Exception as exc:
            if isinstance(exc, OpenAIPreprocessingError):
                last_exc = exc
            else:
                last_exc = OpenAIPreprocessingGenerationError(f"OpenAI preprocessing failed: {exc}")
            if attempt >= total_attempts or not _is_retryable_openai_error(exc):
                raise last_exc
            next_delay_seconds = OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS[attempt - 1]
            _emit_progress(
                progress_logger,
                (
                    f"[openai_preprocessing] transient OpenAI failure on attempt {attempt}/{total_attempts}: "
                    f"{_exception_summary(exc)}; retrying in {next_delay_seconds}s"
                ),
            )
            continue
    if last_exc is not None:
        raise last_exc
    raise OpenAIPreprocessingGenerationError("OpenAI preprocessing failed after retries")


def preflight_openai_json_generation(
    *,
    model: str = DEFAULT_OPENAI_PREPROCESSING_MODEL,
    backend: OpenAIPreprocessingBackend | None = None,
) -> dict[str, Any]:
    active_backend = backend or make_openai_backend(model=model)
    return generate_json(
        backend=active_backend,
        system_instruction="Return only valid JSON.",
        user_prompt='Return exactly this JSON object: {"ok": true}',
        max_output_tokens=512,
        response_json_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    )
