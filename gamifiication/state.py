from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from config import UnitConfig


def _iso_timestamp_utc(now: datetime | None = None) -> str:
    reference = now or datetime.utcnow()
    return reference.replace(microsecond=0).isoformat() + "Z"


def initialize_state(units: list[UnitConfig], *, now: datetime | None = None) -> dict[str, Any]:
    if not units:
        raise ValueError("At least one unit is required to initialize state.")

    state_units: dict[str, dict[str, Any]] = {}
    for index, unit in enumerate(units):
        state_units[unit.id] = {
            "status": "active" if index == 0 else "locked",
            "anki_tag": unit.anki_tag,
            "label": unit.label,
            "mastered_cards": 0,
            "total_cards": 0,
            "mastery_ratio": 0.0,
        }

    return {
        "current_level": 1,
        "units": state_units,
        "daily": {
            "reviews_today": 0,
            "min_daily_reviews": 0,
            "passed": False,
            "missing_reviews": 0,
        },
        "last_sync": _iso_timestamp_utc(now),
        "last_sync_errors": [],
    }


def load_state(path: Path, units: list[UnitConfig]) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("State file must contain a JSON object.")
    else:
        raw = initialize_state(units)

    # Always ensure current unit schema is present, preserving historic fields.
    raw_units = raw.get("units") if isinstance(raw.get("units"), dict) else {}
    normalized_units: dict[str, dict[str, Any]] = {}
    for index, unit in enumerate(units):
        existing = raw_units.get(unit.id, {})
        if not isinstance(existing, dict):
            existing = {}
        normalized_units[unit.id] = {
            "status": existing.get("status", "active" if index == 0 else "locked"),
            "anki_tag": unit.anki_tag,
            "label": unit.label,
            "mastered_cards": int(existing.get("mastered_cards", 0) or 0),
            "total_cards": int(existing.get("total_cards", 0) or 0),
            "mastery_ratio": float(existing.get("mastery_ratio", 0.0) or 0.0),
        }

    raw["units"] = normalized_units
    raw.setdefault("current_level", 1)
    raw.setdefault(
        "daily",
        {
            "reviews_today": 0,
            "min_daily_reviews": 0,
            "passed": False,
            "missing_reviews": 0,
        },
    )
    raw.setdefault("last_sync", _iso_timestamp_utc())
    raw.setdefault("last_sync_errors", [])
    return raw


def atomic_write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
        json.dump(state, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        temp_path = Path(tmp.name)
    temp_path.replace(path)


def derive_unit_status_updates(
    *,
    units: list[UnitConfig],
    unit_progress: dict[str, dict[str, Any]],
    mastery_ratio_threshold: float,
) -> tuple[int, dict[str, dict[str, Any]]]:
    normalized_progress: dict[str, dict[str, Any]] = {}
    first_incomplete_level: int | None = None

    for index, unit in enumerate(units, start=1):
        raw = unit_progress.get(unit.id, {})
        total_cards = int(raw.get("total_cards", 0) or 0)
        mastered_cards = int(raw.get("mastered_cards", 0) or 0)
        if total_cards < 0:
            total_cards = 0
        if mastered_cards < 0:
            mastered_cards = 0
        if mastered_cards > total_cards and total_cards > 0:
            mastered_cards = total_cards

        mastery_ratio = 0.0
        if total_cards > 0:
            mastery_ratio = mastered_cards / total_cards

        if total_cards > 0 and mastery_ratio >= mastery_ratio_threshold:
            status = "completed"
        elif first_incomplete_level is None:
            status = "active"
            first_incomplete_level = index
        else:
            status = "locked"

        normalized_progress[unit.id] = {
            "status": status,
            "anki_tag": unit.anki_tag,
            "label": unit.label,
            "mastered_cards": mastered_cards,
            "total_cards": total_cards,
            "mastery_ratio": round(mastery_ratio, 4),
        }

    if first_incomplete_level is None:
        current_level = len(units)
    else:
        current_level = first_incomplete_level

    return current_level, normalized_progress
