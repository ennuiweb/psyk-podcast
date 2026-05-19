# Freudd Portal UI Audit

Last updated: 2026-05-19

## Purpose

This document combines the May 2026 frontend and interface-design reviews of
the live Freudd Portal UI. It is a working tracker for what has already been
fixed, what still needs design work, and what should be verified after each UI
pass.

Scope reviewed:

- public auth pages: `/accounts/login`, `/accounts/signup`
- authenticated dashboard: `/settings`
- subject pages: `/subjects/personlighedspsykologi`, `/subjects/bioneuro`
- scoreboards: `/leaderboard/personlighedspsykologi`, `/leaderboard/bioneuro`
- quiz wrapper: sample `/q/12734bc0.html`
- flashcard practice: `/subjects/bioneuro/cards/biologisk-psykologi-og-neuropsykologi`

Screenshots were captured from live `https://freudd.dk` with Playwright at:

- desktop: `1365x900`
- mobile: `390x844`

The local screenshot capture from the original audit lived under
`/tmp/freudd-ui-audit/screenshots`. Re-capture screenshots before making large
design decisions, because `/tmp` artifacts are not durable.

## Product Direction

### Domain

Freudd is a study interface, not a generic SaaS dashboard. Relevant product
concepts:

- student study session
- lecture path
- source text
- slide deck
- quiz attempt
- recall practice
- progress mark
- public scoreboard
- semester cohort
- marginal note

### Color World

The visual world should come from study materials and university workflows:

- off-white paper
- beige folders
- graphite text
- blue highlighter / link ink
- green completion marks
- light red correction marks
- soft notebook shadows
- low-contrast rule lines

### Signature

The most Freudd-specific signature should be an annotated learning path:
lecture progression, source cards, quiz status, and recall state should feel
like a structured study notebook with marginal signals. The current timeline
points in this direction, but it is too heavy and too cramped on mobile.

### Defaults To Avoid

- Generic dashboard cards everywhere.
  Replace with study sections whose structure follows the learner task:
  choose lecture, read source, quiz, review.
- Generic app bottom tabs everywhere.
  Replace with context-aware navigation, especially in focus modes.
- Metric boxes that merely display numbers.
  Replace with progress/status displays that answer "what should I do next?"
- Repeated nested cards.
  Replace with one clear surface level per task area.

## Current Status

### Fixed

| Status | Area | Notes |
|---|---|---|
| Done | Login auth card | Main login UI was redesigned into the current paper-studio card. |
| Done | Login subtitle | Removed "Fortsæt din læringssti, og gem dine quizscore undervejs." |
| Done | Auth in-card brand label | Removed the small in-card `freudd` label above the auth heading. |
| Done | Auth in-card logo/icon | Removed the icon/logo from login and signup auth cards. |
| Verified | Live smoke | After the auth-card changes, production returned expected route statuses and no auth icon markup was present. |

### Live Audit Baseline

Observed on the 2026-05-19 screenshot pass:

- no browser console errors
- no Playwright page errors
- no horizontal overflow in the tested desktop/mobile viewports
- auth pages are visually cleaner after the recent removals
- the main remaining problems are interface-system issues, not simple breakage

## Remaining Work

### P0 - Core Study Flow

#### Mobile Bottom Navigation Over Focus Modes

Status: Open

Affected screens:

- quiz wrapper
- flashcard practice
- long subject pages
- scoreboard pages
- settings page

Problem:

The fixed mobile tabbar is too visually dominant and overlaps active content.
On quiz and flashcard screens it competes with the primary task. These pages
are focus modes; navigation should not be the loudest element while answering a
question or reviewing a card.

Recommended direction:

- hide or collapse mobile bottom navigation on quiz and flashcard focus pages
- if navigation remains, make it lower, quieter, and less card-like
- add explicit bottom scroll padding for pages that keep the tabbar
- keep focus controls inside the study surface, not behind the global nav

Acceptance checks:

- quiz answers and next/back controls are never visually covered by the tabbar
- flashcard rating buttons remain fully visible and comfortably tappable
- no content ends underneath the tabbar at the bottom of long pages

#### Mobile Subject Page Structure

Status: Open

Affected screens:

- `/subjects/personlighedspsykologi`
- `/subjects/bioneuro`

Problem:

The mobile subject pages try to preserve the desktop timeline layout. The
result is a narrow timeline plus a narrow content column, with small lecture
dots, small labels, and deeply nested content cards.

Recommended direction:

- replace the always-visible rail on mobile with a lecture picker or compact
  horizontal lecture switcher
- keep the active lecture title and progress in the main flow
- make lecture navigation targets at least `44px` tall/wide
- preserve the timeline as a desktop/tablet signature, not as a cramped mobile
  control

Acceptance checks:

- a mobile user can switch lecture without tapping a tiny dot
- active lecture status is clear without reading the whole timeline
- the content column gains meaningful width on `390px` screens

### P1 - Interface System

#### Reduce Nested Cards And Border Noise

Status: Open

Affected screens:

- subject detail pages
- settings page
- flashcard practice

Problem:

Many screens use cards inside cards inside cards with similar beige borders.
The hierarchy becomes flat: every area looks equally important, even when the
learner's next action should be obvious.

Recommended direction:

- use one outer study surface where needed, then unframed internal sections
- reserve cards for repeated source items, modals, and genuinely bounded tools
- use section headings, rule lines, and spacing before adding another border
- define a clearer surface elevation scale:
  - canvas
  - sheet
  - inset/control
  - raised/action

Acceptance checks:

- the eye can identify the current lecture, next study action, and resource
  sections at a squint
- removing one border layer does not make the layout confusing

#### Footer Cleanup

Status: Open

Affected screens:

- all desktop pages

Problem:

The black footer with `shh 🤫` reads like a development/easter-egg remnant.
It breaks the paper-studio system and visually dominates the end of otherwise
quiet pages.

Recommended direction:

- remove the footer entirely, or
- replace it with a very quiet paper-tone footer with real product/navigation
  content

Acceptance checks:

- desktop pages do not end in a heavy black band
- footer, if present, supports the product instead of acting as a visual joke

#### Settings Information Architecture

Status: Open

Affected screen:

- `/settings`

Problem:

Settings repeats subject information in "mine fag" and "tilmeld og afmeld fag".
The public scoreboard checkbox is a tiny native control in an otherwise custom
interface.

Recommended direction:

- merge subject status and enrollment actions into one subject-management area
- make "Deltag offentligt" a clear toggle row with explanatory helper text
- treat scoreboard alias as a small profile/privacy form, not just another card

Acceptance checks:

- each subject appears once in the main settings flow
- participation state is understandable without reading surrounding paragraphs
- checkbox/toggle target is comfortably tappable

#### Scoreboard Empty And Mobile States

Status: Open

Affected screens:

- `/leaderboard/bioneuro`
- mobile scoreboard table/list

Problem:

The Bioneuro scoreboard empty state feels like a placeholder. The mobile top 50
table is workable for the current small data set, but it is column-constrained
and will age poorly as labels or values grow.

Recommended direction:

- add a task-oriented empty state: "Tag en quiz for at komme på listen"
- link directly to the relevant subject/quiz entry point
- on mobile, consider rank cards or a compact row layout instead of a table

Acceptance checks:

- empty scoreboard communicates the next action
- mobile scoreboard remains readable with longer aliases and more rows

### P2 - Polish And Token Cleanup

#### Auth Card Refinement

Status: Open

Affected screens:

- `/accounts/login`
- `/accounts/signup`

Problem:

Auth is much cleaner after the removals, but the colored top rule now feels
less motivated. Signup starts with optional username before required email,
which makes the first field feel less important than the actual account
identifier.

Recommended direction:

- either remove the colored top rule or make it part of a broader progress /
  study-material motif
- make e-mail the first signup field
- move optional username later or hide it behind a secondary affordance
- keep auth surfaces calmer than app surfaces

Acceptance checks:

- first signup action is unambiguous
- the auth card does not contain decorative elements that do not carry meaning

#### Flashcard Practice Controls

Status: Completed 2026-05-19

Affected screen:

- `/subjects/bioneuro/cards/biologisk-psykologi-og-neuropsykologi`

Problem:

The disabled "Forrige" control read as a thin native/system button. Rating
controls had the right labels, but their hierarchy and spacing did not yet feel
as polished as the rest of the paper-studio UI.

Implemented:

- the action area now uses deliberate paper-studio button styling instead of
  browser-default disabled controls
- `Vis svar` is the primary reveal action, and the official answer stays hidden
  until that action is used
- `Skriv svar` is an explicit toggle for the self-check text area
- rating buttons use equal, predictable touch targets with difficulty-specific
  visual treatment
- subject-page topic chips open practice directly in that category, while
  `Øv alle` remains the all-cards entry point
- learners can still change the practice scope before applying
  `Alle`/`Ubesvarede`/`Besvarede`

Recommended direction:

- align disabled button height with normal controls
- make rating buttons equal, predictable touch targets
- visually distinguish "Vis svar" as the primary reveal action
- keep review-state feedback close to the card, not scattered around the tool

Acceptance checks:

- all flashcard action buttons meet the global control height
- disabled state is visually intentional, not browser-default

#### Token And CSS System Cleanup

Status: Open

Affected files:

- `freudd_portal/templates/base.html`
- page-local CSS blocks under `freudd_portal/templates/quizzes/`

Problem:

The current token layer contains both the older blue system and the current
paper-studio system. Some components still hardcode hex values or introduce
local font variables. That makes the interface feel less systematic and makes
future UI changes harder to keep coherent.

Recommended direction:

- keep paper-studio as the canonical active system
- move hardcoded component colors into semantic tokens
- define specific tokens for controls, borders, surfaces, text hierarchy, and
  focus states
- avoid local font substitutions unless the component genuinely needs a
  different voice

Acceptance checks:

- new UI work can use tokens instead of page-specific hex values
- borders have a clear intensity scale
- controls have dedicated background/border/focus tokens

#### Typography Hierarchy

Status: Open

Affected screens:

- subject detail
- scoreboard
- settings
- auth

Problem:

Fraunces gives Freudd character, but too many headings use a similar heavy
voice. The display font should create identity, while body, metadata, data, and
controls should have clearer roles.

Recommended direction:

- reserve heavy display headings for page and major section titles
- use body/UI font for dense resource titles when readability matters more than
  voice
- use monospace only for data/quiz ids/compact numeric status
- ensure metrics use tabular numbers and consistent labels

Acceptance checks:

- page hierarchy is clear at a squint
- repeated resource items do not all compete as mini headlines

## Suggested Implementation Order

1. Remove or restyle the global footer.
2. Add focus-mode behavior for quiz and flashcard pages so mobile navigation
   does not compete with active study tasks.
3. Redesign mobile subject navigation from a full vertical rail to a compact
   lecture picker.
4. Flatten subject detail content sections and reduce nested borders.
5. Refactor settings subject management and public scoreboard participation.
6. Improve scoreboard empty/mobile states.
7. Polish auth signup field order.
8. Clean up CSS tokens and local hardcoded component colors.

## Verification Checklist

After each UI pass:

- capture desktop and mobile screenshots for every touched route
- run a no-horizontal-overflow check at `390x844` and `1365x900`
- verify there are no console errors or Playwright page errors
- check focus-visible states for any changed control
- verify all mobile interactive targets are at least roughly `44px`
- run Django template/responsive tests when templates changed
- deploy Freudd portal changes and run the production smoke check

## Tracking Notes

Use this section for short progress entries. Keep details in commits or PRs;
this file should stay a current map, not a full changelog.

| Date | Status | Entry |
|---|---|---|
| 2026-05-19 | Baseline | Combined frontend and interface-design audits into this tracker. |
| 2026-05-19 | Completed | Flashcard controls now have intentional answer reveal, optional typed-answer toggle, subject-page topic entry points, in-view topic scoping, and polished rating controls. |
