from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when pipeline configuration is invalid."""


@dataclass(frozen=True)
class UnitConfig:
    id: str
    label: str
    anki_tag: str


@dataclass(frozen=True)
class AnkiConfig:
    endpoint: str
    deck_name: str
    note_model: str
    front_field: str
    back_field: str
    default_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HabiticaConfig:
    api_base: str
    task_id: str
    user_id_env: str
    api_token_env: str
    xp_per_review: float
    gold_per_review: float
    damage_per_missing_review: float
    max_damage: float
    reviews_per_score_up: int
    missing_reviews_per_score_down: int


@dataclass(frozen=True)
class SyncConfig:
    min_daily_reviews: int
    state_file: Path
    timezone: str
    deck_name: str
    mastery_interval_days: int
    mastery_ratio_threshold: float
    units: list[UnitConfig]


@dataclass(frozen=True)
class RenderConfig:
    mode: str
    html_template: Path
    html_output: Path
    canvas_file: Path


@dataclass(frozen=True)
class IngestConfig:
    provider: str
    model: str
    api_key_env: str
    max_cards: int
    default_unit_tag: str


@dataclass(frozen=True)
class AppConfig:
    anki: AnkiConfig
    habitica: HabiticaConfig
    sync: SyncConfig
    render: RenderConfig
    ingest: IngestConfig


def _require_dict(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be an object.")
    return value


def _require_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_int(value: Any, *, name: str, minimum: int | None = None) -> int:
    if not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer.")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def _require_float(value: Any, *, name: str, minimum: float | None = None) -> float:
    if not isinstance(value, (float, int)):
        raise ConfigError(f"{name} must be a number.")
    numeric = float(value)
    if minimum is not None and numeric < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return numeric


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _parse_units(raw_units: Any, *, name: str) -> list[UnitConfig]:
    if not isinstance(raw_units, list) or not raw_units:
        raise ConfigError(f"{name} must be a non-empty array.")

    units: list[UnitConfig] = []
    seen_ids: set[str] = set()
    for index, raw_unit in enumerate(raw_units, start=1):
        unit_obj = _require_dict(raw_unit, name=f"{name}[{index}]")
        unit_id = _require_non_empty_string(unit_obj.get("id"), name=f"{name}[{index}].id")
        if unit_id in seen_ids:
            raise ConfigError(f"Duplicate unit id: {unit_id}")
        seen_ids.add(unit_id)

        label = _require_non_empty_string(
            unit_obj.get("label") or unit_id,
            name=f"{name}[{index}].label",
        )
        anki_tag = _require_non_empty_string(
            unit_obj.get("anki_tag") or unit_id,
            name=f"{name}[{index}].anki_tag",
        )
        units.append(UnitConfig(id=unit_id, label=label, anki_tag=anki_tag))
    return units


def load_config(config_path: Path) -> AppConfig:
    resolved_path = config_path.expanduser().resolve()
    with resolved_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    config_obj = _require_dict(raw, name="config")
    base_dir = resolved_path.parent

    anki_obj = _require_dict(config_obj.get("anki"), name="anki")
    raw_default_tags = anki_obj.get("default_tags", [])
    if raw_default_tags is None:
        raw_default_tags = []
    if not isinstance(raw_default_tags, list):
        raise ConfigError("anki.default_tags must be an array of strings.")

    anki = AnkiConfig(
        endpoint=_require_non_empty_string(
            anki_obj.get("endpoint") or "http://localhost:8765", name="anki.endpoint"
        ),
        deck_name=_require_non_empty_string(
            anki_obj.get("deck_name") or "Psychology", name="anki.deck_name"
        ),
        note_model=_require_non_empty_string(
            anki_obj.get("note_model") or "Basic", name="anki.note_model"
        ),
        front_field=_require_non_empty_string(
            anki_obj.get("front_field") or "Front", name="anki.front_field"
        ),
        back_field=_require_non_empty_string(
            anki_obj.get("back_field") or "Back", name="anki.back_field"
        ),
        default_tags=[str(tag).strip() for tag in raw_default_tags if str(tag).strip()],
    )

    habitica_obj = _require_dict(config_obj.get("habitica"), name="habitica")
    habitica = HabiticaConfig(
        api_base=_require_non_empty_string(
            habitica_obj.get("api_base") or "https://habitica.com/api/v3",
            name="habitica.api_base",
        ).rstrip("/"),
        task_id=_require_non_empty_string(habitica_obj.get("task_id"), name="habitica.task_id"),
        user_id_env=_require_non_empty_string(
            habitica_obj.get("user_id_env") or "HABITICA_USER_ID", name="habitica.user_id_env"
        ),
        api_token_env=_require_non_empty_string(
            habitica_obj.get("api_token_env") or "HABITICA_API_TOKEN",
            name="habitica.api_token_env",
        ),
        xp_per_review=_require_float(
            habitica_obj.get("xp_per_review", 0.2),
            name="habitica.xp_per_review",
            minimum=0,
        ),
        gold_per_review=_require_float(
            habitica_obj.get("gold_per_review", 0.05),
            name="habitica.gold_per_review",
            minimum=0,
        ),
        damage_per_missing_review=_require_float(
            habitica_obj.get("damage_per_missing_review", 0.3),
            name="habitica.damage_per_missing_review",
            minimum=0,
        ),
        max_damage=_require_float(
            habitica_obj.get("max_damage", 15),
            name="habitica.max_damage",
            minimum=0,
        ),
        reviews_per_score_up=_require_int(
            habitica_obj.get("reviews_per_score_up", 20),
            name="habitica.reviews_per_score_up",
            minimum=1,
        ),
        missing_reviews_per_score_down=_require_int(
            habitica_obj.get("missing_reviews_per_score_down", 5),
            name="habitica.missing_reviews_per_score_down",
            minimum=1,
        ),
    )

    sync_obj = _require_dict(config_obj.get("sync"), name="sync")
    units = _parse_units(sync_obj.get("units"), name="sync.units")
    sync = SyncConfig(
        min_daily_reviews=_require_int(
            sync_obj.get("min_daily_reviews", 20),
            name="sync.min_daily_reviews",
            minimum=1,
        ),
        state_file=_resolve_path(
            base_dir,
            _require_non_empty_string(
                sync_obj.get("state_file") or "semester_state.json", name="sync.state_file"
            ),
        ),
        timezone=_require_non_empty_string(
            sync_obj.get("timezone") or "UTC", name="sync.timezone"
        ),
        deck_name=_require_non_empty_string(
            sync_obj.get("deck_name") or anki.deck_name,
            name="sync.deck_name",
        ),
        mastery_interval_days=_require_int(
            sync_obj.get("mastery_interval_days", 7),
            name="sync.mastery_interval_days",
            minimum=1,
        ),
        mastery_ratio_threshold=_require_float(
            sync_obj.get("mastery_ratio_threshold", 0.8),
            name="sync.mastery_ratio_threshold",
            minimum=0,
        ),
        units=units,
    )
    if sync.mastery_ratio_threshold > 1:
        raise ConfigError("sync.mastery_ratio_threshold must be <= 1.")

    render_obj = _require_dict(config_obj.get("render"), name="render")
    render_mode = _require_non_empty_string(render_obj.get("mode") or "html", name="render.mode")
    if render_mode not in {"none", "html", "canvas"}:
        raise ConfigError("render.mode must be one of: none, html, canvas")
    render = RenderConfig(
        mode=render_mode,
        html_template=_resolve_path(
            base_dir,
            _require_non_empty_string(
                render_obj.get("html_template") or "templates/path.html.j2",
                name="render.html_template",
            ),
        ),
        html_output=_resolve_path(
            base_dir,
            _require_non_empty_string(
                render_obj.get("html_output") or "index.html",
                name="render.html_output",
            ),
        ),
        canvas_file=_resolve_path(
            base_dir,
            _require_non_empty_string(
                render_obj.get("canvas_file") or "course_map.canvas",
                name="render.canvas_file",
            ),
        ),
    )

    ingest_obj = _require_dict(config_obj.get("ingest"), name="ingest")
    provider = _require_non_empty_string(ingest_obj.get("provider") or "openai", name="ingest.provider")
    if provider not in {"openai", "mock"}:
        raise ConfigError("ingest.provider must be one of: openai, mock")
    ingest = IngestConfig(
        provider=provider,
        model=_require_non_empty_string(
            ingest_obj.get("model") or "gpt-4.1-mini", name="ingest.model"
        ),
        api_key_env=_require_non_empty_string(
            ingest_obj.get("api_key_env") or "OPENAI_API_KEY",
            name="ingest.api_key_env",
        ),
        max_cards=_require_int(ingest_obj.get("max_cards", 10), name="ingest.max_cards", minimum=1),
        default_unit_tag=_require_non_empty_string(
            ingest_obj.get("default_unit_tag") or sync.units[0].anki_tag,
            name="ingest.default_unit_tag",
        ),
    )

    return AppConfig(anki=anki, habitica=habitica, sync=sync, render=render, ingest=ingest)
