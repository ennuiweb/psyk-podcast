# Freudd Portal (non-technical overview)

Freudd Portal is the learner-facing layer on top of static quiz and podcast content. Students can sign in, enroll in subjects, and continue where they left off through a structured lecture-first journey.

The progress experience is split into two clear tracks:
- Personal tracking (private): each student can manually mark readings as read and podcasts as listened, while quiz completion still comes from actual completed quizzes.
- Public quizliga: an opt-in public leaderboard that only shows alias, rank, and number of completed quizzes per subject.

This split keeps personal study habits private while still allowing a lightweight shared competition around quiz completion.

Quizliga is seasonal and automatically resets every half year (UTC). Ranking is based on unique completed quizzes in the active season, with tie-break by who reached the score first.

The portal still keeps core motivation features (quiz progress and gamification snapshots), but avoids exposing detailed personal learning activity publicly.

The platform also supports selectable visual design systems so teams can evaluate different interface directions without rebuilding core pages. Learners can switch style from "mit overblik" and keep their preferred system across sessions.

## Design system reference

The UI design system that implements this product intent is documented in `freudd_portal/docs/design-guidelines.md`.

That system formalizes four promises in the interface:
- show personal learning continuity quickly,
- keep next actions obvious,
- make progress and completion visible,
- keep the learning sequence coherent across quizzes, readings, and podcast assets.

Alternative visual direction (expressive V2):
- `freudd_portal/docs/design-system-v2-expressive.md`
