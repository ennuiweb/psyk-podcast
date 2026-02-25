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

- Keep title + intro in the same visual block as semester controls.
- Semester control is top-level context, not a separate full section.

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

### Overview and next action

- Use compact overview KPI cards for progress orientation.
- Keep `Næste fokus` as the primary directional block.
- Use one primary CTA (`Start nu`) when available.
- Optional secondary CTA can link to Spotify episode for the active lecture context.

### Learning path timeline

- Render lectures as a timeline of `timeline-item` rows with collapsed-by-default lecture details.
- Keep status explicit with text labels (`Aktiv`, `Fuldført`, `Låst`, `Ingen quiz`), not color alone.
- Keep per-lecture and per-reading progress bars plus numeric counts.
- Keep `Udvid alle` and `Luk alle` as neutral productivity controls.
- Preserve open lecture state in local browser storage for continuity.

## Component hierarchy

- Primary button: `btn-primary` (high emphasis actions).
- Secondary page CTA: `subject-open-link`.
- Neutral action: `subject-toggle-button`.
- Header utility actions: `nav-action` (separate role from content CTA).

## Accessibility baseline

- Minimum target size for interactive controls: `44px` height.
- Preserve visible keyboard focus (`:focus-visible`) on links, buttons, and form controls.
- Do not communicate status by color alone where text labels exist.
- Treat the `44px` target as a baseline, not a soft recommendation.

## Implementation notes

- Main implementation lives in:
  - `templates/quizzes/progress.html`
  - `templates/quizzes/subject_detail.html`
  - `templates/base.html`
- Keep these patterns aligned if related templates are refactored.

## Change checklist for future UI updates

1. Keep spacing/radius on the documented scale.
2. Keep control hierarchy explicit (primary vs secondary vs neutral).
3. Reuse existing section models (`/progress`, `/subjects/<slug>`) before adding new standalone blocks.
4. Validate keyboard focus and mobile tap target sizes.
5. Update this document when interface conventions change.
