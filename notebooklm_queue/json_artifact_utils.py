"""Helpers for semantically stable JSON artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_VOLATILE_KEYS = frozenset({"generated_at"})


def render_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _normalize_for_semantics(value: Any, *, ignore_keys: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_for_semantics(item, ignore_keys=ignore_keys)
            for key, item in sorted(value.items())
            if key not in ignore_keys
        }
    if isinstance(value, list):
        return [_normalize_for_semantics(item, ignore_keys=ignore_keys) for item in value]
    return value


def semantic_payload(value: Any, *, ignore_keys: frozenset[str] = DEFAULT_VOLATILE_KEYS) -> Any:
    return _normalize_for_semantics(value, ignore_keys=ignore_keys)


def semantic_equal(left: Any, right: Any, *, ignore_keys: frozenset[str] = DEFAULT_VOLATILE_KEYS) -> bool:
    return semantic_payload(left, ignore_keys=ignore_keys) == semantic_payload(right, ignore_keys=ignore_keys)


def semantic_fingerprint(value: Any, *, ignore_keys: frozenset[str] = DEFAULT_VOLATILE_KEYS) -> str:
    normalized = semantic_payload(value, ignore_keys=ignore_keys)
    rendered = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def semantic_file_fingerprint(path: Path, *, ignore_keys: frozenset[str] = DEFAULT_VOLATILE_KEYS) -> str:
    return semantic_fingerprint(json.loads(path.read_text(encoding="utf-8")), ignore_keys=ignore_keys)


def _preserve_existing_generated_at(payload: Any, existing_payload: Any) -> Any:
    if not isinstance(payload, dict) or not isinstance(existing_payload, dict):
        return payload
    if "generated_at" not in payload:
        return payload
    existing_generated_at = existing_payload.get("generated_at")
    if not existing_generated_at:
        return payload
    updated = dict(payload)
    updated["generated_at"] = existing_generated_at
    return updated


def write_json_stably(
    path: Path,
    payload: Any,
    *,
    ignore_keys: frozenset[str] = DEFAULT_VOLATILE_KEYS,
) -> tuple[Any, bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    final_payload = payload
    existing_text: str | None = None
    existing_payload: Any = None

    if path.exists() and path.is_file():
        existing_text = path.read_text(encoding="utf-8")
        try:
            existing_payload = json.loads(existing_text)
        except json.JSONDecodeError:
            existing_payload = None
        if existing_payload is not None and semantic_equal(existing_payload, payload, ignore_keys=ignore_keys):
            final_payload = _preserve_existing_generated_at(payload, existing_payload)

    rendered = render_json(final_payload)
    if existing_text == rendered:
        return final_payload, False

    path.write_text(rendered, encoding="utf-8")
    return final_payload, True
