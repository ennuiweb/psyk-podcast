from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import RenderConfig


class RenderError(RuntimeError):
    """Raised when visual state rendering fails."""


ICON_BY_STATUS = {
    "completed": "🟢",
    "active": "🟡",
    "locked": "🔒",
}

CANVAS_COLOR_BY_STATUS = {
    "completed": "green",
    "active": "yellow",
    "locked": "gray",
}


def render_html_state(state: dict[str, Any], *, render_config: RenderConfig) -> Path:
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ModuleNotFoundError as exc:
        raise RenderError("Jinja2 is required for HTML rendering. Install dependencies and retry.") from exc

    template_path = render_config.html_template
    if not template_path.exists():
        raise RenderError(f"HTML template not found: {template_path}")

    environment = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    template = environment.get_template(template_path.name)

    output_path = render_config.html_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    units = []
    for unit_id, unit_state in state.get("units", {}).items():
        if not isinstance(unit_state, dict):
            continue
        status = str(unit_state.get("status", "locked"))
        node_class = "locked"
        node_icon = "🔒"
        if status == "active":
            node_class = "active"
            node_icon = "▶"
        elif status == "completed":
            node_class = "completed"
            node_icon = "✓"
        units.append(
            {
                "id": unit_id,
                "label": unit_state.get("label", unit_id),
                "status": status,
                "icon": ICON_BY_STATUS.get(status, "🔒"),
                "node_class": node_class,
                "node_icon": node_icon,
                "mastered_cards": int(unit_state.get("mastered_cards", 0) or 0),
                "total_cards": int(unit_state.get("total_cards", 0) or 0),
                "mastery_ratio": float(unit_state.get("mastery_ratio", 0.0) or 0.0),
            }
        )

    rendered = template.render(
        current_level=state.get("current_level", 1),
        units=units,
        daily=state.get("daily", {}),
        last_sync=state.get("last_sync"),
    )
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def _normalize_canvas_label(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[🔒🟢🟡\s]+", "", cleaned)
    return cleaned.strip().casefold()


def update_canvas_state(state: dict[str, Any], *, render_config: RenderConfig) -> tuple[Path, int]:
    canvas_path = render_config.canvas_file
    if not canvas_path.exists():
        raise RenderError(f"Canvas file not found: {canvas_path}")

    with canvas_path.open("r", encoding="utf-8") as handle:
        canvas = json.load(handle)

    if not isinstance(canvas, dict):
        raise RenderError("Canvas file must contain a JSON object.")

    units = state.get("units", {})
    if not isinstance(units, dict):
        raise RenderError("State units payload is invalid.")

    unit_lookup: dict[str, dict[str, Any]] = {}
    for unit_id, unit_state in units.items():
        if not isinstance(unit_state, dict):
            continue
        unit_lookup[str(unit_id).casefold()] = unit_state
        label = str(unit_state.get("label", unit_id)).casefold()
        unit_lookup[label] = unit_state

    nodes = canvas.get("nodes")
    if not isinstance(nodes, list):
        raise RenderError("Canvas JSON is missing a nodes array.")

    updated_nodes = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        text = node.get("text")
        if not isinstance(text, str) or not text.strip():
            continue

        normalized = _normalize_canvas_label(text)
        unit_state = unit_lookup.get(normalized)
        if not unit_state:
            continue

        status = str(unit_state.get("status", "locked"))
        label = str(unit_state.get("label") or normalized)
        icon = ICON_BY_STATUS.get(status, "🔒")
        node["text"] = f"{icon} {label}"
        node["color"] = CANVAS_COLOR_BY_STATUS.get(status, "gray")
        updated_nodes += 1

    canvas_path.write_text(json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8")
    return canvas_path, updated_nodes
