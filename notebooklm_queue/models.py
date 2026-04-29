"""Data models for the NotebookLM queue subsystem."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def _normalize_token(value: str) -> str:
    return str(value).strip()


def _normalize_content_types(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = sorted({_normalize_token(value) for value in values if _normalize_token(value)})
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class JobIdentity:
    """Stable identity for one queue job."""

    show_slug: str
    subject_slug: str
    lecture_key: str
    content_types: tuple[str, ...]
    config_hash: str
    campaign: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "show_slug", _normalize_token(self.show_slug))
        object.__setattr__(self, "subject_slug", _normalize_token(self.subject_slug))
        object.__setattr__(self, "lecture_key", _normalize_token(self.lecture_key))
        object.__setattr__(self, "config_hash", _normalize_token(self.config_hash))
        object.__setattr__(self, "campaign", _normalize_token(self.campaign or "") or None)
        object.__setattr__(self, "content_types", _normalize_content_types(self.content_types))
        if not self.show_slug:
            raise ValueError("show_slug is required")
        if not self.subject_slug:
            raise ValueError("subject_slug is required")
        if not self.lecture_key:
            raise ValueError("lecture_key is required")
        if not self.content_types:
            raise ValueError("content_types must not be empty")
        if not self.config_hash:
            raise ValueError("config_hash is required")

    def to_payload(self) -> dict[str, object]:
        return {
            "show_slug": self.show_slug,
            "subject_slug": self.subject_slug,
            "lecture_key": self.lecture_key,
            "content_types": list(self.content_types),
            "config_hash": self.config_hash,
            "campaign": self.campaign,
        }

    def stable_key(self) -> str:
        payload = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

