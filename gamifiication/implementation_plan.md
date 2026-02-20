# Implementation Plan: Gamified SRS Pipeline

## Goal
Deliver a robust local pipeline that converts study material into Anki cards, translates daily review performance into Habitica gamification events, and renders visible progression with minimal moving parts.

## Scope boundary
- Implement only the pipeline described in `Gamified SRS Pipeline.md`.
- Keep architecture lightweight (Python scripts + JSON state + API calls).
- Avoid building web apps/frontend frameworks.

## Delivery phases
1. **Foundation & config hardening**
- Define explicit typed config (`config.py`) with strict validation.
- Resolve all file paths relative to config location.
- Fail fast on malformed config, but preserve runtime degradations for optional components.

2. **Ingestion path (PDF/Text -> LLM -> Anki)**
- Implement source readers (`.txt/.md` native, `.pdf` via optional `pypdf`).
- Implement extraction providers:
  - `openai` for production.
  - `mock` for no-network fallback and deterministic local testing.
- Validate card schema before write (`front`/`back` non-empty).
- Write via AnkiConnect `addNotes` with unit and default tags.

3. **Sync engine (Anki -> Habitica + state)**
- Fetch `getNumCardsReviewedToday` from Anki.
- Evaluate pass/fail against `min_daily_reviews`.
- Map outcome to Habitica up/down score events with configurable scaling.
- Update `semester_state.json` atomically to avoid partial writes.

4. **Mastery progression model**
- Query per-unit total cards and mastered cards (`prop:ivl>=N`).
- Compute `mastery_ratio` and derive status progression:
  - `completed` if ratio >= threshold
  - first incomplete = `active`
  - following units = `locked`
- Persist normalized per-unit metrics for auditability.

5. **Renderer outputs**
- HTML renderer (Jinja2 template) for quick visual path.
- Optional Obsidian canvas updater by mutating node text/color by status.
- Rendering errors must not block state updates.

6. **Testing & validation**
- Unit tests for:
  - card payload parsing/validation
  - daily scoring logic
  - unit-status derivation
  - config validation edge cases
- Dry-run support for ingestion/sync to validate behavior without external writes.

## Error-mitigation strategy
- **Network/API failures**: catch and report; continue non-dependent stages.
- **Credential failures**: disable Habitica interaction but continue local state sync.
- **Schema drift**: validate all external payloads (Anki/Habitica/LLM) before use.
- **File corruption risk**: atomic state writes via temp file + replace.
- **Optional dependency failures**: clear actionable errors (`Jinja2`, `pypdf`) without stack noise.

## Operational safeguards
- `sync --dry-run` for safe preflight checks.
- Structured JSON command outputs for easier cron log parsing.
- `last_sync_errors` in state file for persistent diagnostics.

## Maintainability controls
- Module boundaries by concern (`ingest`, `state`, `renderers`, clients).
- Typed dataclasses for config contract.
- Deterministic pure functions for core logic (easy unit testing).
- Minimal dependency surface (`requests` + optional `Jinja2`/`pypdf`).

## Acceptance criteria
- `check-anki` prints review count when Anki is available.
- `ingest --dry-run` emits valid note payload without touching Anki.
- `sync --dry-run` evaluates pass/fail and mastery without external writes.
- `sync` writes/upserts `semester_state.json` and records errors when integrations fail.
- `render` produces configured HTML/canvas output from state.
