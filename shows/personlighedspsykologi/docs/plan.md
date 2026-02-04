# Implementation Plan (Personlighedspsykologi F26)

## Status summary
- Show scaffolding already exists (`config.*`, `auto_spec.json`, `episode_metadata.json`).
- Socialpsykologi feed review confirms a mixed output pattern:
  - Weekly overview episodes (e.g., "Alle kilder")
  - Per-reading episodes
  - Short "[Brief]" variants for some readings

## Output policy (decisions)
- Weekly overview: **"Alle kilder"** episode per week.
  - Format: `deep-dive`
  - Length: `long`
  - Prompt: from `shows/personlighedspsykologi/prompt_config.json`
  - Language: from `shows/personlighedspsykologi/prompt_config.json`
- Per-reading episode: one per reading in each week folder.
  - Format: `deep-dive`
  - Length: `default`
  - Prompt: from `shows/personlighedspsykologi/prompt_config.json`
  - Language: from `shows/personlighedspsykologi/prompt_config.json`
- Brief variants: every **Grundbog kapitel** gets an extra brief version.
  - Format: `brief`
  - Length: not set (UI does not expose length for brief; config value is ignored)
  - Prompt: from `shows/personlighedspsykologi/prompt_config.json`
  - Language: from `shows/personlighedspsykologi/prompt_config.json`
  - Name prefix: `[Brief]`

## Automation scope (decisions)
- **Per-episode notebooks only.** We are **not** using single-notebook + source-ID selection for now.
- **Source de-duplication on reuse.** When reusing a notebook, already-uploaded sources are skipped to avoid duplicates.

## Highlighting / important readings
- `important_text_mode` is `week_x_only`.
- Only file names starting with `W## X` will be highlighted as `[Gul tekst]`.
- Reading map uses `W## X` prefixes; rename files to match when ready.

## Missing-file skip policy
- Skip audio generation for any episode whose source file is missing.
- Skip the **weekly "Alle kilder"** episode if any reading in that week is missing.

Single-file skips:
- W11: Funch & Roald (2014)
- W17: Jensen (2014)
- W20: Staunæs & Juelskjær (2014)
- W21: Bank (2014)
- W22: Køppe (2014)
- W22: Køppe & Dammeyer (2014b)

Weekly overview skips:
- W11
- W17
- W20
- W21
- W22

## Reading map
- The authoritative per-week reading list is in:
  - `shows/personlighedspsykologi/docs/reading-file-key.md`
- Source inventory currently lives in:
  - OneDrive: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

## Socialpsykologi reference used
- Drive structure: week folders containing `kilder/` + MP3s at week root.
- Feed file: `shows/social-psychology/feeds/rss.xml` (shows mixed per-week + per-reading + brief pattern).

## Next execution steps (pending)
1. Sync OneDrive readings into `shows/personlighedspsykologi/sources/W## …`.
2. Apply filename renames for `W## X` highlights and `[Brief]` variants.
3. Generate audio via NotebookLM (non-blocking) and record `artifact_id`s.
4. Download completed MP3s.
5. Upload MP3s to Drive week folders.
6. Run local feed build for validation.

## Week generation command
Command (non-blocking by default, add `--wait` to block):

```bash
.venv/bin/python shows/personlighedspsykologi/scripts/generate_week.py --week W04
```

This command:
- Uses `shows/personlighedspsykologi/prompt_config.json` for prompts/lengths.
- Skips weekly “Alle kilder” when missing readings are listed for that week.
- Emits MP3s to `shows/personlighedspsykologi/output/W##/`.
- Writes a request log per non-blocking episode: `*.mp3.request.json`.

Optional flags:
- `--skip-existing` to skip outputs that already exist.
- `--source-timeout SECONDS` / `--generation-timeout SECONDS` to override timeouts.
- `--dry-run` to print planned outputs and exit without generating audio.

## Output placement
- Weekly overview: `shows/personlighedspsykologi/output/W##/W## - Alle kilder.mp3`
- Per-reading: `shows/personlighedspsykologi/output/W##/W## - <reading>.mp3`
- Brief (Grundbog): `shows/personlighedspsykologi/output/W##/[Brief] W## - <reading>.mp3`
- Non-blocking request log: `shows/personlighedspsykologi/output/W##/*.mp3.request.json`

## Test log
- 2026-02-04: Ran `generate_week.py` with a temporary test week (W99) and three PDFs.
  - Weekly overview + per-reading + brief generation requests were successfully created (non-blocking).
  - One run timed out at 120s; rerun with 300s completed.
  - Output folder created at `tmp/personlighedspsykologi-test/output/W99/` with `sources_week.txt`.
- 2026-02-04: Downloaded W99 test audio artifacts into `tmp/personlighedspsykologi-test/output/W99/`.
  - First `download audio` for `W99 - Alle kilder.mp3` reported a temp rename error, but the file was created successfully.
