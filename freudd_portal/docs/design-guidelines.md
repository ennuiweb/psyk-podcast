# Freudd Portal Design Guidelines

Last updated: 2026-02-25

## Purpose

This document captures the current UI direction and reusable interface patterns for `freudd_portal`, with focus on the learner dashboard (`/progress`) and course detail page (`/subjects/<subject_slug>`).

## Direction and feel

- Calm, study-first interface.
- High clarity over decoration.
- Action-oriented hierarchy: users should quickly see what to do next.
- Consistent blue-accent system on light surfaces.

## Core visual system

### Spacing

- Base unit: `4px`.
- Working scale: `8px`, `12px`, `16px`, `24px`, `32px`.
- Avoid one-off spacing values unless required by content constraints.
- If one-off spacing is unavoidable, document the reason in the related change.

### Radius

- `10px`: compact controls.
- `12px`: nested sub-cards or grouped content blocks.
- `14px`: cards and table containers.
- `18px`: major sections.
- `22px`: top-level page card container (`.card`) in shared layout.
- `999px`: pills and rounded action buttons.

### Depth strategy

- Primary strategy: subtle borders for structure.
- Secondary strategy: very light shadow only on main containers.
- Avoid strong mixed shadow stacks.

## Progress page structure (`/progress`)

### Header block

- Keep title + intro in a compact visual block without extra global selectors.
- Keep the header lightweight and focused on orientation.

### Subjects section

- Use one section: `Mine fag`.
- Enrollment state and actions are inline per subject card.
- Keep one primary action (`Åbn fag`) and one secondary action (`Tilmeld`/`Afmeld`).
- Show `Senest åbnet fag` badge as quick orientation.

### Quiz history section

- Use `Quizhistorik` as section title.
- Keep table semantics, but optimize scanability:
  - clamped title lines,
  - compact quiz id line,
  - difficulty chip,
  - status pill with dot,
  - answer progress bar + numeric ratio,
  - fixed datetime formatting.

## Subject detail structure (`/subjects/<subject_slug>`)

### Header and orientation

- Keep subject title/description and enrollment status in the top header block.
- Keep the return navigation (`Tilbage til min side`) as a utility action.
- Keep actions in this page focused on learning flow, not enrollment mutation.

### Overview

- Use compact overview KPI cards for progress orientation.
- Avoid separate hero blocks for "next step" direction.
- Keep actions close to the lecture/reading assets in the timeline.

### Learning path timeline

- Render lectures as a timeline of `timeline-item` rows with collapsed-by-default lecture details.
- Keep one action-first CTA in lecture headers (`Start næste quiz`) so the next step is always visible.
- Use text status labels only when they differentiate state (`Fuldført`, `Ingen quiz`); do not render `Aktiv` labels by default.
- Keep per-lecture and per-reading numeric progress counts; replace 0% bars with `Ikke startet endnu`.
- Order difficulty actions `Let` -> `Mellem` -> `Svær` and reinforce with difficulty-specific color/icon coding.
- Keep timeline connectors context-aware: connector from a lecture is accented only when that lecture is completed.
- Keep compact spacing rhythm in expanded panels: denser inner padding/gaps than lecture headers.
- Keep `Udvid alle` and `Luk alle` as neutral productivity controls.
- Preserve open lecture state in local browser storage for continuity.

## Quiz wrapper structure (`/q/<quiz_id>.html`)

### Header identity

- Render quiz identity as two levels: module label (`Uge x, forelæsning x`) and cleaned quiz title.
- Show metadata as compact chips (for example `Lyd`, `Deep dive`, `EN`) plus explicit difficulty and quiz id.
- Avoid exposing raw file metadata in the visible title (`{type=...}`, hash fragments, file extensions).

### Question flow

- Keep question stage action-first and focused on one decision at a time.
- Show lightweight flow feedback (`Spørgsmål x/y`, `Besvaret x/y`, and a compact progress bar).
- Answer options should keep strong hit areas and clear selected/correct/wrong states without relying on color alone.

## Component hierarchy

- Primary button: `btn-primary` (high emphasis actions).
- Secondary page CTA: `subject-open-link`.
- Neutral action: `subject-toggle-button`.
- Header utility actions: `nav-action` (separate role from content CTA).

## Accessibility baseline

- Primary, secondary, and neutral controls use minimum target size `44px` height.
- Dense content chips (quiz/podcast links in timeline blocks) may use `32-36px` height when spacing/focus remains clear.
- Preserve visible keyboard focus (`:focus-visible`) on links, buttons, and form controls.
- Do not communicate status by color alone where text labels exist.
- Difficulty chips may use color as the primary cue because each chip retains a textual level label.

## Implementation notes

- Shared primitives in `templates/base.html` enforce spacing/radius/depth/focus baselines portal-wide.
- Main implementation lives in:
  - `templates/quizzes/progress.html`
  - `templates/quizzes/subject_detail.html`
  - `templates/quizzes/wrapper.html`
  - `templates/base.html`
  - `templates/registration/login.html`
  - `templates/registration/signup.html`
- Keep these patterns aligned if related templates are refactored.

## Change checklist for future UI updates

1. Keep spacing/radius on the documented scale.
2. Keep control hierarchy explicit (primary vs secondary vs neutral).
3. Reuse existing section models (`/progress`, `/subjects/<slug>`) before adding new standalone blocks.
4. Validate keyboard focus and mobile tap target sizes.
5. Update this document when interface conventions change.
