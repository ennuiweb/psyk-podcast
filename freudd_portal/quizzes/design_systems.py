"""Design system registry and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DesignSystemDefinition:
    key: str
    label: str
    description: str


_DESIGN_SYSTEMS: tuple[DesignSystemDefinition, ...] = (
    DesignSystemDefinition(
        key="classic",
        label="Classic",
        description="Eksisterende lyse portal-design.",
    ),
    DesignSystemDefinition(
        key="night-lab",
        label="Night Lab",
        description="Mørkt, fokuseret og kontraststærkt studieudtryk.",
    ),
    DesignSystemDefinition(
        key="paper-studio",
        label="Paper Studio",
        description="Lys, varm og editorial-inspireret læseflade.",
    ),
)

DEFAULT_DESIGN_SYSTEM_KEY = "paper-studio"

DESIGN_SYSTEM_KEY_TO_DEFINITION: dict[str, DesignSystemDefinition] = {
    item.key: item for item in _DESIGN_SYSTEMS
}
VALID_DESIGN_SYSTEM_KEYS: set[str] = set(DESIGN_SYSTEM_KEY_TO_DEFINITION)


def list_design_systems() -> tuple[DesignSystemDefinition, ...]:
    return _DESIGN_SYSTEMS


def normalize_design_system_key(value: object) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    if key not in VALID_DESIGN_SYSTEM_KEYS:
        return None
    return key


def get_design_system_definition(key: object) -> DesignSystemDefinition:
    normalized = normalize_design_system_key(key) or DEFAULT_DESIGN_SYSTEM_KEY
    return DESIGN_SYSTEM_KEY_TO_DEFINITION.get(normalized) or DESIGN_SYSTEM_KEY_TO_DEFINITION[
        DEFAULT_DESIGN_SYSTEM_KEY
    ]


def iter_design_system_payload() -> Iterable[dict[str, str]]:
    for item in _DESIGN_SYSTEMS:
        yield {
            "key": item.key,
            "label": item.label,
            "description": item.description,
        }
