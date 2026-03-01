# Freudd Portal UI Design Specification (Contractor Edition)

## 1. Objective

Design a focused, motivating learning interface for Freudd Portal that helps students:

1. Resume quickly.
2. Understand progress at a glance.
3. Move through lectures in a clear sequence.
4. Stay motivated with visible completion signals.

This specification is the design source of truth for visual language and UX behavior.

## 2. Product Context

Freudd Portal is a learner-facing platform for:

- Reading assignments (`Tekster`)
- Podcast episodes (`Podcasts`)
- Quiz-based learning checks (`Quiz for alle kilder`)

Primary UI language is Danish (`da`).

## 3. Experience Principles

1. Study-first clarity: the interface must be easy to scan under cognitive load.
2. One dominant action per section: users should always know what to do next.
3. Progress before decoration: status and continuity cues are higher priority than visual novelty.
4. Semantic consistency: the same states must look and read the same everywhere.
5. Mobile-first readability: dense information is acceptable; confusion is not.

## 4. Visual Direction

Theme name: `Paper Studio`

Character:

- Editorial, calm, and practical.
- Neutral-heavy surfaces with intentional accent contrast.
- Quietly premium, never generic SaaS.

### 4.1 Typography

- Display and headings: `Fraunces` (600-700, optical size enabled)
- Body and UI: `Public Sans` (400-700)
- Data and metadata: `IBM Plex Mono` (500-600)

Typography rules:

- Heading line-height around `1.1`.
- Body line-height around `1.5`.
- Avoid decorative or novelty fonts.
- Keep heading style consistent per page.
- Do not use `Inter`, `Roboto`, `Arial`, or fallback-only typography as identity.

### 4.2 Color Tokens

Use semantic tokens rather than raw color values in component designs.

| Role | Token | Value |
|---|---|---|
| App background | `--bg` | `#f4efe4` |
| Soft backdrop | `--bg-soft` | `#efe7d7` |
| Main surface | `--surface` | `#fffdf7` |
| Soft surface | `--surface-soft` | `#f8f2e6` |
| Primary text | `--ink` | `#201d18` |
| Secondary text | `--muted` | `#625a4f` |
| Primary accent | `--accent` | `#0f5f8c` |
| Accent strong | `--accent-strong` | `#0b4b6f` |
| Success | `--success` | `#2f8a23` |
| Danger | `--danger` | `#ba344f` |
| Border default | `--border` | `#d5c7ac` |
| Border strong | `--border-strong` | `#c5b494` |
| Focus ring | `--focus-ring` | `rgba(15, 95, 140, 0.28)` |

Color semantics:

- Blue = action/progression.
- Green = completion/success.
- Red = error/incorrect.
- Never communicate critical state with color alone; always pair with text/icon.

### 4.3 Spacing and Shape

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

- Prefer borders over heavy shadows.
- Use subtle container depth and minimal hover depth.

### 4.4 Background and Atmosphere

- Avoid flat monochrome backgrounds.
- Use layered gradients and subtle patterning for depth.
- Keep atmosphere low-noise so content remains dominant.

### 4.5 Motion

Defaults:

- Entry motion: around `220ms` ease-out baseline.
- Hover/focus transitions: `140-180ms`.

Motion rules:

- Use one coordinated reveal sequence per page.
- Prefer subtle translation (`translateY(-1px)` max on hover).
- Never use aggressive card scaling.
- Honor `prefers-reduced-motion` with functional equivalents.

## 5. Layout System

### 5.1 Global Shell

- Sticky top navigation for orientation.
- Constrained content width (`max-width: 1120px`) in main content shell.
- Single primary content card per route as default framing pattern.

### 5.2 Responsive Behavior

- Desktop: full header + full lecture rail labels + two-column learning layout.
- Compact (`<=1024px`): local topbar on subject detail; fixed bottom tabbar.
- Bottom tabbar must never cover interactive content.
- All layouts must avoid horizontal page scroll.

Target validation viewports:

- `375px` mobile baseline
- `414x896` (iPhone 11 Pro Max class)
- `768x1024` (tablet portrait)
- Desktop widths `>=1280px`

## 6. Component Specification

### 6.1 Cards and Surfaces

- Rounded cards (`14-20px`) with strong but subtle border contrast.
- Compact but readable spacing rhythm (`12-24px` between major blocks).

### 6.2 Buttons and Action Hierarchy

- Primary action: high-contrast fill (`.btn-primary` style intent).
- Secondary action: visually lighter than primary.
- Utility controls: neutral and non-competing.
- One primary CTA per local section.

### 6.3 Status and Feedback

Required explicit state labels:

- `Fuldført`
- `I gang`
- `Ikke startet`
- `Ingen quiz` (where relevant)

Rules:

- Status chips/badges must combine text + color.
- Dot markers may support state but never replace text.
- Correct/wrong quiz feedback must be explicit and immediate.

### 6.4 Progress Indicators

- Show numeric context (`x/y` or `%`) next to progress bars.
- Explicitly label zero-state progress (`Ikke startet endnu`).

### 6.5 Forms

- Minimum control height: `44px`.
- Always-visible labels.
- Inline validation at field level and/or form-level error summary.

### 6.6 Data Tables

- Keep semantic table structure.
- Optimize scanability with concise metadata and clear row hierarchy.
- Hover states must remain subtle and non-disruptive.

### 6.7 Lecture Timeline and Section Partitioning

Learning path pattern:

- Left lecture rail + right active lecture card.
- Lecture switching is URL-addressable (`?lecture=<lecture_key>`).

Active lecture card must include three sibling sections in this order:

1. `Tekster`
2. `Podcasts`
3. `Quiz for alle kilder`

Strict content boundaries:

- Quiz chips and quiz status only in `Quiz for alle kilder`.
- Episode metadata only in `Podcasts`.
- Reading cards/progress only in `Tekster`.
- L/M/S difficulty indicators always visible on reading cards.
- Empty states shown per section independently.

## 7. Page-Level Blueprints

### 7.1 Dashboard (`/progress`)

Order:

1. Intro context (`dashboard-head`)
2. `Mine fag` cards with status and `Åbn fag`
3. Tracking + leaderboard blocks
4. `Quizhistorik` table
5. `Tilmeld og afmeld fag` module

Behavior:

- `Åbn fag` is dominant for enrolled subjects.
- Enrollment mutation controls are isolated to bottom module.
- Alias editing is explicit mode-based (not always-on).

### 7.2 Subject Detail (`/subjects/<subject_slug>`)

Order:

1. Subject header and return action
2. Left lecture rail
3. Single active lecture card

Behavior:

- No enrollment mutation controls on this page.
- No KPI strip and no global expand/collapse controls.
- Rail interaction updates active lecture.
- Maintain fixed section order and strict section boundaries.

Responsive contract:

- Desktop: standard header + labeled rail + two-column layout.
- Compact: local topbar + fixed bottom tabbar + safe-area-aware padding.
- Visual reprioritization may occur in compact mode, but semantic section structure must remain stable.

### 7.3 Quiz Wrapper (`/q/<quiz_id>.html`)

Order:

1. Structured identity header (`module` + cleaned title)
2. Question stage with progress context
3. Answer options and rationale/hint feedback
4. Summary and login prompt (for anonymous handoff)

Behavior:

- One decision per step.
- Large answer hit areas.
- Clear selected/correct/wrong states.
- No noisy raw filename strings in visible title surfaces.

### 7.4 Auth (`/accounts/login`, `/accounts/signup`)

- Compact, direct, trust-oriented forms.
- Short, action-first CTA copy.
- Keep transport/security warning visible when applicable.

## 8. Accessibility Requirements

1. Minimum target size `44x44` for primary interactive controls.
2. Visible keyboard focus (`:focus-visible` equivalent ring behavior).
3. WCAG AA contrast minimum for text and controls.
4. Status communication must not rely on color only.
5. Motion-reduced experience must preserve usability.
6. Long Danish words must wrap safely (`overflow-wrap:anywhere`, `hyphens:auto` behavior).

## 9. Copy and Language

- Interface language: Danish.
- Keep labels short and concrete.
- Favor action verbs and measurable progress phrasing.
- Avoid technical/internal file terminology in learner-facing UI.

## 10. Anti-Patterns

Do not use:

- Purple-on-white gradient templates.
- Equal-weight palettes where everything competes.
- Heavy, generic component-library look copied 1:1.
- Flat, atmosphere-free page backgrounds.
- Multiple unrelated animations on a single screen.

## 11. Contractor Deliverables

Provide:

1. High-fidelity designs for `/progress`, `/subjects/<subject_slug>`, `/q/<quiz_id>.html`, login, and signup.
2. Component sheet covering buttons, cards, badges/chips, timeline rail, form controls, and table rows.
3. Responsive variants (mobile, tablet portrait, desktop).
4. Interaction notes for hover, focus, active, disabled, and success/error states.
5. Accessibility annotations (contrast, focus behavior, touch targets, motion-reduced behavior).

Acceptance criteria:

1. Visual language matches Paper Studio direction and token semantics.
2. Action hierarchy is unambiguous across all page types.
3. Lecture section partitioning is respected without cross-section leakage.
4. Designs are implementation-ready without requiring interpretation of historical/project-internal context.
