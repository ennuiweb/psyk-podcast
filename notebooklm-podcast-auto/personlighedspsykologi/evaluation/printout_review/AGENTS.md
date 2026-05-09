## Project Identity

- Name: `printout_review`
- Type: `project`
- Absolute path: `/Users/oskar/repo/podcasts/notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review`
- Parent repo: `/Users/oskar/repo/podcasts`
- Global reference: `/Users/oskar/.agents/AGENTS.md`

## Inheritance From Repo AGENTS

- Repo-wide rules in `/Users/oskar/repo/podcasts/AGENTS.md` apply by default.
- This file adds only printout-review-local workflow rules.

## Project-local Rules

- Treat the printout pipeline as `JSON -> Markdown -> PDF`.
- For content-only development, inspect JSON and Markdown first.
- Do not default to PDF inspection when the change only affects prompt wording, field selection, prioritization, or other learner-facing content that does not change rendering behavior.
- PDF inspection is required when a change can affect layout, spacing, typography, headers/footers, answer-space sizing, diagram space, page breaks, or other visual rendering behavior.
- PDF inspection is also required before sign-off on any substantial printout change, even if the main iteration happened in JSON or Markdown.
- When iterating on prompts or normalization logic, prefer the cheaper loop first:
  1. inspect the internal artifact JSON if the issue is structural
  2. inspect Markdown if the issue is textual/editorial
  3. inspect PDF only when the change reaches rendering-sensitive territory or final review
- Fresh-from-source generation remains the rule for candidate artifacts; JSON or Markdown inspection must not reintroduce seeded or recycled candidate workflows.
- Use the repo `.venv` Python for review generation commands unless there is a documented reason not to.

## Local Context Map

- Workspace overview and operator workflow: `README.md`
- Prompt overlays: `prompts/`
- Experimental engine and generators: `scripts/`
- Shared flat review-PDF drop zone: `review/`
- Run manifests, prompt captures, and generated candidate outputs: `runs/`

## Self-maintenance Rules

- If the local development workflow for inspecting JSON, Markdown, and PDF changes, update this file and `README.md` together.
