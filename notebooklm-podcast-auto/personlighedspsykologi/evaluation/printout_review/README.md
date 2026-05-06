# Printout Review Workspace

This folder is the sidecar evaluation lane for experimental printout variants.

Its current purpose is to let us generate and inspect problem-driven reading
scaffolds without touching the canonical scaffold output tree under:

`notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/scaffolding/<source_id>/`

## Current use

The first review track is:

- `problem_driven_v1`

It keeps the current schema-v3 scaffold shape, but changes the prompt behavior
to emphasize:

- a mission to solve
- short search tasks
- visible progress
- model-building payoffs
- a stronger final challenge

## Folder layout

- `runs/<run-name>/manifest.json`
  Canonical manifest for one printout review run.
- `runs/<run-name>/candidate_output/`
  Generated problem-driven candidate printouts for that run.

The manifest also records where the canonical baseline scaffold would normally
live for each source under the standard output root.

## Generate a dry-run plan

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_problem_driven_scaffolds.py \
  --run-name 2026-05-problem-driven-pilot \
  --lectures W01L1 \
  --dry-run \
  --no-pdf
```

This writes:

- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json`

and plans candidate output under:

- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/candidate_output/`

## Generate one candidate set

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_problem_driven_scaffolds.py \
  --run-name 2026-05-problem-driven-pilot \
  --source-id w01l1-lewis-1999-295c67e3 \
  --no-pdf
```

Useful flags:

- `--force`
  Overwrite existing candidate artifacts in the run.
- `--rerender-existing`
  Re-render candidate Markdown and PDFs from the existing candidate JSON.
- `--source-family lecture_slide`
  Target non-reading sources when needed.
- `--output-root /custom/path`
  Override the default candidate output location while keeping the run manifest.

## Working rule

This is an evaluation path, not the canonical production path.

- do not point this script at the canonical live output root by default
- compare candidate printouts against the baseline artifacts recorded in the
  manifest
- judge the learner fit first, not only schema validity

## Status

This workspace currently supports:

- generating sidecar problem-driven scaffold candidates
- recording run manifests with baseline and candidate paths

It does not yet include an automated judge script. For now, review is manual or
ad hoc.
