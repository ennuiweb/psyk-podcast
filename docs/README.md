# Docs

This folder holds the top-level operational docs for the repository.

Canonical architecture naming lives in [../TECHNICAL.md](../TECHNICAL.md) under
`Naming`. Use those labels consistently when referring to the wider Freudd
system and its subsystems.

Use these files:

- [freudd-learning-system-architecture.md](freudd-learning-system-architecture.md) - canonical system-wide architecture and maturity assessment for the full Freudd Learning System.
- [feed-automation.md](feed-automation.md) - podcast feed generation, show layout, GitHub Actions, Apps Script triggers, and feed hosting.
- [learning-material-design.md](learning-material-design.md) - repo-level design principles for learner-facing study materials, including problem-first reward-loop design.
- [notebooklm-automation.md](notebooklm-automation.md) - subject-oriented NotebookLM workflows, mirrors, and output conventions.
- [notebooklm-queue-operations.md](notebooklm-queue-operations.md) - Hetzner runtime contract, systemd install, env requirements, and failure playbook for the queue-owned NotebookLM publisher.
- [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md) - canonical implementation plan and backlog for the Hetzner queue + object-storage migration program.
- [notebooklm-queue-current-state.md](notebooklm-queue-current-state.md) - current implementation checkpoint for the queue + R2 migration, separate from the longer-term plan.
- [freudd-portal.md](freudd-portal.md) - repo-level Freudd integration notes and the canonical links for deploy, smoke, and portal contracts.
- [spotify-transcripts.md](spotify-transcripts.md) - local-first Spotify transcript capture, auth state, artifact layout, and sync commands.

Canonical repo entrypoints outside this folder:

- [TECHNICAL.md](../TECHNICAL.md) - short technical index for the repo.
- [AGENTS.md](../AGENTS.md) - repo-local operating rules.
- [freudd_portal/README.md](../freudd_portal/README.md) - full Freudd product and runtime contract.
- [freudd_portal/docs/deploy-and-smoke.md](../freudd_portal/docs/deploy-and-smoke.md) - canonical Freudd deploy and smoke runbook.
- [shows/personlighedspsykologi-en/docs/learning-material-outputs.md](../shows/personlighedspsykologi-en/docs/learning-material-outputs.md) - canonical boundary, quality contract, and evaluation map for learner-facing podcasts and printouts.
- [shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md](../shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md) - alternative problem-first scaffolding mode for reward-driven learners.

Cross-doc principle:

- The `Freudd Content Engine` is intentionally designed as a decomposed
  alternative to a single giant full-course reasoning pass. Relevant docs should
  preserve the distinction between bottom-up, top-down, and sideways
  information flow when describing the `Course Understanding Pipeline`,
  especially its `Source Intelligence Layer` and `Course Context Layer`.
- Use `Course Understanding Pipeline` for the pre-output source/course
  understanding work. Use `Prompt Assembly Layer` for downstream prompt
  construction. Do not use the understanding-pipeline name for NotebookLM runs,
  scaffold PDF rendering, queue publication, or portal presentation.
