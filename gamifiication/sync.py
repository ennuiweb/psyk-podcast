#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from anki_client import AnkiClient, AnkiConnectError
from config import AppConfig, ConfigError, RenderConfig, UnitConfig, load_config
from habitica_client import HabiticaClient, HabiticaError
from ingest import (
    IngestError,
    build_anki_notes,
    extract_cards_with_mock,
    extract_cards_with_openai,
    read_source_text,
)
from renderers import RenderError, render_html_state, update_canvas_state
from state import atomic_write_state, derive_unit_status_updates, load_state


@dataclass(frozen=True)
class DailyOutcome:
    reviews_today: int
    min_daily_reviews: int
    passed: bool
    missing_reviews: int
    score_direction: str
    score_events: int
    projected_xp: float
    projected_gold: float
    projected_damage: float


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _anki_quote(value: str) -> str:
    escaped = value.replace('"', r'\"')
    return f'"{escaped}"'


def evaluate_daily_outcome(*, reviews_today: int, config: AppConfig) -> DailyOutcome:
    minimum = config.sync.min_daily_reviews
    missing_reviews = max(0, minimum - reviews_today)
    passed = reviews_today >= minimum

    if passed:
        score_events = max(1, reviews_today // config.habitica.reviews_per_score_up)
        score_direction = "up"
    else:
        score_events = max(1, math.ceil(missing_reviews / config.habitica.missing_reviews_per_score_down))
        score_direction = "down"

    projected_xp = round(reviews_today * config.habitica.xp_per_review, 2)
    projected_gold = round(reviews_today * config.habitica.gold_per_review, 2)
    projected_damage = round(
        min(config.habitica.max_damage, missing_reviews * config.habitica.damage_per_missing_review),
        2,
    )

    return DailyOutcome(
        reviews_today=reviews_today,
        min_daily_reviews=minimum,
        passed=passed,
        missing_reviews=missing_reviews,
        score_direction=score_direction,
        score_events=score_events,
        projected_xp=projected_xp,
        projected_gold=projected_gold,
        projected_damage=projected_damage,
    )


def collect_unit_progress(anki_client: AnkiClient, *, sync_deck_name: str, units: list[UnitConfig], mastery_interval_days: int) -> dict[str, dict[str, Any]]:
    progress: dict[str, dict[str, Any]] = {}
    for unit in units:
        base_query = f"deck:{_anki_quote(sync_deck_name)} tag:{_anki_quote(unit.anki_tag)}"
        mastered_query = f"{base_query} prop:ivl>={mastery_interval_days}"

        total_cards = len(anki_client.find_cards(base_query))
        mastered_cards = len(anki_client.find_cards(mastered_query))

        progress[unit.id] = {
            "total_cards": total_cards,
            "mastered_cards": mastered_cards,
        }
    return progress


def run_check_anki(args: argparse.Namespace, config: AppConfig) -> int:
    _ = args
    anki = AnkiClient(config.anki.endpoint)
    reviews_today = anki.get_num_cards_reviewed_today()
    print(reviews_today)
    return 0


def run_ingest(args: argparse.Namespace, config: AppConfig) -> int:
    source_file = Path(args.input).expanduser().resolve()
    text = read_source_text(source_file)
    if args.text_limit_chars and args.text_limit_chars > 0:
        text = text[: args.text_limit_chars]

    provider = args.provider or config.ingest.provider
    max_cards = args.max_cards or config.ingest.max_cards

    if provider == "mock":
        cards = extract_cards_with_mock(text, max_cards=max_cards)
    elif provider == "openai":
        api_key = os.getenv(config.ingest.api_key_env, "").strip()
        if not api_key:
            raise IngestError(
                f"Missing API key environment variable: {config.ingest.api_key_env}"
            )
        cards = extract_cards_with_openai(
            text=text,
            api_key=api_key,
            model=config.ingest.model,
            max_cards=max_cards,
        )
    else:
        raise IngestError(f"Unsupported provider: {provider}")

    unit_tag = (args.unit_tag or config.ingest.default_unit_tag).strip()
    tags: list[str] = []
    for candidate in [*config.anki.default_tags, unit_tag, *(args.tag or [])]:
        cleaned = str(candidate).strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)

    notes = build_anki_notes(
        cards=cards,
        deck_name=config.anki.deck_name,
        note_model=config.anki.note_model,
        front_field=config.anki.front_field,
        back_field=config.anki.back_field,
        tags=tags,
    )

    if args.dry_run:
        payload = {
            "mode": "dry_run",
            "provider": provider,
            "source_file": str(source_file),
            "cards_generated": len(cards),
            "tags": tags,
            "notes": notes,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    anki = AnkiClient(config.anki.endpoint)
    inserted_ids = anki.add_notes(notes)

    added = 0
    failed = 0
    for note_id in inserted_ids:
        if note_id is None:
            failed += 1
        else:
            added += 1

    payload = {
        "mode": "live",
        "provider": provider,
        "source_file": str(source_file),
        "cards_generated": len(cards),
        "notes_added": added,
        "notes_failed": failed,
        "tags": tags,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if added > 0 else 1


def _apply_habitica_scores(
    *,
    config: AppConfig,
    outcome: DailyOutcome,
    dry_run: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    result: dict[str, Any] = {
        "enabled": True,
        "task_id": config.habitica.task_id,
        "direction": outcome.score_direction,
        "planned_events": outcome.score_events,
        "applied_events": 0,
    }

    if dry_run:
        result["mode"] = "dry_run"
        result["applied_events"] = outcome.score_events
        return result, errors

    if config.habitica.task_id.upper().startswith("REPLACE_"):
        result["enabled"] = False
        result["mode"] = "disabled"
        errors.append(
            "Habitica task_id is still a placeholder. Set habitica.task_id in config to enable scoring."
        )
        return result, errors

    try:
        habitica = HabiticaClient.from_env(
            api_base=config.habitica.api_base,
            user_id_env=config.habitica.user_id_env,
            api_token_env=config.habitica.api_token_env,
        )
    except HabiticaError as exc:
        errors.append(str(exc))
        result["enabled"] = False
        result["mode"] = "disabled"
        return result, errors

    result["mode"] = "live"
    for _ in range(outcome.score_events):
        try:
            habitica.score_task(config.habitica.task_id, outcome.score_direction)
            result["applied_events"] = int(result["applied_events"]) + 1
        except HabiticaError as exc:
            errors.append(str(exc))
            break

    return result, errors


def _render_outputs(*, config: AppConfig, state: dict[str, Any]) -> dict[str, Any]:
    if config.render.mode == "none":
        return {"mode": "none", "output": None}
    if config.render.mode == "html":
        output = render_html_state(state, render_config=config.render)
        return {"mode": "html", "output": str(output)}
    if config.render.mode == "canvas":
        output, updated_nodes = update_canvas_state(state, render_config=config.render)
        return {
            "mode": "canvas",
            "output": str(output),
            "updated_nodes": updated_nodes,
        }
    raise RenderError(f"Unsupported render mode: {config.render.mode}")


def run_sync(args: argparse.Namespace, config: AppConfig) -> int:
    anki = AnkiClient(config.anki.endpoint)
    state = load_state(config.sync.state_file, config.sync.units)

    reviews_today = anki.get_num_cards_reviewed_today()
    outcome = evaluate_daily_outcome(reviews_today=reviews_today, config=config)

    habitica_result, habitica_errors = _apply_habitica_scores(
        config=config,
        outcome=outcome,
        dry_run=args.dry_run,
    )

    unit_progress = collect_unit_progress(
        anki,
        sync_deck_name=config.sync.deck_name,
        units=config.sync.units,
        mastery_interval_days=config.sync.mastery_interval_days,
    )
    current_level, normalized_units = derive_unit_status_updates(
        units=config.sync.units,
        unit_progress=unit_progress,
        mastery_ratio_threshold=config.sync.mastery_ratio_threshold,
    )

    state["current_level"] = current_level
    state["units"] = normalized_units
    state["daily"] = {
        "reviews_today": outcome.reviews_today,
        "min_daily_reviews": outcome.min_daily_reviews,
        "passed": outcome.passed,
        "missing_reviews": outcome.missing_reviews,
        "projected_xp": outcome.projected_xp,
        "projected_gold": outcome.projected_gold,
        "projected_damage": outcome.projected_damage,
    }
    state["habitica"] = habitica_result
    state["last_sync"] = _utc_now_iso()

    sync_errors = [*habitica_errors]
    render_result: dict[str, Any] = {"mode": "none", "output": None}

    if args.dry_run:
        render_result = {"mode": config.render.mode, "output": "skipped-dry-run"}
    else:
        try:
            render_result = _render_outputs(config=config, state=state)
        except RenderError as exc:
            sync_errors.append(str(exc))
            render_result = {"mode": config.render.mode, "output": None}

    state["last_sync_errors"] = sync_errors

    if not args.dry_run:
        atomic_write_state(config.sync.state_file, state)

    payload = {
        "mode": "dry_run" if args.dry_run else "live",
        "state_file": str(config.sync.state_file),
        "reviews_today": outcome.reviews_today,
        "pass_condition": outcome.passed,
        "missing_reviews": outcome.missing_reviews,
        "habitica": habitica_result,
        "render": render_result,
        "current_level": current_level,
        "errors": sync_errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


def run_render(args: argparse.Namespace, config: AppConfig) -> int:
    state = load_state(config.sync.state_file, config.sync.units)

    # Optional one-off override if caller wants to force a renderer.
    if args.mode:
        render_mode = args.mode.strip().lower()
        if render_mode not in {"none", "html", "canvas"}:
            raise RenderError("--mode must be one of: none, html, canvas")
        config = AppConfig(
            anki=config.anki,
            habitica=config.habitica,
            sync=config.sync,
            ingest=config.ingest,
            render=RenderConfig(
                mode=render_mode,
                html_template=config.render.html_template,
                html_output=config.render.html_output,
                canvas_file=config.render.canvas_file,
            ),
        )

    render_result = _render_outputs(config=config, state=state)
    payload = {
        "mode": "live",
        "state_file": str(config.sync.state_file),
        "render": render_result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gamified SRS pipeline orchestrator")
    parser.add_argument(
        "--config",
        default="gamifiication/config.local.json",
        help="Path to JSON configuration file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_anki = subparsers.add_parser(
        "check-anki",
        help="Print Anki getNumCardsReviewedToday and exit.",
    )
    check_anki.set_defaults(handler=run_check_anki)

    ingest = subparsers.add_parser("ingest", help="Extract cards from source text/PDF and add to Anki.")
    ingest.add_argument("--input", required=True, help="Path to source text (.txt/.md) or PDF file.")
    ingest.add_argument(
        "--provider",
        choices=["openai", "mock"],
        help="Override ingestion provider from config.",
    )
    ingest.add_argument("--unit-tag", help="Unit tag to attach to generated notes.")
    ingest.add_argument(
        "--tag",
        action="append",
        help="Additional tag(s) to append. Can be repeated.",
    )
    ingest.add_argument("--max-cards", type=int, help="Override max number of cards to generate.")
    ingest.add_argument(
        "--text-limit-chars",
        type=int,
        default=24000,
        help="Trim source text before prompting the LLM (0 disables trimming).",
    )
    ingest.add_argument("--dry-run", action="store_true", help="Generate notes without writing to Anki.")
    ingest.set_defaults(handler=run_ingest)

    sync = subparsers.add_parser(
        "sync",
        help="Run daily sync: Anki reviews -> Habitica scoring + state/render updates.",
    )
    sync.add_argument("--dry-run", action="store_true", help="Read-only mode (no Habitica/state/render writes).")
    sync.set_defaults(handler=run_sync)

    render = subparsers.add_parser("render", help="Render the current local semester state.")
    render.add_argument("--mode", choices=["none", "html", "canvas"], help="Override renderer mode.")
    render.set_defaults(handler=run_render)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
        handler = args.handler
        return handler(args, config)
    except (ConfigError, AnkiConnectError, HabiticaError, IngestError, RenderError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
