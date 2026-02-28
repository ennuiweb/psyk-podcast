# Freudd Portal (non-technical overview)

Freudd Portal is the learner-facing layer on top of static quiz and podcast content. Students can sign in, enroll in subjects, and continue where they left off through a structured lecture-first journey.

The progress experience is split into two clear tracks:
- Personal tracking (private): each student can manually mark tekster as read and podcasts as listened, while quiz completion still comes from actual completed quizzes.
- Public freudd quiz cup: an opt-in public leaderboard that shows alias, rank, point score, and completed quiz count per subject.

This split keeps personal study habits private while still allowing a lightweight shared competition around quiz completion.

freudd quiz cup is seasonal and automatically resets every half year (UTC). Ranking is based on a score that weighs correct answers highest and adds a speed bonus for faster quiz completion.

Each quiz question has a built-in timer, and quiz retries are throttled with an escalating cooldown to prevent rapid retakes.

The portal still keeps core motivation features (quiz progress and gamification snapshots), but avoids exposing detailed personal learning activity publicly.

The platform uses a single locked visual design system (`paper-studio`) so learners get a consistent interface across all pages.

## Design system reference

The UI design system that implements this product intent is documented in `freudd_portal/docs/design-guidelines.md`.

That system formalizes four promises in the interface:
- show personal learning continuity quickly,
- keep next actions obvious,
- make progress and completion visible,
- keep the learning sequence coherent across quizzes, tekster, and podcast assets.

This reference now includes both the operational baseline and the former expressive V2 guidance.
