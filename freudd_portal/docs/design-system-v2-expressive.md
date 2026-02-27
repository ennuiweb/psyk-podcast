# Freudd Portal Design System V2 (Expressive)

Last updated: 2026-02-26

## Intent

This is the active visual system for `freudd_portal` designed to avoid generic SaaS aesthetics. It keeps the same product goals (identity, continuity, progression, motivation, coherence) but uses stronger typography, bolder contrast, and atmospheric surfaces.

Primary inspiration:
- Editorial print systems (content dignity and hierarchy)
- Nordic cultural contrast (quiet base + sharp signal accents)

## Direction

Theme lock (effective 2026-02-26):
- `Paper Studio` is the selected and only approved redesign theme.
- All new redesign work must start from Paper Studio tokens, typography, and surfaces.
- `Night Lab` is archived for reference and must not be used for new redesigns.

## Typography System

Avoided on purpose: `Inter`, `Roboto`, `Arial`, system-default-heavy stacks.

### Paper Studio pairing (locked)

- Display/headers: `Fraunces` (`600-700`, optical size enabled)
- Body/UI: `Public Sans` (`400-700`)
- Data/meta: `IBM Plex Mono` (`500-600`)

Character:
- Editorial authority with practical UI clarity.
- Better long-form comfort for tekst-heavy sections.

## Color + Theme Tokens

Dominant palette strategy:
- Large neutral fields carry concentration.
- One electric action color + one warm highlight create rhythm.
- Success and danger stay semantically stable across components.

```css
/* shared semantic slots */
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --radius-sm: 8px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --radius-pill: 999px;
  --control-min-height: 44px;
  --focus-ring-size: 3px;
}

/* Locked theme: Paper Studio (light editorial) */
:root[data-design-system="paper-studio"] {
  --bg: #f4efe4;
  --bg-elevated: #efe7d7;
  --surface: #fffdf7;
  --surface-soft: #f8f2e6;
  --ink: #201d18;
  --muted: #625a4f;
  --border: #d5c7ac;
  --accent: #0f5f8c;
  --accent-strong: #0b4b6f;
  --accent-warm: #d9480f;
  --success: #2f8a23;
  --danger: #ba344f;
  --focus-ring: color-mix(in srgb, var(--accent) 40%, transparent);
}
```

## Atmospheric Background System

No flat monochrome canvas. Use layered depth:

### Paper Studio background

```css
body {
  background:
    radial-gradient(900px 500px at 6% -10%, rgba(15, 95, 140, 0.09), transparent 56%),
    radial-gradient(1000px 420px at 92% -4%, rgba(217, 72, 15, 0.09), transparent 64%),
    linear-gradient(160deg, #f6f1e7 0%, #f3ecdf 52%, #ede3d2 100%);
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image: repeating-linear-gradient(
    0deg,
    transparent 0 24px,
    rgba(98, 90, 79, 0.03) 24px 25px
  );
}
```

## Motion System

Use one orchestrated entrance per page, not many unrelated animations.

### Page load choreography

- Animate only: header, primary card shell, first action row.
- Stagger with class delays (`.reveal-1`, `.reveal-2`, `.reveal-3`).
- Duration range: `260-420ms`.
- Easing: `cubic-bezier(0.22, 1, 0.36, 1)` for enter.

```css
@keyframes reveal-up {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}

.reveal {
  opacity: 0;
  animation: reveal-up 360ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.reveal-1 { animation-delay: 40ms; }
.reveal-2 { animation-delay: 120ms; }
.reveal-3 { animation-delay: 200ms; }

@media (prefers-reduced-motion: reduce) {
  .reveal {
    animation: none;
    opacity: 1;
    transform: none;
  }
}
```

### Micro-interaction rules

- Hover states: color/border/light translation only (`translateY(-1px)` max).
- Never scale cards enough to shift layout.
- Keep transitions in `140-180ms` range.

## Component Language

### Signature shapes

- Main cards: rounded (`14-20px`) with strong border contrast.
- Pills/chips: fully rounded but compact.
- Section separators: subtle rule + small uppercase label.

### Buttons

- Primary button uses action color fill with warm accent on hover border.
- Secondary button is outline on elevated surface.
- Utility controls must stay visually lighter than progression CTAs.

### Status system

- `Fuldført` => success color + textual badge.
- `I gang` => accent color + textual badge.
- `Ikke startet` => muted badge + explicit wording.
- Wrong/correct answer states in quizzes always pair color with text or iconography.

### Timeline

- Keep lecture progression as a left rail with numbered markers and connector.
- Active marker uses accent; non-active markers stay neutral with completed context on connector.
- Timeline copy must show both week and lecture title, e.g. `Uge 1, forelæsning 1: Intro...`.
- Right column renders a single active lecture card selected by URL query (`?lecture=<lecture_key>`).

### Lecture detail partitioning (required)

- Active lecture card must render three sibling sections in this order: `Tekster`, `Podcasts`, `Quiz for alle kilder`.
- Each section has its own heading, icon, and content container.
- Quiz chips, level pills, and quiz status live only in `Quiz for alle kilder`.
- Episode metadata (duration, listen-state, speed markers) lives only in `Podcasts`.
- Text/article cards and tekst progress live only in `Tekster`.
- Tekst cards always expose L/M/S difficulty indicators in subject detail.
- Empty state messaging is shown per section; one populated section must not hide the others.

## Page Blueprints

### `/progress`

- Hero row: learner greeting + "resume" action + one fast metric.
- Subject cards: asymmetric 2-column rhythm on desktop.
- History table: denser but with stronger row states and sticky header.

### `/subjects/<subject_slug>`

- Remove KPI strip and global expand/collapse controls.
- Use lecture rail navigation (left) + one active lecture card (right).
- Active lecture card uses fixed section order:
  - `Tekster` (text/article cards with L/M/S indicators + tracking controls).
  - `Podcasts` (flat episode list with discrete tracking controls).
  - `Quiz for alle kilder` (lecture quiz chips by level).
- Quiz chips use stronger level distinction: `Let` calm, `Mellem` vivid, `Svær` warm/high-attention.

#### Responsive contract (required)

- Desktop (`>1100px`): two-column lecture rail + active lecture card.
- Tablet (`901-1100px`): still two-column, with compressed rail width and wrapped-safe header navigation.
- Tablet/mobile stack (`<=900px`): lecture rail and active lecture card stack in one column.
- Mobile narrow (`<=520px`): lecture-level quiz band collapses to a single-column list.

Guardrails:
- No horizontal page scroll on subject detail for iPhone 11 Pro Max (`414x896`) and iPad portrait (`768x1024`).
- Active lecture title and rail labels must support long Danish compounds (`overflow-wrap:anywhere`, `hyphens:auto`).
- On coarse pointers, primary interaction controls must be at least `44x44`.

### `/q/<quiz_id>.html`

- Quiz header becomes an "exam card" with module label and large title.
- Question stage keeps single-decision layout.
- Correct/wrong transitions are instant-feedback first, then rationale reveal.

## Anti-Slop Guardrails

Do not use:
- `Inter`, `Roboto`, `Arial`, fallback-only visual identity.
- Purple-on-white gradient templates.
- Equal-weight palettes where every color competes.
- Component libraries copied 1:1 without local character.
- Flat solid-color page backgrounds without atmosphere.

Do use:
- Paper Studio font pairing (`Fraunces`, `Public Sans`, `IBM Plex Mono`).
- Strong neutral dominance with sharp, intentional accents.
- One high-quality page entrance animation with stagger.
- Layered gradients/patterns tied to Paper Studio only.

## Theme Governance (Paper Studio Only)

- All future redesign documentation and UI proposals in `freudd_portal` must be authored for `Paper Studio`.
- New redesign PRs must include a short "Paper Studio compliance" note covering typography, tokens, and section partitioning.
- If an experimental visual direction is explored, it must be documented outside this file and cannot replace the Paper Studio baseline.

## Implementation Plan (safe incremental)

1. Add design-system tokens and fonts in `templates/base.html`.
2. Set `data-design-system="paper-studio"` on `<html>` as locked default.
3. Update shared controls (`.btn-primary`, `.nav-action`, `.card`) to tokenized V2 slots.
4. Migrate `progress`, `subject_detail`, and `wrapper` page-specific colors to semantic tokens.
5. Refactor subject detail lecture content into three explicit blocks: `Tekster`, `Podcasts`, `Quiz for alle kilder` (implemented in `templates/quizzes/subject_detail.html` + `quizzes/views.py`).
6. Add reduced-motion-safe reveal classes to top-level sections only.
7. Validate contrast, keyboard focus, and section partitioning behavior before rollout.
