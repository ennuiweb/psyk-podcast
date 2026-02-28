# Freudd Portal Design Guidelines

Last updated: 2026-02-26

## Purpose

This document defines the production design baseline for `freudd_portal`.
It maps product goals to concrete UI rules and component behavior.

Source alignment:
- Product intent: `docs/non-technical-overview.md`
- Shared primitives: `templates/base.html`
- Page patterns: `templates/quizzes/progress.html`, `templates/quizzes/subject_detail.html`, `templates/quizzes/wrapper.html`
- Auth patterns: `templates/registration/login.html`, `templates/registration/signup.html`
- Expressive reference: `docs/design-system-v2-expressive.md`

## Scope and governance

- `Paper Studio` is the only approved redesign theme for new UI work.
- Any new redesign proposal must include a short `Paper Studio compliance` note.
- Legacy systems (`classic`, `night-lab`) are removed from runtime selection; `paper-studio` is locked for users.
- This file is the operational baseline; `design-system-v2-expressive.md` is the stylistic expansion layer.

## Runtime design-system architecture (current code)

- Registry: `quizzes/design_systems.py`.
- Runtime keys available: `paper-studio`.
- Default key: `paper-studio`.
- Theme attribute on HTML: `data-design-system="<key>"`.
- Selector UI: removed (users cannot switch design system).
- Resolution behavior: only valid key is `paper-studio`; unsupported overrides fall back to default.
- Resolver/context wiring: `quizzes/theme_resolver.py` + `quizzes/context_processors.py`.

## Product intent -> design requirements

Freudd Portal exists to add identity, memory, progression, and motivation on top of static quiz content.
The UI must always make these jobs visible:

1. Identity: learner sees personal context quickly.
2. Continuity: learner sees where they left off and can resume fast.
3. Progression: learner sees completed vs pending in a clear sequence.
4. Motivation: learner effort is reflected in status and achievement cues.
5. Coherence: quizzes, tekster, and podcasts feel like one learning journey.

## Experience principles

1. Study-first clarity: keep visual noise low and decisions obvious.
2. One dominant action per block: each section has one clear next step.
3. Progress over decoration: status and momentum cues outrank ornament.
4. Consistent semantics: same status always uses same words, colors, and shapes.
5. Mobile-first readability: dense information is allowed, hard scanning is not.

## Visual language (Paper Studio baseline)

### Brand personality

- Reliable
- Focused
- Encouraging
- Practical

### Typography

- Display/headers: `Fraunces` (`600-700`, optical size enabled)
- Body/UI: `Public Sans` (`400-700`)
- Data/meta: `IBM Plex Mono` (`500-600`)

Usage rules:
- Keep heading line-height tight (`~1.1`) and body line-height comfortable (`~1.5`).
- Keep UI copy in Danish (`da`) until multilingual rollout is explicitly enabled.
- Avoid decorative or novelty fonts in learner flows.
- Keep heading casing and emphasis consistent within each template.

### Color system (Paper Studio semantic tokens)

`templates/base.html` and `:root[data-design-system="paper-studio"]` are the source of truth.

| Role | Token | Value | Usage |
|---|---|---|---|
| App background | `--bg` | `#f4efe4` | Global page backdrop |
| Soft backdrop | `--bg-soft` | `#efe7d7` | Supporting surface blocks |
| Main surface | `--surface` | `#fffdf7` | Cards and forms |
| Soft surface | `--surface-soft` | `#f8f2e6` | Section containers |
| Primary text | `--ink` | `#201d18` | Core readable text |
| Secondary text | `--muted` | `#625a4f` | Metadata/support text |
| Primary accent | `--accent` | `#0f5f8c` | Primary action and active state |
| Accent strong | `--accent-strong` | `#0b4b6f` | Link and higher emphasis |
| Success | `--success` | `#2f8a23` | Completed states |
| Danger | `--danger` | `#ba344f` | Error/wrong states |
| Border default | `--border` | `#d5c7ac` | Neutral card/section border |
| Border strong | `--border-strong` | `#c5b494` | Inputs and controls |
| Focus ring | `--focus-ring` | `rgba(15, 95, 140, 0.28)` | Keyboard-visible focus outline |

Color behavior rules:
- Blue accent indicates action/progression.
- Green indicates completion/success.
- Red indicates errors/incorrect answers.
- Never rely on color as the only state cue where text is required.

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
- Respect reduced motion preferences for all new animation.

## Layout system

### Global shell

- Sticky top navigation (`.site-header`) for orientation persistence.
- Authenticated mobile/tablet views (`<=1180px`) keep a persistent bottom tabbar (`Quizliga`, `Mit overblik`, `Mine fag`) across all pages.
- Constrained content width (`max-width: 1120px`) inside `.page-shell`.
- Single primary content card (`.card`) per route as default frame.

### Information density model

- Keep section stacks compact (`12-24px` rhythm).
- Keep metadata close to actions.
- Prefer grouped cards over long uninterrupted text blocks.

## Component system

### Action hierarchy

- Primary action: `.btn-primary` for commit/continue actions.
- Page-level secondary action: `.subject-open-link` for subject progression.
- Neutral utility action: `.nav-action`, `.subject-toggle-button`, `.ghost-button`, `.toolbar-btn`.

Rules:
- One primary action per local section.
- Secondary and neutral controls must not visually compete with primary.
- All interactive controls must keep pointer cursor and visible hover/focus states.

### Status and feedback

- `status-pill`, `status-badge`, `subject-status-pill`, and difficulty chips carry state.
- Status text must remain explicit (`Fuldført`, `Ikke startet`, `Ingen quiz`) where state matters.
- Dot indicators (`.status-dot`) supplement text, never replace it.

### Progress indicators

- Use compact progress tracks with numeric context (`x/y` or percent) nearby.
- `0%` should be explained as `Ikke startet endnu` where relevant.
- Completed lecture context may shift progress gradient to success green.

### Timeline and lecture detail partitioning

- Learning path is a two-column rail layout: left lecture rail + right single active lecture card.
- Lecture switching is URL-addressable (`?lecture=<lecture_key>`) and server-rendered on reload.
- Rail connector remains muted by default and accentuates completed context.
- Rail rows render both numbered marker and lecture copy (short week label + lecture title).
- Active lecture card must always render three sibling sections in this order:
  - `Tekster`
  - `Podcasts`
  - `Quiz for alle kilder`
- Section content boundaries are strict:
  - Quiz chips and quiz status belong only in `Quiz for alle kilder`.
  - Episode metadata belongs only in `Podcasts`.
  - Text/article cards and tekst progress belong only in `Tekster`.
- Tekst cards always show L/M/S difficulty indicators in subject detail.
- Empty state messaging is shown per section; a populated section never hides the other two.

### Data table pattern

- Keep semantic table structure for quiz history.
- Improve scanability with clamped titles, module labels, difficulty chips, and concise metadata.
- Keep row hover subtle and non-disruptive.

### Form pattern

- Inputs use shared `44px` minimum control height.
- Labels are always visible and directly associated.
- Validation errors appear inline near field or as a form-level non-field error.

## Page blueprints

### `/progress` (dashboard)

Order:
1. Intro context (`dashboard-head`)
2. `Mine fag` cards with status + `Åbn fag`
3. Tracking + leaderboard blocks
4. `Quizhistorik` table
5. Bottom `Tilmeld og afmeld fag` module

Behavior:
- `Åbn fag` is the dominant action when enrolled.
- Enrollment mutation stays secondary and is isolated to the bottom module (`Tilmeld`/`Afmeld`).
- `Senest åbnet fag` badge supports continuity.
- Existing leaderboard alias is locked by default and requires explicit edit mode.

### `/subjects/<subject_slug>` (learning path)

Order:
1. Subject title/description and return utility action
2. Left lecture rail with numbered markers
3. Single active lecture card with section blocks

Behavior:
- No enrollment mutation controls on this page.
- No KPI strip or global expand/collapse controls on this page.
- Rail marker click updates active lecture via `?lecture=<lecture_key>`.
- Active lecture card uses fixed section order:
  - `Tekster` (text/article cards with always-visible L/M/S indicators + tracking controls)
  - `Podcasts` (flat episode list with discrete tracking controls)
  - `Quiz for alle kilder` (lecture quiz level chips in order `Let`, `Mellem`, `Svær`)

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
- Keep CTA copy action-first and short.

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
2. Keep spacing and radius on the documented scale.
3. Preserve action hierarchy (primary vs secondary vs neutral).
4. Verify keyboard focus, tap targets, and color contrast.
5. Verify mobile layouts at `375px` and tablet/desktop breakpoints.
6. Verify lecture detail partitioning (`Quizzer`, `Podcasts`, `Tekster`) and per-section empty states.
7. Include a `Paper Studio compliance` note in the PR.
8. Update this document when introducing a new recurring UI pattern.
