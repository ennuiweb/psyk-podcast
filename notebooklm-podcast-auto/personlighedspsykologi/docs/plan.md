# Personlighedspsykologi Automation Plan

This document is the compact operational plan for the NotebookLM generation
pipeline. Feed ownership, RSS derivation, Spotify/Freudd sidecars, and public
artifact contracts live in `shows/personlighedspsykologi-en/docs/`.

## Current Baseline

- The pipeline is lecture-key based (`W##L#`), not week-folder based.
- Output generation is configured through
  `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`.
- The default output root is `notebooklm-podcast-auto/personlighedspsykologi/output`
  unless `PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT` or `--output-root` is set.
- `generate_week.py`, `download_week.py`, and `sync_reading_summaries.py`
  resolve a macOS Alias output-root file to its target directory when possible.
- Config-tagged filenames are the default and should stay enabled for all
  multi-format, multi-language, or multi-difficulty runs.

## Generation Policy

| Artifact | Policy |
|---|---|
| `Alle kilder (undtagen slides)` audio | One lecture-level overview per `W##L#`, generated from readings only. |
| Per-reading audio | One default-length deep-dive per reading source. |
| Short audio | Reading shorts plus lecture-slide shorts according to `short.apply_to`. Exercise slide shorts must not surface in the public RSS policy. |
| Slide audio | Generated per manually mapped lecture/exercise slide from `shows/personlighedspsykologi-en/slides_catalog.json`; seminar slides are excluded. |
| Infographics | Generated only when `--content-types` includes `infographic`. |
| Quizzes | Generated only when `--content-types` includes `quiz`; `quiz.difficulty: "all"` fans out to easy, medium, and hard. |
| Languages | Driven by `prompt_config.json`. Public English output keeps the ` [EN]` filename marker before feed cleanup. |

## Standard Commands

Dry-run one lecture:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
```

Generate selected content for multiple lecture selectors:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py \
  --weeks W01,W02L1 \
  --content-types audio,infographic \
  --profile default
```

Download from request logs:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W01,W02 --content-types audio,infographic,quiz
```

Validate reading and weekly summary coverage:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

## Request Logs

- Non-blocking generation writes `*.request.json` for queued jobs.
- Failed generation writes `*.request.error.json`.
- `generate_week.py --skip-existing` treats a valid `*.request.json` with an
  `artifact_id` as existing output unless a newer error log exists.
- `download_week.py` removes matching request and error logs after successful
  download or when the target artifact already exists.
- Use `--no-cleanup-requests` when request logs need to be retained for
  debugging. The older `--archive-requests` / `--no-archive-requests` aliases
  still exist for compatibility, but the behavior is cleanup, not archive.

## Output Contracts

- Output directories are `output/W##L#/` unless `--output-profile-subdir` is
  explicitly used.
- Output names keep one normalized leading lecture token (`W##L# - ...`).
- Config tags are non-semantic metadata and match:
  `\s\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\}`.
- Profile suffixes such as `[default]` are not appended to canonical output
  filenames.
- Legacy weekly `Alle kilder` names and legacy leading `X ` reading names are
  handled by backward-compatibility skip/rename logic.

## Prompt Quality Review

- Baseline run:
  `notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline`.
- Candidate runs must use `--review-manifest` and a run-local `--output-root`.
- If automatic Gemini meta-prompting should run, set `GEMINI_API_KEY` or
  `GOOGLE_API_KEY`. Without a key, auto-meta fails open and NotebookLM
  generation continues without generated sidecars.
- After candidate MP3s are downloaded, run
  `sync_episode_ab_review_candidates.py`, then transcribe the candidate side.

## Validation Checklist

1. Run `generate_week.py --dry-run` for the changed lecture selector.
2. Confirm planned paths use the resolved output root and zero-padded `W##L#`.
3. Confirm generated filenames include stable config tags.
4. Run `download_week.py --dry-run` and verify the selected auth profile.
5. Run `sync_reading_summaries.py --validate-only --validate-weekly`.
6. Run `python3 scripts/check_personlighedspsykologi_artifact_invariants.py`
   before committing changes that affect config, mirror paths, or docs contracts.
