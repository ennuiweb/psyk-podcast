"""Template context processors for UI concerns."""

from __future__ import annotations

from .design_systems import iter_design_system_payload
from .theme_resolver import (
    DESIGN_SYSTEM_QUERY_PARAM,
    DESIGN_SYSTEM_SESSION_PREVIEW_KEY,
    get_cookie_name,
    resolve_design_system,
)


def design_system_context(request):
    resolved = resolve_design_system(request)
    return {
        "design_systems": list(iter_design_system_payload()),
        "active_design_system": {
            "key": resolved.key,
            "label": resolved.definition.label,
            "description": resolved.definition.description,
            "source": resolved.source,
            "is_preview": resolved.is_preview,
        },
        "active_design_system_key": resolved.key,
        "design_system_query_param": DESIGN_SYSTEM_QUERY_PARAM,
        "design_system_cookie_name": get_cookie_name(),
        "design_system_preview_session_key": DESIGN_SYSTEM_SESSION_PREVIEW_KEY,
    }
