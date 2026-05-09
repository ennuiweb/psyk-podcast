"""Resolve queue-runtime behavior from show config plus repo defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

QUEUE_POLICY_MODES = {"always", "never", "quiz_or_infographic"}


@dataclass(frozen=True, slots=True)
class QuizSyncSettings:
    output_root: str
    links_file: str
    subject_slug: str
    remote_root: str
    include_subject_in_flat_id: bool = False
    language_tag: str = "[EN]"


@dataclass(frozen=True, slots=True)
class QueueShowPolicies:
    quiz_sync: QuizSyncSettings | None = None
    spotify_sync: bool = False
    spotify_show_url: str | None = None
    content_manifest_mode: str = "never"
    portal_sidecars_mode: str = "never"
    validate_manual_summaries: bool = False
    regeneration_registry: bool = False
    validate_regeneration_inventory: bool = False
    audit_slide_briefs: bool = False
    learning_material_registry: bool = False
    downstream_freudd_deploy: bool = False


DEFAULT_QUEUE_SHOW_POLICIES: dict[str, QueueShowPolicies] = {
    "bioneuro": QueueShowPolicies(
        quiz_sync=QuizSyncSettings(
            output_root="notebooklm-podcast-auto/bioneuro/output",
            links_file="shows/bioneuro/quiz_links.json",
            subject_slug="bioneuro",
            remote_root="/var/www/quizzes/bioneuro",
            include_subject_in_flat_id=True,
        ),
        spotify_sync=True,
        spotify_show_url="https://open.spotify.com/show/5QIHRkc1N6xuCqtnfmsPfN",
        content_manifest_mode="always",
        portal_sidecars_mode="always",
        downstream_freudd_deploy=True,
    ),
    "personlighedspsykologi-en": QueueShowPolicies(
        quiz_sync=QuizSyncSettings(
            output_root="notebooklm-podcast-auto/personlighedspsykologi/output",
            links_file="shows/personlighedspsykologi-en/quiz_links.json",
            subject_slug="personlighedspsykologi",
            remote_root="/var/www/quizzes/personlighedspsykologi",
            language_tag="[EN]",
        ),
        spotify_sync=True,
        spotify_show_url="https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv",
        content_manifest_mode="always",
        portal_sidecars_mode="quiz_or_infographic",
        validate_manual_summaries=True,
        regeneration_registry=True,
        validate_regeneration_inventory=True,
        audit_slide_briefs=True,
        learning_material_registry=True,
        downstream_freudd_deploy=True,
    ),
}


def resolve_queue_show_policies(*, show_slug: str, config: Mapping[str, Any]) -> QueueShowPolicies:
    defaults = DEFAULT_QUEUE_SHOW_POLICIES.get(show_slug, QueueShowPolicies())
    queue_cfg = config.get("queue")
    if queue_cfg is None:
        return defaults
    if not isinstance(queue_cfg, Mapping):
        raise ValueError("queue config must be a JSON object when present.")

    quiz_sync = _resolve_quiz_sync(defaults.quiz_sync, queue_cfg.get("quiz_sync"))
    spotify_sync = _coerce_bool(queue_cfg.get("spotify_sync"), default=defaults.spotify_sync)
    spotify_show_url = _string_or_none(queue_cfg.get("spotify_show_url"), default=defaults.spotify_show_url)

    return QueueShowPolicies(
        quiz_sync=quiz_sync,
        spotify_sync=spotify_sync,
        spotify_show_url=spotify_show_url,
        content_manifest_mode=_resolve_mode(
            queue_cfg.get("content_manifest_mode"),
            default=defaults.content_manifest_mode,
            field_name="queue.content_manifest_mode",
        ),
        portal_sidecars_mode=_resolve_mode(
            queue_cfg.get("portal_sidecars_mode"),
            default=defaults.portal_sidecars_mode,
            field_name="queue.portal_sidecars_mode",
        ),
        validate_manual_summaries=_coerce_bool(
            queue_cfg.get("validate_manual_summaries"),
            default=defaults.validate_manual_summaries,
        ),
        regeneration_registry=_coerce_bool(
            queue_cfg.get("regeneration_registry"),
            default=defaults.regeneration_registry,
        ),
        validate_regeneration_inventory=_coerce_bool(
            queue_cfg.get("validate_regeneration_inventory"),
            default=defaults.validate_regeneration_inventory,
        ),
        audit_slide_briefs=_coerce_bool(
            queue_cfg.get("audit_slide_briefs"),
            default=defaults.audit_slide_briefs,
        ),
        learning_material_registry=_coerce_bool(
            queue_cfg.get("learning_material_registry"),
            default=defaults.learning_material_registry,
        ),
        downstream_freudd_deploy=_coerce_bool(
            queue_cfg.get("freudd_deploy"),
            default=defaults.downstream_freudd_deploy,
        ),
    )


def _resolve_quiz_sync(
    default: QuizSyncSettings | None,
    raw_value: object,
) -> QuizSyncSettings | None:
    if raw_value is None:
        return default
    if not isinstance(raw_value, Mapping):
        raise ValueError("queue.quiz_sync must be a JSON object when present.")

    enabled_default = default is not None
    enabled = _coerce_bool(raw_value.get("enabled"), default=enabled_default)
    if not enabled:
        return None

    base = default
    output_root = _string_or_none(raw_value.get("output_root"), default=base.output_root if base else None)
    links_file = _string_or_none(raw_value.get("links_file"), default=base.links_file if base else None)
    subject_slug = _string_or_none(raw_value.get("subject_slug"), default=base.subject_slug if base else None)
    remote_root = _string_or_none(raw_value.get("remote_root"), default=base.remote_root if base else None)
    language_tag = _string_or_none(raw_value.get("language_tag"), default=base.language_tag if base else "[EN]")
    include_subject_in_flat_id = _coerce_bool(
        raw_value.get("include_subject_in_flat_id"),
        default=base.include_subject_in_flat_id if base else False,
    )

    if not output_root:
        raise ValueError("queue.quiz_sync.output_root is required when quiz sync is enabled.")
    if not links_file:
        raise ValueError("queue.quiz_sync.links_file is required when quiz sync is enabled.")
    if not subject_slug:
        raise ValueError("queue.quiz_sync.subject_slug is required when quiz sync is enabled.")
    if not remote_root:
        raise ValueError("queue.quiz_sync.remote_root is required when quiz sync is enabled.")
    if not language_tag:
        raise ValueError("queue.quiz_sync.language_tag is required when quiz sync is enabled.")

    return QuizSyncSettings(
        output_root=output_root,
        links_file=links_file,
        subject_slug=subject_slug,
        remote_root=remote_root,
        include_subject_in_flat_id=include_subject_in_flat_id,
        language_tag=language_tag,
    )


def _resolve_mode(raw_value: object, *, default: str, field_name: str) -> str:
    if raw_value in (None, ""):
        mode = default
    else:
        mode = str(raw_value).strip().lower()
    if mode not in QUEUE_POLICY_MODES:
        allowed = ", ".join(sorted(QUEUE_POLICY_MODES))
        raise ValueError(f"{field_name} must be one of: {allowed}.")
    return mode


def _string_or_none(raw_value: object, *, default: str | None) -> str | None:
    if raw_value in (None, ""):
        return default
    value = str(raw_value).strip()
    return value or default


def _coerce_bool(raw_value: object, *, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Expected boolean-like value, got {raw_value!r}.")
