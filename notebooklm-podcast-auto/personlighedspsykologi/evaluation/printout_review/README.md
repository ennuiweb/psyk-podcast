# Printout Review Workspace

This folder is the sidecar evaluation lane for experimental printout variants.

Its current purpose is to let us generate and inspect problem-driven reading
printouts without touching the canonical printout output tree under:

`notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/`

## Current use

The first review track is:

- `problem_driven_v1`

It keeps the intended schema-v3 printout shape, but changes the learner-facing
behavior to emphasize:

- a mission to solve
- short search tasks
- visible progress
- model-building payoffs
- a stronger final challenge

## Why This Lives Here

The production printout path and the experimental printout path are not the
same thing.

For now, this workspace deliberately carries its own experimental printout
engine under `scripts/` so we can test learner-fit changes without turning the
production printout path into a second moving target.

## Folder layout

- `prompts/problem-driven-v1.md`
  The editable prompt overlay for the current experiment.
- `scripts/printout_engine.py`
  The local experimental printout engine used only by this workspace.
- `scripts/bootstrap_run.py`
  Creates a run manifest and review-note skeletons from selected sources.
- `scripts/generate_candidates.py`
  Generates experimental candidate printouts into the run-local output root.
- `runs/<run-name>/manifest.json`
  Canonical manifest for one printout review run.
- `runs/<run-name>/notes/`
  Manual review notes for each selected source.
- `runs/<run-name>/prompts/`
  Exact prompt captures used for candidate generation.
- `runs/<run-name>/candidate_output/`
  Generated problem-driven candidate printouts for that run.

The manifest also records where the canonical baseline printout would normally
live for each source under the standard output root.

## Bootstrap a run

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/bootstrap_run.py \
  --run-name 2026-05-problem-driven-pilot \
  --lectures W01L1
```

This writes:

- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json`
- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/notes/*.md`

and plans candidate output under:

- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/candidate_output/`

## Dry-run candidate generation

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --dry-run \
  --no-pdf
```

## Generate one candidate set

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --source-id w01l1-lewis-1999-295c67e3 \
  --no-pdf
```

Useful flags:

- `--force`
  Overwrite existing candidate artifacts in the run.
- `--rerender-existing`
  Re-render candidate Markdown and PDFs from the existing candidate JSON.
- `--variant-prompt`
  Override the prompt overlay markdown for one run.
- `--source-id`
  Generate only a subset of the run entries.

## Working rule

This is an evaluation path, not the canonical production path.

- do not point candidate output at the canonical live printout root
- compare candidate printouts against the baseline artifacts recorded in the
  manifest
- capture exact prompts per run so results are reproducible
- judge learner fit first, not only schema validity

## Status

This workspace currently supports:

- bootstrapping run manifests with baseline and candidate paths
- generating sidecar problem-driven printout candidates
- recording exact prompt captures per source
- keeping all experimental generation code under the review workspace

It does not yet include an automated judge script. For now, review is manual or
ad hoc.
