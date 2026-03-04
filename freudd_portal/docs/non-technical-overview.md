# Freudd Portal (non-technical overview)

Freudd Portal is the learner-facing layer on top of static quiz and podcast content. Students can sign in, enroll in subjects, and continue where they left off through a structured lecture-first journey.

The settings page (`/settings`) focuses on three things:
- subject access and enrollment management,
- personal quiz history and status,
- public quizkonkurrencen settings.

The dedicated quizkonkurrencen page (`/leaderboard/<subject_slug>`) presents this as subject tabs, a top-3 podium, and a Top 50 table.

Personal study habits for tekster/podcasts remain private to each learner on subject pages, while a lightweight shared competition around quizzes is available through quizkonkurrencen.

quizkonkurrencen runs on semesters and automatically resets every half year (UTC). Ranking is based on a score that weighs correct answers highest and adds a speed bonus for faster quiz completion.

Each quiz question has a built-in timer, and quiz retries are throttled with an escalating cooldown to prevent rapid retakes.

The portal still keeps core motivation features (quiz progress and gamification snapshots), but avoids exposing detailed personal learning activity publicly.

The platform uses a single locked visual design system (`paper-studio`) so learners get a consistent interface across all pages.
Future multi-theme support may be reintroduced, but is not active in the current product.

## Design system reference

The UI design system that implements this product intent is documented in `freudd_portal/docs/design-guidelines.md`.

That system formalizes four promises in the interface:
- show personal learning continuity quickly,
- keep next actions obvious,
- make progress and completion visible,
- keep the learning sequence coherent across quizzes, tekster, and podcast assets.

This reference now includes both the operational baseline and the former expressive V2 guidance.
