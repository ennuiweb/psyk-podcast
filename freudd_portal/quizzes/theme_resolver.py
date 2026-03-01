"""Resolve active design system for each request.

Current runtime is locked to Paper Studio. The registry helpers remain so
additional themes can be added later without changing template contracts.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from .design_systems import (
    DEFAULT_DESIGN_SYSTEM_KEY,
    DesignSystemDefinition,
    get_design_system_definition,
    normalize_design_system_key,
)


@dataclass(frozen=True)
class ResolvedDesignSystem:
    key: str
    source: str
    is_preview: bool
    definition: DesignSystemDefinition


def _default_design_system_key() -> str:
    configured = normalize_design_system_key(getattr(settings, "FREUDD_DESIGN_SYSTEM_DEFAULT", ""))
    return configured or DEFAULT_DESIGN_SYSTEM_KEY


def resolve_design_system(request) -> ResolvedDesignSystem:
    key = _default_design_system_key()
    return ResolvedDesignSystem(
        key=key,
        source="default",
        is_preview=False,
        definition=get_design_system_definition(key),
    )
