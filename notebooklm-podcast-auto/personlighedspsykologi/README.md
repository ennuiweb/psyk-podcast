# Personlighedspsykologi (NotebookLM Generation)

This folder contains the generation pipeline assets for Personlighedspsykologi audio + infographic + quiz production.
It is **not** a podcast feed. Feed config now lives in:

- `shows/personlighedspsykologi-en`
- Feed ordering preference is configured there via `feed.sort_mode: "wxlx_kind_priority"` (`Short -> Alle kilder -> Oplæst/TTS readings -> other readings` within each `W#L#` block).
- In this mode, `pubDate` values inside each `W#L#` block are also re-sequenced so clients that sort by `Oldest` show `Alle kilder` first in the block.

## Key paths
- `scripts/` - generation helpers (`generate_week.py`, `download_week.py`, `sync_reading_summaries.py`)
- `prompt_config.json` - prompts + language variants for NotebookLM (audio + infographic + quiz defaults, including `audio_prompt_strategy`, `exam_focus`, and `meta_prompting`)
- OneDrive Readings root (authoritative source dirs):
  - `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`
- `output/` - generated MP3s/PNGs/quiz exports + request logs
- `docs/` - planning notes
- `evaluation/episode_ab_review/` - before/after quality-review workspace for matched transcript comparisons

## Output root default
- `generate_week.py`, `download_week.py`, and `sync_reading_summaries.py` accept `--output-root`.
- If `PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT` is set, those scripts use it as the default output root.
- Otherwise they fall back to `notebooklm-podcast-auto/personlighedspsykologi/output`.

```bash
export PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT="/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive upload/podcast output personlighedsspyk/output"
```

Archived show configs are stored in `archive-show-config/` for reference.

Current generation is configured for English-only outputs (see `prompt_config.json`).

## Authoritative source root
- `generate_week.py` and `sync_reading_summaries.py` now default `--sources-root` to the OneDrive Readings path above.
- Source fallback to repo-local `sources/` is intentionally disabled for weekly sync metadata updates.
- Migration utility:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py --apply
# after archiving repo-local sources/, use:
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py --canonical-root notebooklm-podcast-auto/personlighedspsykologi/sources.archive-<timestamp>
```

- Post-migration validations:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1L2 --dry-run
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W8L1 --dry-run
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W10L2 --dry-run
```

## "Alle kilder" notebook behavior (lecture-level episodes)
- `Alle kilder (undtagen slides)` generation runs per lecture (`W#L#`) and uses a fresh NotebookLM notebook on every run (no notebook reuse).
- This guarantees the run re-uploads the full lecture source list instead of relying on existing notebook sources.
- `Alle kilder` is skipped automatically for lecture folders that contain only one source file.
- Manual slide entries from `shows/personlighedspsykologi-en/slides_catalog.json` are included as per-slide sources for reading-level generation when they are lecture or exercise slides and have a valid `local_relative_path`.
- Slide sources generate their own per-source podcasts/quizzes. Short episodes are currently configured for all readings plus lecture slides only via `short.apply_to: "readings_and_lecture_slides"` (the older config key is still accepted), with descriptor titles like `Slide lecture: <title>`.
- Slide audio settings come from `per_slide` in `prompt_config.json`; reading audio settings stay under `per_reading`.
- Audio prompts are source-aware by default through `audio_prompt_strategy.prompt_types` in `prompt_config.json`.
  - Implemented prompt types are `single_reading`, `single_slide`, `weekly_readings_only`, `short`, and `mixed_sources`.
  - `Alle kilder (undtagen slides)` currently uses `weekly_readings_only`, so weekly overviews remain readings-only.
  - `single_reading` asks for argument structure, conceptual distinctions, corrections/rejections, likely misunderstandings, and implications for personality/subject thinking.
  - `single_slide` treats slides as fragmentary lecture scaffolding and asks NotebookLM to reconstruct the argumentative sequence rather than summarize slide bullets.
  - `mixed_sources` is implemented in the builder for future mixed notebooks and assigns explicit source roles: slides provide structure and lecture framing; readings provide nuance and argumentative depth.
  - `short` uses a compact, exam-oriented focus rather than the full deep-dive checklist.
  - The default tone is calm, precise, and teaching-oriented, with explicit anti-dramatization guidance.
- `exam_focus` is a separate additive block in `prompt_config.json`.
  - It injects short exam-facing evaluation criteria after the scenario focus block.
  - The defaults emphasize historical tradition/core assumptions, possibilities and limitations, theory-method relation, and what should be evaluated critically rather than merely repeated.
- The raw `prompt` fields under `weekly_overview`, `per_reading`, `per_slide`, and `short` are additive for audio: they append extra instructions on top of the built-in prompt structure rather than replacing it.
- Individual slide podcasts can override `per_slide` by `slide_key`:

```json
"per_slide": {
  "format": "deep-dive",
  "length": "default",
  "prompt": "",
  "overrides": {
    "w09l1-lecture-17-kritisk-psykologi-30798115": {
      "length": "long"
    }
  }
}
```

- Override fields are optional and inherit from the base `per_slide` block. Supported fields are `format`, `length`, and `prompt`.
- You can attach external pre-analysis from another LLM and have it folded into audio prompts automatically through `meta_prompting`.
  - Per-source sidecars: `<source>.prompt.md`, `<source>.prompt.txt`, `<source>.analysis.md`, `<source>.analysis.txt` (both `Foo.pdf.prompt.md` and `Foo.prompt.md` are accepted).
  - Weekly sidecars: `week.prompt.md`, `week.prompt.txt`, `week.analysis.md`, `week.analysis.txt`, plus `W01L1.prompt.md` / `.txt` / `.analysis.md` / `.analysis.txt`.
  - Sidecars are appended under the configured `meta_prompting.heading`.
  - Sidecars are excluded from the source inventory, so they are never uploaded to NotebookLM as course materials.
  - `meta_prompting.automatic` can fill in missing sidecars automatically before audio generation. Existing sidecars still win; automation only fills gaps.
  - Automatic mode defaults to Gemini Developer API with `provider=gemini` and `model=gemini-2.5-pro`.
  - Gemini mode needs `GEMINI_API_KEY` or `GOOGLE_API_KEY` plus the `google-genai` and `pypdf` packages from `requirements.txt`.
  - Anthropic is still supported as `provider=anthropic` if you explicitly want that path, and then it needs `ANTHROPIC_API_KEY` plus the `anthropic` package.
  - Dry runs can resolve automatic meta notes in memory so you can inspect likely resolved prompts with `--print-resolved-prompts`, but they do not write sidecar files and a later real run may still differ unless you materialize a sidecar first.
- Standalone helper: `python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_meta_prompts.py --prompt-type single_reading --reading-source /path/to/Foucault.pdf --output /tmp/Foucault.analysis.md --dry-run`
- Use `--print-resolved-prompts` together with `--dry-run` when you want to inspect the fully assembled audio prompt before generation.
- To bootstrap a balanced before-only review sample for prompt QA:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/bootstrap_episode_ab_review.py \
  --run-name 2026-04-before-baseline \
  --episode-output-root '/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive upload/podcast output personlighedsspyk'
```

- Find stable slide keys in `shows/personlighedspsykologi-en/slides_catalog.json`.
- To regenerate only one slide podcast, use `--only-slide <slide_key>`. This skips `Alle kilder`, readings, and short-form outputs for that run:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W09L1 --content-types audio --only-slide w09l1-lecture-17-kritisk-psykologi-30798115 --wait
```

- Non-dry `--only-slide` audio runs quarantine stale full-slide MP3s with the same visible slide basename but a different audio config tag under `.ai/quarantine/slide-audio-overrides/`, including request sidecars. This prevents old `length=default` and new `length=long` slide files from both being published.
- Seminar slides are excluded from generation, and non-dry runs auto-delete any stale `Slide seminar: ...` outputs in the target week folder before planning new artifacts.
- Non-dry runs also delete stale slide short outputs that fall outside the configured short scope (for example old `Slide exercise: ...` short files when `short.apply_to` is lecture-only for slides).
- Slides are excluded from the notebook source set for `Alle kilder (undtagen slides)` and therefore also excluded from its `sources=<n>` tag.

## Output filename config tags
- `generate_week.py` appends a human-readable config tag before the extension: ` {...}`.
- The tag includes artifact output options (type/language + API settings) and a full effective generation config hash.
- `Alle kilder` audio outputs additionally include `sources=<n>` (number of uploaded sources in the lecture notebook).
- Output filenames never append profile collision suffixes like `[default]` or `[default-2]`; canonical paths are always used.
- Reading filenames are normalized to a single leading week token (`W#L# - ...`) even when source PDFs include repeated week labels.
- Legacy `Alle kilder` weekly-overview files using the old basename are treated as existing outputs during skip checks.
- On non-dry runs, `generate_week.py` auto-renames legacy weekly-overview files from `Alle kilder` to `Alle kilder (undtagen slides)` when the canonical target path is free.
- Legacy reading files that still include an old leading `X ` prefix are also treated as existing outputs during skip checks.
- On non-dry runs, `generate_week.py` auto-renames those legacy `X ...` reading outputs to the current canonical basename when the target path is free.
- Example: `W11L2 - Raggatt (2006) [EN] {type=audio lang=en format=deep-dive length=long hash=7f1bf8c4}.mp3`
- Tag regex contract (case-insensitive in parsers):
  - `\s\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\}`
- Controls:
  - `--config-tagging` (default on)
  - `--no-config-tagging`
  - `--config-tag-len N` (default: 8)

## Quiz generation
- Configure quiz settings in `prompt_config.json` under `quiz` (difficulty, quantity, format, prompt).
  - `quiz.difficulty` supports `easy`, `medium`, `hard`, and `all`.
  - Use `all` to fan out quiz generation across all three difficulties for every episode in one `generate_week.py` run.
- Generate quizzes for a week:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --profile default
```

- Generate all quiz difficulties for a single `generate_podcast.py` invocation:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/generate_podcast.py --artifact-type quiz --quiz-difficulty all --quiz-format html --sources-file <sources.txt> --notebook-title "<title>" --output "<output>.html" --profile default
```

- Download quiz exports from request logs:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W1 --content-types quiz
```

- Download all output types (audio + infographic + quiz) for a full week or a specific lecture:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W2
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W2L1
```

- Request-log cleanup behavior (default): after a successful download (or when output already exists), `download_week.py` removes matching `*.request.json` and `*.request.error.json` files for that output.
  - Use `--no-cleanup-requests` to keep logs.
  - Backward-compatible aliases still work: `--archive-requests` / `--no-archive-requests`.

- Override quiz download format (html/markdown/json):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html
```

- Legacy quiz HTML->JSON extraction is no longer part of the default local flow in this branch.
- Git hook behavior: quiz extraction is disabled by default. Enable with `QUIZ_JSON_EXTRACT_ON_PUSH=1` if the extractor script exists in your checkout.

## Reading summaries cache (for feed descriptions)
- Scaffold missing summary entries from local episode files (dry-run first):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py
```

- Scaffold/update per-lecture `Alle kilder` cache from all source summaries:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview
```

- Validate coverage (warn-only, no writes):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

- Rebuild the feed after syncing summaries:

```bash
python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json
```

- Sync behavior:
  - Uses local audio files under `output/` as inventory for all non-weekly episode variants, including reading, slide, short, and `TTS`.
  - Excludes `Alle kilder` / `All sources` files from the reading summary inventory.
  - Adds missing `by_name` placeholders with empty `summary_lines` + `key_points`.
  - `--validate-only` reports missing/incomplete entries and always exits non-blocking for coverage gaps.
  - Run scaffold/update before validation when checking a fresh cache (`--validate-only` reads current file state only).
  - Writes cache to `shows/personlighedspsykologi-en/reading_summaries.json`.
  - `Alle kilder` cache path is `shows/personlighedspsykologi-en/weekly_overview_summaries.json`; it stores Danish manual lecture-level summaries plus source-coverage metadata and draft aggregate text.
  - `--sync-weekly-overview` updates lecture-level `Alle kilder` coverage metadata and draft fields, while preserving manual `summary_lines` / `key_points`.
  - `--validate-weekly` adds warn-only lecture-level checks (`weekly_missing_entry`, `weekly_incomplete_summary`, `weekly_incomplete_key_points`, `weekly_non_danish`, `weekly_source_coverage_gap`).
  - Manual fill targets are `2-4` summary lines and `3-5` key points per entry.
  - Language rule: if the source text is Danish, write `summary_lines` and `key_points` in Danish (otherwise keep English).
  - Feed build requires Google dependencies (`google-auth`, `google-api-python-client`) and `shows/personlighedspsykologi-en/service-account.json`.

## Troubleshooting
- If you interrupt `download_week.py` while waiting, rerun the same command. Already-downloaded outputs are skipped.
- To avoid long waits for in-progress artifacts, set `--timeout` and rerun later.
- `generate_week.py` suppresses per-file skip logs by default; add `--print-skips` when you want to inspect every skipped output path.
- If `generate_week.py` starts creating notebooks even though quiz `.json` files exist, verify tag parity first.
  - Canonical quiz JSON outputs should be tagged `download=json` with matching config hash.
  - Legacy `download=html`-tagged quiz JSON names (from older extraction runs) should be renamed or re-extracted to avoid duplicate generation.
  - Quick check: `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --dry-run`
  - Keep `quiz.format` in `prompt_config.json` aligned with expected filenames (`json` for canonical JSON outputs).
- If weekly `Alle kilder (undtagen slides)` files were previously generated as `Alle kilder`, dry-run now still counts the legacy files as existing, and non-dry runs will rename them into the canonical basename before continuing.
- The same backward-compatibility logic applies to reading outputs that were previously generated with a leading `X ` in the basename.
- If both `<output>.request.json` and `<output>.request.error.json` exist, `generate_week.py` now trusts the newest log:
  - newer `.request.json` (with `artifact_id`) means the job is already queued, so it is skipped.
  - newer `.request.error.json` means the latest attempt failed, so it is retried.
- To list legacy double-prefix files (`W1L1 - W1L1 ...`), run:
  `find notebooklm-podcast-auto/personlighedspsykologi/output -type f | rg '/W[0-9]+L[0-9]+/W[0-9]+L[0-9]+ - W[0-9]+L[0-9]+'`

## Quiz hosting (droplet)
Quiz links are hosted on the droplet under:
`http://64.226.79.109/q/<id>.html`
where `<id>` is a deterministic flat hex ID (default length: 8).

Server storage is now subject-isolated:
- `personlighedspsykologi` -> `/var/www/quizzes/personlighedspsykologi`
- `bioneuro` -> `/var/www/quizzes/bioneuro`

Both sync scripts auto-append `--subject-slug` when `--remote-root` ends with `/quizzes`, so
`--remote-root /var/www/quizzes` is safe for multi-subject sync.

The mapping and upload can run automatically in GitHub Actions (when quiz JSON
files are uploaded to Drive) via `podcast-tools/sync_drive_quiz_links.py`, as
long as the repository has the secret `DIGITALOCEAN_SSH_KEY` set. The Apps Script
Drive trigger must include `application/json` in `mimePrefixes` to detect quiz changes.

Use the sync script locally to upload quizzes and update the mapping used by the feed:

```bash
python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi --quiz-difficulty any --quiz-path-mode flat-id --flat-id-len 8 --remote-root /var/www/quizzes --dry-run
python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi --quiz-difficulty any --quiz-path-mode flat-id --flat-id-len 8 --remote-root /var/www/quizzes
```

The mapping file lives at `shows/personlighedspsykologi-en/quiz_links.json` and is
used by the feed generator to append quiz links to episode descriptions when
available. With `--quiz-difficulty any`, episode descriptions include all
available quiz difficulties (`easy`, `medium`, `hard`) for the matching audio
episode.
Source-of-truth is quiz JSON exports; mapping intentionally keeps `.html` relative paths
to preserve public `/q/<id>.html` URLs.
The feed item `<link>` still prefers the `medium` quiz URL when available.
