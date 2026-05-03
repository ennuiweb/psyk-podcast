"""Shared prompt assembly helpers for NotebookLM generation wrappers."""

from __future__ import annotations

import re
from pathlib import Path

PROMPT_SIDECAR_SUFFIXES = (
    ".prompt.md",
    ".prompt.txt",
    ".analysis.md",
    ".analysis.txt",
)
WEEK_PROMPT_SIDECAR_NAMES = (
    "week.prompt.md",
    "week.prompt.txt",
    "week.analysis.md",
    "week.analysis.txt",
)
AUDIO_PROMPT_TYPES = (
    "single_reading",
    "single_slide",
    "weekly_readings_only",
    "short",
    "mixed_sources",
)
AUDIO_FORMAT_VALUES = {"deep-dive", "brief", "critique", "debate"}
AUDIO_LENGTH_VALUES = {"short", "default", "long"}
GEMINI_META_PROMPT_MODEL = "gemini-3.1-pro-preview"

DEFAULT_AUDIO_PROMPT_STRATEGY = {
    "enabled": True,
    "audience": "a bachelor's-level psychology student",
    "tone": "calm, precise, teaching-oriented. Avoid dramatization.",
    "source_roles": {
        "slides": "Use the slides as the structural map and the lecturer's interpretive frame.",
        "readings": "Use the readings for conceptual distinctions, qualifications, and argumentative depth.",
    },
    "prompt_types": {
        "single_reading": {
            "focus": [
                "the source's central claims and argument structure",
                "the most important conceptual distinctions and delimitations",
                "what the source explicitly rejects, corrects, or qualifies",
                "where a student is most likely to misunderstand the source",
                "what the source changes for psychological thinking about personality and the subject",
            ]
        },
        "single_slide": {
            "lead": "The source is a slide deck. Slides are fragmentary and assume spoken elaboration.",
            "focus": [
                "the overarching problem the lecture is trying to address",
                "the sequence logic that organizes the lecture",
                "the concepts and distinctions that are most exam-relevant",
                "where the slides most likely simplify something important",
                "what the material challenges in psychology's self-understanding",
            ]
        },
        "weekly_readings_only": {
            "lead": "You are working with multiple readings on the same lecture block.",
            "focus": [
                "the shared problem or question that organizes the material",
                "the key conceptual distinctions, tensions, and disagreements across the readings",
                "where the readings qualify, deepen, or correct one another",
                "what a student is most likely to misunderstand",
                "what matters most for psychological thinking about personality and the subject",
            ]
        },
        "short": {
            "lead": "Keep the explanation compact, memorable, and exam-oriented without becoming vague.",
            "focus": [
                "the single most important claim, problem, or insight",
                "the key distinction or clarification to remember",
                "the misunderstanding or oversimplification to avoid",
                "what is most important to take into exam preparation",
            ]
        },
        "mixed_sources": {
            "lead": "You are working with both slides and readings.",
            "focus": [
                "the overarching problem and argumentative sequence of the lecture block",
                "the key distinctions, tensions, and corrections across slides and readings",
                "where the readings nuance, complicate, or correct the lecture framing",
                "what is most exam-relevant and easiest to misunderstand",
                "what the material changes in psychology's self-understanding",
            ]
        },
    },
}
DEFAULT_EXAM_FOCUS = {
    "enabled": True,
    "heading": "Exam lens:",
    "prompt_types": {
        "single_reading": [
            "clarify the theory's historical tradition and core assumptions",
            "analyze the theory's possibilities and limitations for the problem at hand",
            "explain what kind of method relation or methodological stance is implied",
            "make clear what should be evaluated critically, not just summarized",
        ],
        "single_slide": [
            "clarify the lecture's theoretical placement where the slides make it possible",
            "state the most important possibilities and limitations implied by the material",
            "note what kind of theory-method relation is implied",
            "flag what should be evaluated critically rather than repeated",
        ],
        "weekly_readings_only": [
            "clarify the historical tradition and core assumptions in play across the readings",
            "analyze the theories' possibilities and limitations for the shared problem",
            "make the relation between theory and method explicit where it matters",
            "show what should be evaluated critically, not just summarized",
        ],
        "short": [
            "make clear what matters most for exam preparation",
            "include at least one limitation, tension, or critical point rather than only summarizing",
        ],
        "mixed_sources": [
            "clarify the historical tradition and core assumptions in play",
            "analyze the theories' possibilities and limitations for the problem at hand",
            "make the relation between theory and method explicit where it matters",
            "show what should be evaluated critically, not just summarized",
        ],
    },
}
DEFAULT_META_PROMPTING = {
    "enabled": True,
    "heading": "External pre-analysis to integrate if useful:",
    "per_source_suffixes": list(PROMPT_SIDECAR_SUFFIXES),
    "weekly_sidecars": list(WEEK_PROMPT_SIDECAR_NAMES),
    "automatic": {
        "enabled": False,
        "provider": "gemini",
        "model": GEMINI_META_PROMPT_MODEL,
        "fail_open": True,
        "default_per_source_output_suffix": ".analysis.md",
        "default_weekly_output_name": "week.analysis.md",
        "max_chars_per_source": 12000,
        "max_total_chars": 24000,
    },
}
DEFAULT_AUDIO_PROMPT_FRAMEWORK = {
    "enabled": True,
    "heading": "Generation rules:",
    "shared_rules": [
        "Explain the material as a line of thought, not as a disconnected recap.",
        "Distinguish clearly between what the source explicitly argues and what you are inferring from context.",
        "Do not invent studies, examples, citations, or author positions that are not grounded in the supplied material.",
        "Prioritize conceptual tensions, assumptions, and stakes over exhaustive detail lists.",
    ],
    "format_guidance": {
        "deep-dive": [
            "Build a cumulative explanation with a clear argumentative arc rather than a list of points.",
            "Spend time on why the distinctions matter, not only on naming them.",
        ],
        "brief": [
            "Compress aggressively around the central claim and one or two decisive distinctions.",
            "Omit secondary branches unless they change the main interpretation.",
        ],
        "critique": [
            "Surface internal tensions, blind spots, and limitations explicitly, but do not caricature the source.",
            "Anchor critique in the source's own claims and assumptions.",
        ],
        "debate": [
            "Stage the strongest competing interpretations fairly before taking a side.",
            "Make disagreements explicit and explain what turns on them.",
        ],
    },
    "length_guidance": {
        "short": [
            "Aim for a dense explanation with very little repetition.",
            "Prioritize the one or two takeaways a student must remember.",
        ],
        "default": [
            "Use enough space to explain the main distinctions and their stakes without drifting.",
        ],
        "long": [
            "Take time to unfold the argument step by step and connect it to broader theoretical stakes.",
            "Use repetition only when it clarifies a difficult distinction.",
        ],
    },
}


def _deep_copy_prompt_defaults(value: object) -> object:
    if isinstance(value, dict):
        return {key: _deep_copy_prompt_defaults(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy_prompt_defaults(item) for item in value]
    return value


def _normalize_string_list(section: str, field: str, value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(f"{section}.{field} must be a list of strings.")
    cleaned = [item.strip() for item in value if item.strip()]
    if not cleaned:
        raise SystemExit(f"{section}.{field} must contain at least one non-empty string.")
    return cleaned


def normalize_audio_prompt_strategy(raw: object) -> dict:
    defaults = _deep_copy_prompt_defaults(DEFAULT_AUDIO_PROMPT_STRATEGY)
    if raw in (None, ""):
        return defaults
    if not isinstance(raw, dict):
        raise SystemExit("audio_prompt_strategy must be an object.")

    normalized = defaults
    for field in ("audience", "tone"):
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, str):
            raise SystemExit(f"audio_prompt_strategy.{field} must be a string.")
        stripped = value.strip()
        if stripped:
            normalized[field] = stripped

    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("audio_prompt_strategy.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]

    if "source_roles" in raw:
        source_roles = raw["source_roles"]
        if not isinstance(source_roles, dict):
            raise SystemExit("audio_prompt_strategy.source_roles must be an object.")
        for role in ("slides", "readings"):
            if role not in source_roles:
                continue
            value = source_roles[role]
            if not isinstance(value, str):
                raise SystemExit(f"audio_prompt_strategy.source_roles.{role} must be a string.")
            stripped = value.strip()
            if stripped:
                normalized["source_roles"][role] = stripped

    if "prompt_types" in raw:
        prompt_types = raw["prompt_types"]
        if not isinstance(prompt_types, dict):
            raise SystemExit("audio_prompt_strategy.prompt_types must be an object.")
        unknown = sorted(set(prompt_types) - set(AUDIO_PROMPT_TYPES))
        if unknown:
            raise SystemExit(
                "Unknown audio prompt type(s): "
                + ", ".join(unknown)
                + ". Allowed: "
                + ", ".join(AUDIO_PROMPT_TYPES)
            )
        for prompt_type, prompt_cfg in prompt_types.items():
            if not isinstance(prompt_cfg, dict):
                raise SystemExit(f"audio_prompt_strategy.prompt_types.{prompt_type} must be an object.")
            if "lead" in prompt_cfg:
                value = prompt_cfg["lead"]
                if not isinstance(value, str):
                    raise SystemExit(
                        f"audio_prompt_strategy.prompt_types.{prompt_type}.lead must be a string."
                    )
                normalized["prompt_types"][prompt_type]["lead"] = value.strip()
            if "focus" in prompt_cfg:
                normalized["prompt_types"][prompt_type]["focus"] = _normalize_string_list(
                    f"audio_prompt_strategy.prompt_types.{prompt_type}",
                    "focus",
                    prompt_cfg["focus"],
                )
    return normalized


def normalize_exam_focus(raw: object) -> dict:
    defaults = _deep_copy_prompt_defaults(DEFAULT_EXAM_FOCUS)
    if raw in (None, ""):
        return defaults
    if not isinstance(raw, dict):
        raise SystemExit("exam_focus must be an object.")

    normalized = defaults
    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("exam_focus.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]
    if "heading" in raw:
        if not isinstance(raw["heading"], str):
            raise SystemExit("exam_focus.heading must be a string.")
        stripped = raw["heading"].strip()
        if stripped:
            normalized["heading"] = stripped
    if "prompt_types" in raw:
        prompt_types = raw["prompt_types"]
        if not isinstance(prompt_types, dict):
            raise SystemExit("exam_focus.prompt_types must be an object.")
        unknown = sorted(set(prompt_types) - set(AUDIO_PROMPT_TYPES))
        if unknown:
            raise SystemExit(
                "Unknown exam focus prompt type(s): "
                + ", ".join(unknown)
                + ". Allowed: "
                + ", ".join(AUDIO_PROMPT_TYPES)
            )
        for prompt_type, items in prompt_types.items():
            normalized["prompt_types"][prompt_type] = _normalize_string_list(
                f"exam_focus.prompt_types.{prompt_type}",
                "items",
                items,
            )
    return normalized


def normalize_meta_prompting(raw: object) -> dict:
    defaults = _deep_copy_prompt_defaults(DEFAULT_META_PROMPTING)
    if raw in (None, ""):
        return defaults
    if not isinstance(raw, dict):
        raise SystemExit("meta_prompting must be an object.")

    normalized = defaults
    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("meta_prompting.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]
    if "heading" in raw:
        if not isinstance(raw["heading"], str):
            raise SystemExit("meta_prompting.heading must be a string.")
        stripped = raw["heading"].strip()
        if stripped:
            normalized["heading"] = stripped
    if "per_source_suffixes" in raw:
        normalized["per_source_suffixes"] = _normalize_string_list(
            "meta_prompting",
            "per_source_suffixes",
            raw["per_source_suffixes"],
        )
    if "weekly_sidecars" in raw:
        normalized["weekly_sidecars"] = _normalize_string_list(
            "meta_prompting",
            "weekly_sidecars",
            raw["weekly_sidecars"],
        )
    if "automatic" in raw:
        automatic = raw["automatic"]
        if not isinstance(automatic, dict):
            raise SystemExit("meta_prompting.automatic must be an object.")
        for field in ("enabled", "fail_open"):
            if field not in automatic:
                continue
            if not isinstance(automatic[field], bool):
                raise SystemExit(f"meta_prompting.automatic.{field} must be true or false.")
            normalized["automatic"][field] = automatic[field]
        for field in (
            "provider",
            "model",
            "default_per_source_output_suffix",
            "default_weekly_output_name",
        ):
            if field not in automatic:
                continue
            value = automatic[field]
            if not isinstance(value, str):
                raise SystemExit(f"meta_prompting.automatic.{field} must be a string.")
            stripped = value.strip()
            if stripped:
                normalized["automatic"][field] = stripped
        for field in ("max_chars_per_source", "max_total_chars"):
            if field not in automatic:
                continue
            value = automatic[field]
            if not isinstance(value, int) or value < 1:
                raise SystemExit(f"meta_prompting.automatic.{field} must be an integer >= 1.")
            normalized["automatic"][field] = value

    auto = normalized["automatic"]
    provider = str(auto["provider"]).strip().lower()
    if provider not in {"gemini", "anthropic"}:
        raise SystemExit("meta_prompting.automatic.provider must be 'gemini' or 'anthropic'.")
    auto["provider"] = provider
    if provider == "gemini":
        auto["model"] = GEMINI_META_PROMPT_MODEL
    source_suffix = str(auto["default_per_source_output_suffix"]).strip()
    if not source_suffix.startswith("."):
        raise SystemExit(
            "meta_prompting.automatic.default_per_source_output_suffix must start with '.'."
        )
    weekly_name = str(auto["default_weekly_output_name"]).strip()
    if "/" in weekly_name or "\\" in weekly_name:
        raise SystemExit(
            "meta_prompting.automatic.default_weekly_output_name must be a plain filename."
        )

    per_source_suffixes = list(dict.fromkeys(normalized["per_source_suffixes"]))
    weekly_sidecars = list(dict.fromkeys(normalized["weekly_sidecars"]))
    if source_suffix not in per_source_suffixes:
        per_source_suffixes.append(source_suffix)
    if weekly_name not in weekly_sidecars:
        weekly_sidecars.append(weekly_name)
    normalized["per_source_suffixes"] = per_source_suffixes
    normalized["weekly_sidecars"] = weekly_sidecars
    return normalized


def normalize_audio_prompt_framework(raw: object) -> dict:
    defaults = _deep_copy_prompt_defaults(DEFAULT_AUDIO_PROMPT_FRAMEWORK)
    if raw in (None, ""):
        return defaults
    if not isinstance(raw, dict):
        raise SystemExit("audio_prompt_framework must be an object.")

    normalized = defaults
    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("audio_prompt_framework.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]
    if "heading" in raw:
        if not isinstance(raw["heading"], str):
            raise SystemExit("audio_prompt_framework.heading must be a string.")
        stripped = raw["heading"].strip()
        if stripped:
            normalized["heading"] = stripped
    if "shared_rules" in raw:
        normalized["shared_rules"] = _normalize_string_list(
            "audio_prompt_framework",
            "shared_rules",
            raw["shared_rules"],
        )
    for field, allowed in (
        ("format_guidance", AUDIO_FORMAT_VALUES),
        ("length_guidance", AUDIO_LENGTH_VALUES),
    ):
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, dict):
            raise SystemExit(f"audio_prompt_framework.{field} must be an object.")
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise SystemExit(
                f"Unknown audio_prompt_framework.{field} key(s): "
                + ", ".join(unknown)
                + ". Allowed: "
                + ", ".join(sorted(allowed))
            )
        for key, items in value.items():
            normalized[field][key] = _normalize_string_list(
                f"audio_prompt_framework.{field}.{key}",
                "items",
                items,
            )
    return normalized


def ensure_prompt(_: str, value: str) -> str:
    return value.strip()


def _canonicalize_lecture_key(value: str) -> str:
    match = re.fullmatch(r"\s*W?0*(\d{1,2})L0*(\d{1,2})\s*", value, re.IGNORECASE)
    if not match:
        return value.strip().upper()
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def is_prompt_sidecar_file(path: Path, meta_prompting: dict | None = None) -> bool:
    config = meta_prompting or DEFAULT_META_PROMPTING
    if path.name in set(config["weekly_sidecars"]):
        return True
    return any(path.name.endswith(suffix) for suffix in config["per_source_suffixes"])


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def _source_prompt_sidecar_candidates(source_path: Path, meta_prompting: dict) -> list[Path]:
    candidates: list[Path] = []
    stem_base = source_path.with_suffix("")
    seen: set[Path] = set()
    for suffix in meta_prompting["per_source_suffixes"]:
        for candidate in (
            source_path.parent / f"{source_path.name}{suffix}",
            stem_base.parent / f"{stem_base.name}{suffix}",
        ):
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _week_prompt_sidecar_candidates(week_dir: Path, week_label: str | None, meta_prompting: dict) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    label = _canonicalize_lecture_key(week_label or "")
    names = list(meta_prompting["weekly_sidecars"])
    if label:
        for suffix in meta_prompting["per_source_suffixes"]:
            names.append(f"{label}{suffix}")
    for name in names:
        candidate = week_dir / name
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


def _read_prompt_sidecars(
    candidates: list[Path],
    meta_note_overrides: dict[Path, str] | None = None,
) -> str:
    sections: list[str] = []
    for path in candidates:
        if meta_note_overrides and path in meta_note_overrides:
            content = str(meta_note_overrides[path]).strip()
        else:
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
        if not content:
            continue
        sections.append(f"[{path.name}]\n{content}")
    return "\n\n".join(sections)


def build_audio_prompt(
    *,
    prompt_type: str,
    prompt_strategy: dict | None,
    exam_focus: dict | None,
    prompt_framework: dict | None,
    meta_prompting: dict | None,
    meta_note_overrides: dict[Path, str] | None = None,
    custom_prompt: str,
    audio_format: str | None = None,
    audio_length: str | None = None,
    source_item: object | None = None,
    source_items: list[object] | None = None,
    week_dir: Path | None = None,
    week_label: str | None = None,
) -> str:
    if prompt_type not in AUDIO_PROMPT_TYPES:
        raise ValueError(
            f"Unknown audio prompt type '{prompt_type}'. Allowed: {', '.join(AUDIO_PROMPT_TYPES)}."
        )
    custom_prompt = ensure_prompt("audio", custom_prompt)
    notes = ""
    if meta_prompting and meta_prompting.get("enabled", False):
        if source_item is not None:
            source_path = getattr(source_item, "path", None)
            if isinstance(source_path, Path):
                notes = _read_prompt_sidecars(
                    _source_prompt_sidecar_candidates(source_path, meta_prompting),
                    meta_note_overrides=meta_note_overrides,
                )
        elif source_items is not None and week_dir is not None:
            notes = _read_prompt_sidecars(
                _week_prompt_sidecar_candidates(week_dir, week_label, meta_prompting),
                meta_note_overrides=meta_note_overrides,
            )

    sections: list[str] = []
    if prompt_strategy and prompt_strategy.get("enabled", False):
        prompt_type_cfg = prompt_strategy["prompt_types"][prompt_type]
        sections.append(
            f"Create a deep-dive audio overview for {prompt_strategy['audience']}."
        )
        lead = str(prompt_type_cfg.get("lead") or "").strip()
        if lead:
            sections.append(lead)
        if prompt_type == "mixed_sources":
            sections.append(
                "Source roles:\n"
                f"- Slides: {prompt_strategy['source_roles']['slides']}\n"
                f"- Readings: {prompt_strategy['source_roles']['readings']}"
            )
        elif prompt_type == "short" and getattr(source_item, "source_type", None) == "slide":
            sections.append(
                "Because the source is a slide deck, reconstruct the argumentative line instead of paraphrasing bullet fragments."
            )
        sections.append(f"Focus on:\n{_format_bullets(prompt_type_cfg['focus'])}")

    if exam_focus and exam_focus.get("enabled", False):
        exam_items = exam_focus["prompt_types"].get(prompt_type) or []
        if exam_items:
            sections.append(f"{exam_focus['heading']}\n{_format_bullets(exam_items)}")

    if prompt_framework and prompt_framework.get("enabled", False):
        framework_rules = list(prompt_framework.get("shared_rules") or [])
        normalized_audio_format = str(audio_format or "").strip().lower()
        normalized_audio_length = str(audio_length or "").strip().lower()
        if normalized_audio_format:
            framework_rules.extend(
                prompt_framework.get("format_guidance", {}).get(normalized_audio_format, [])
            )
        if normalized_audio_length:
            framework_rules.extend(
                prompt_framework.get("length_guidance", {}).get(normalized_audio_length, [])
            )
        if framework_rules:
            sections.append(
                f"{prompt_framework['heading']}\n{_format_bullets(framework_rules)}"
            )

    if prompt_strategy and prompt_strategy.get("enabled", False):
        sections.append(f"Tone: {prompt_strategy['tone']}")

    if custom_prompt:
        sections.append(f"Additional instructions:\n{custom_prompt}")
    if notes:
        heading = (
            meta_prompting["heading"]
            if meta_prompting and meta_prompting.get("enabled", False)
            else "External pre-analysis:"
        )
        sections.append(f"{heading}\n{notes}")
    return "\n\n".join(section for section in sections if section.strip())
