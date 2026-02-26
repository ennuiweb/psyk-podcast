# Freudd Portal Design System

Last updated: 2026-02-26

## Purpose

This design system defines the product-facing and implementation-facing UI rules for `freudd_portal`. It turns the goals in `docs/non-technical-overview.md` into reusable visual language and component behavior.

Source alignment:
- Product intent: `docs/non-technical-overview.md`
- Shared primitives: `templates/base.html`
- Page patterns: `templates/quizzes/progress.html`, `templates/quizzes/subject_detail.html`, `templates/quizzes/wrapper.html`
- Auth patterns: `templates/registration/login.html`, `templates/registration/signup.html`
- External reference method: `ui-ux-pro-max` skill searches (style, color, typography, UX)

## Product intent -> design requirements

Freudd Portal exists to add identity, memory, progression, and motivation on top of static quiz content. The UI therefore must always make these five jobs visible:

1. Identity: learner sees personal context quickly.
2. Continuity: learner sees where they left off and can resume fast.
3. Progression: learner sees completed vs pending in a clear sequence.
4. Motivation: learner effort is reflected in status and achievement cues.
5. Coherence: quizzes, readings, and podcast assets feel like one journey.

## Experience principles

1. Study-first clarity: keep visual noise low, keep decisions obvious.
2. One primary action per block: each section highlights only one "next step".
3. Progress over decoration: status and momentum cues outrank ornamental effects.
4. Consistent semantics: same status always uses same words, colors, and shapes.
5. Mobile-first readability: dense information may exist, but scanning must stay easy on small screens.

## Visual language

The style direction is "calm educational dashboard" with accessibility-first behavior and restrained, flat-to-soft surfaces.

### Brand personality

- Reliable
- Focused
- Encouraging
- Practical

### Typography

- Heading font: `Space Grotesk` (`600-700`) for section hierarchy and labels that need authority.
- Body font: `Manrope` (`400-700`) for readability in dense learning content.
- Monospace utility: system monospace only for raw IDs/technical metadata (`.quiz-id`).

Usage rules:
- Keep heading line-height tight (`~1.1`) and body line-height comfortable (`~1.5`).
- Avoid decorative fonts in learner flows.
- Keep all UI copy in Danish until multilingual rollout is enabled.

### Color system (live tokens)

The current token set in `templates/base.html` is the source of truth.

| Role | Token | Value | Usage |
|---|---|---|---|
| App background | `--bg` | `#edf3fb` | Global page backdrop |
| Soft backdrop | `--bg-soft` | `#f8faff` | Supporting surface blocks |
| Main surface | `--surface` | `#ffffff` | Cards and forms |
| Soft surface | `--surface-soft` | `#f4f7ff` | Section containers |
| Strong surface | `--surface-strong` | `#e9efff` | Emphasized neutral fills |
| Primary text | `--ink` | `#1a2743` | Core readable text |
| Secondary text | `--muted` | `#607194` | Supportive metadata text |
| Primary accent | `--accent` | `#2f67e8` | Active/primary interactive state |
| Strong accent | `--accent-strong` | `#224fbd` | Link text and higher emphasis |
| Soft accent fill | `--accent-soft` | `#e4edff` | Hover/secondary emphasis |
| Accent on dark | `--accent-ink` | `#ffffff` | Text on accent backgrounds |
| Success | `--success` | `#1f8f4e` | Completed states |
| Danger | `--danger` | `#b23b4f` | Error/wrong states |
| Warning bg | `--warn-bg` | `#fff4de` | Caution banners |
| Warning border | `--warn-border` | `#f1c26b` | Caution boundaries |
| Warning text | `--warn-ink` | `#714b12` | Caution text |
| Border default | `--border` | `#d3ddf0` | Neutral card/section border |
| Border strong | `--border-strong` | `#b8c7e7` | Inputs and controls |
| Focus ring | `--focus-ring` | `rgba(47, 103, 232, 0.28)` | Keyboard-visible focus outline |

Color behavior rules:
- Blue accent indicates action/progression.
- Green indicates completion/success.
- Red indicates errors or incorrect answers.
- Never rely on color as the only state cue when a label can be shown.

### Spacing, radius, depth, motion

Spacing scale:
- `--space-1: 4px`
- `--space-2: 8px`
- `--space-3: 12px`
- `--space-4: 16px`
- `--space-5: 24px`
- `--space-6: 32px`

Radius scale:
- `--radius-sm: 10px`
- `--radius-sub: 12px`
- `--radius-md: 14px`
- `--radius-lg: 18px`
- `--radius-xl: 22px`
- `--radius-pill: 999px`

Depth:
- Main container shadow only: `--shadow-container`.
- Hover shadow only where needed: `--shadow-hover-subtle`.
- Prefer borders over heavy shadows.

Motion:
- Page/container entry: `~220ms` ease-out.
- Hover/focus transitions: `~140-160ms`.
- Respect reduced motion preferences when adding new animations.

## Layout system

### Global shell

- Sticky top navigation (`.site-header`) with blurred light background for orientation persistence.
- Constrained content width (`max-width: 1120px`) inside `.page-shell`.
- Single primary content card (`.card`) per route as default frame.

### Information density model

- Keep section stacks compact (`12-24px` rhythm).
- Keep metadata close to actions.
- Prefer grouped cards over long uninterrupted text blocks.

## Component system

### Action hierarchy

- Primary action: `.btn-primary` for commit/continue actions.
- Page-level secondary action: `.subject-open-link` for "open this subject" progression.
- Neutral utility action: `.nav-action`, `.subject-toggle-button`, `.ghost-button`, `.toolbar-btn`.

Rules:
- One primary action per local section.
- Secondary and neutral controls should not visually compete with primary.
- All interactive controls must keep pointer cursor and hover/focus states.

### Status and feedback

- `status-pill`, `status-badge`, `subject-status-pill`, and difficulty chips carry state.
- Status text must remain explicit (`Fuldført`, `Ingen quiz`, etc.) where state matters.
- Dot indicators (`.status-dot`) supplement text, never replace it.

### Progress indicators

- Use compact progress tracks with numeric context (`x/y` or percent) nearby.
- `0%` should be explained as "Ikke startet endnu" where relevant.
- Completed lecture context can shift progress bar gradient to success green.

### Timeline and sequence components

- Learning path is a vertical timeline of lecture items (`.timeline-item`).
- Lecture details default collapsed (`<details>`), open state persisted client-side.
- Timeline connector accent appears only for completed lectures.
- Reading/asset chips remain inside the lecture context to preserve sequence comprehension.

### Data table pattern

- Keep semantic table structure for quiz history.
- Improve scanability with clamped titles, module labels, difficulty chips, and concise metadata.
- Keep row hover subtle and non-disruptive.

### Form pattern

- Inputs use shared 44px minimum control height.
- Labels are always visible and directly associated.
- Validation errors appear inline near the field or as a form-level non-field error.

## Page blueprints

### `/progress` (dashboard)

Order:
1. Intro context (`dashboard-head`)
2. `Mine fag` cards with enrollment + next action
3. `Quizhistorik` table

Behavior:
- "Åbn fag" is the dominant action when enrolled.
- Enrollment mutation stays secondary (`Tilmeld`/`Afmeld`).
- "Senest åbnet fag" badge improves continuity.

### `/subjects/<subject_slug>` (learning path)

Order:
1. Subject title/description and return utility action
2. Compact KPI overview cards
3. Timeline with lectures, readings, quizzes, podcasts

Behavior:
- No enrollment mutation controls on this page.
- `Udvid alle`/`Luk alle` are neutral productivity controls.
- Difficulty action order: `Let`, `Mellem`, `Svær`.

### `/q/<quiz_id>.html` (quiz wrapper)

Order:
1. Structured identity header (`module` + cleaned title)
2. Question stage with progress context
3. Answer options and rationale/hint feedback
4. Summary and login prompt (for anonymous completion handoff)

Behavior:
- Keep one decision per step.
- Keep option hit areas large and stateful (selected/correct/wrong).
- Never expose noisy raw filename metadata in the visible title area.

### Auth routes (`/accounts/login`, `/accounts/signup`)

- Keep forms compact, direct, and trust-oriented.
- Keep insecure transport warning visible when `insecure_http` is true.
- Keep call-to-action copy action-first and short.

## Accessibility baseline

- Minimum target size: `44px` for main controls.
- Dense chips may use `32-36px` only when focus state remains clear.
- Keyboard focus must always be visible (`:focus-visible` ring).
- Contrast should meet WCAG AA minimum for text and controls.
- Motion should be minimal and optional for users with reduced-motion preferences.
- Status communication should include text, not color only.

## Copy and language system

- Product UI language: Danish (`da`).
- Keep labels concrete and action-oriented (`Log ind`, `Opret konto`, `Åbn fag`).
- Prefer short verbs and measurable progress phrases (`Besvaret x/y`, `Fuldført`).
- Avoid technical file jargon in learner-facing text.

## Governance and change checklist

Before shipping UI changes:

1. Reuse existing tokens in `templates/base.html` before adding new raw values.
2. Keep spacing/radius on the documented scale.
3. Preserve action hierarchy (primary vs secondary vs neutral).
4. Verify keyboard focus, tap targets, and color contrast.
5. Verify mobile layouts at 375px and tablet/desktop breakpoints.
6. Update this document if a new recurring pattern is introduced.
