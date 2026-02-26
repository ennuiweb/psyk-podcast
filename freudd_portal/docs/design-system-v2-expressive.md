# Freudd Portal Design System V2 (Expressive)

Last updated: 2026-02-26

## Intent

This is an alternative visual system for `freudd_portal` designed to avoid generic SaaS aesthetics. It keeps the same product goals (identity, continuity, progression, motivation, coherence) but uses stronger typography, bolder contrast, and atmospheric surfaces.

Primary inspiration:
- Dark IDE environments (focused study energy)
- Editorial print systems (content dignity and hierarchy)
- Nordic cultural contrast (quiet base + sharp signal accents)

## Direction

One product, two intentional moods:
- `Night Lab` (default): dark, concentrated, confident.
- `Paper Studio`: warm light, editorial, reflective.

Both modes use the same component grammar and spacing so users can switch without relearning the interface.

## Typography System

Avoided on purpose: `Inter`, `Roboto`, `Arial`, system-default-heavy stacks.

### Pairing A (Night Lab)

- Display/headers: `Syne` (`600-800`)
- Body/UI: `Instrument Sans` (`400-700`)
- Data/meta: `IBM Plex Mono` (`500-600`)

Character:
- Geometric but human.
- Distinctive headings without sacrificing readability.
- Strong visual separation between narrative text and technical metadata.

### Pairing B (Paper Studio)

- Display/headers: `Fraunces` (`600-700`, optical size enabled)
- Body/UI: `Public Sans` (`400-700`)
- Data/meta: `IBM Plex Mono` (`500-600`)

Character:
- Editorial authority with practical UI clarity.
- Better long-form comfort for reading-heavy sections.

## Color + Theme Tokens

Dominant palette strategy:
- Large neutral fields carry concentration.
- One electric action color + one warm highlight create rhythm.
- Success and danger stay semantically stable across modes.

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

/* Theme A: Night Lab (dark default) */
:root[data-theme="night-lab"] {
  --bg: #0a0f1d;
  --bg-elevated: #111a30;
  --surface: #141f39;
  --surface-soft: #1a2746;
  --ink: #e8eefc;
  --muted: #9aabcf;
  --border: #2a3c68;
  --accent: #1de2b6;
  --accent-strong: #0fbf97;
  --accent-warm: #ff9f1c;
  --success: #4dd36f;
  --danger: #ff627e;
  --focus-ring: color-mix(in srgb, var(--accent) 45%, transparent);
}

/* Theme B: Paper Studio (light editorial) */
:root[data-theme="paper-studio"] {
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

### Night Lab background

```css
body {
  background:
    radial-gradient(1200px 600px at 12% -10%, rgba(29, 226, 182, 0.12), transparent 55%),
    radial-gradient(900px 420px at 90% 0%, rgba(255, 159, 28, 0.11), transparent 60%),
    linear-gradient(160deg, #0a0f1d 0%, #0d1426 45%, #101a31 100%);
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(154, 171, 207, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(154, 171, 207, 0.06) 1px, transparent 1px);
  background-size: 36px 36px;
}
```

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

- Keep vertical timeline for lectures/readings.
- Dot marker uses accent on active node and success on completed node.
- Connector remains muted unless previous node is completed.

## Page Blueprints

### `/progress`

- Hero row: learner greeting + "resume" action + one fast metric.
- Subject cards: asymmetric 2-column rhythm on desktop.
- History table: denser but with stronger row states and sticky header.

### `/subjects/<subject_slug>`

- Keep KPI strip at top, but move "what next" cue into first timeline item.
- Lecture details remain collapsed by default.
- Quiz chips use stronger level distinction:
  - `Let` calm
  - `Mellem` vivid
  - `Svær` warm/high-attention

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
- Distinct font pairings per mood.
- Strong neutral dominance with sharp, intentional accents.
- One high-quality page entrance animation with stagger.
- Layered gradients/patterns tied to the selected theme.

## Implementation Plan (safe incremental)

1. Add theme tokens and new fonts in `templates/base.html`.
2. Introduce `data-theme` on `<html>` with `night-lab` default.
3. Update shared controls (`.btn-primary`, `.nav-action`, `.card`) to tokenized V2 slots.
4. Migrate `progress`, `subject_detail`, and `wrapper` page-specific colors to semantic tokens.
5. Add reduced-motion-safe reveal classes to top-level sections only.
6. Validate contrast and keyboard focus in both modes before rollout.
