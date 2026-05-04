# Docs

This folder holds the top-level operational docs for the repository.

Canonical architecture naming lives in [../TECHNICAL.md](../TECHNICAL.md) under
`Naming`. Use those labels consistently when referring to the wider Freudd
system and its subsystems.

Use these files:

- [feed-automation.md](feed-automation.md) - podcast feed generation, show layout, GitHub Actions, Apps Script triggers, and feed hosting.
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
