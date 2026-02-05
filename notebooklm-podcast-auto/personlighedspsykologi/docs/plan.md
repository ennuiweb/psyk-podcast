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
  - Prompt: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
  - Language: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
- Per-reading episode: one per reading in each week folder.
  - Format: `deep-dive`
  - Length: `default`
  - Prompt: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
  - Language: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
- Brief variants: every **Grundbog kapitel** gets an extra brief version.
  - Format: `brief`
  - Length: not set (UI does not expose length for brief; config value is ignored)
  - Prompt: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
  - Language: from `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
  - Name prefix: `[Brief]`
 - Language variants: generate **Danish + English** for all episodes.
   - Config: `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` → `languages`
   - English naming: adds suffix ` [EN]` to file names and notebook titles.

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
  - `notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md`
- Source inventory currently lives in:
  - OneDrive: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

## Socialpsykologi reference used
- Drive structure: week folders containing `kilder/` + MP3s at week root.
- Feed file: `shows/social-psychology/feeds/rss.xml` (shows mixed per-week + per-reading + brief pattern).

## Next execution steps (pending)
1. Sync OneDrive readings into `notebooklm-podcast-auto/personlighedspsykologi/sources/W## …`.
2. Apply filename renames for `W## X` highlights and `[Brief]` variants.
3. Generate audio via NotebookLM (non-blocking) and record `artifact_id`s.
4. Download completed MP3s.
5. Upload MP3s to Drive week folders.
6. Run local feed build for validation.

## Week generation command
Command (non-blocking by default, add `--wait` to block):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W04 --profile default
```

Multiple weeks in one command:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --weeks W01,W02,W03 --profile default
```

This command:
- Uses `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` for prompts/lengths.
- Skips weekly “Alle kilder” when missing readings are listed for that week.
- Emits MP3s to `notebooklm-podcast-auto/personlighedspsykologi/output/W##/`.
- Writes a request log per non-blocking episode: `*.mp3.request.json`.
- Empty prompts are allowed (no validation).
- Continues on per-episode failures and prints a failure summary at the end (non-zero exit).

Optional flags:
- `--skip-existing` (default) to skip outputs that already exist.
- `--no-skip-existing` to force re-generation.
- `--print-downloads` (default) to print wait/download commands.
- `--no-print-downloads` to disable printing.
- `--source-timeout SECONDS` / `--generation-timeout SECONDS` to override timeouts.
- `--artifact-retries N` / `--artifact-retry-backoff SECONDS` to retry artifact creation (default retries: 2).
- `--dry-run` to print planned outputs and exit without generating audio.
- `--print-downloads` to print `artifact wait` + `download audio` commands for this run (requires non-blocking mode).
- `--output-profile-subdir` to nest outputs under a profile-based subdirectory (profile name or storage file stem).
- Auth pass-through:
  - `--profile NAME` (uses `profiles.json` from `notebooklm-podcast-auto/` or `--profiles-file`)
  - `--profiles-file PATH` (custom profile map)
  - `--storage PATH` (explicit storage file; cannot be combined with `--profile`)
- Auto-selection: if no profile is provided, `default` (or the only profile) from `profiles.json` is used automatically.

## Output placement
- Weekly overview: `notebooklm-podcast-auto/personlighedspsykologi/output/W##/W## - Alle kilder.mp3`
- Per-reading: `notebooklm-podcast-auto/personlighedspsykologi/output/W##/W## - <reading>.mp3`
- Brief (Grundbog): `notebooklm-podcast-auto/personlighedspsykologi/output/W##/[Brief] W## - <reading>.mp3`
- English variants add ` [EN]` before `.mp3`.
- Non-blocking request log: `notebooklm-podcast-auto/personlighedspsykologi/output/W##/*.mp3.request.json`
- Failed generation error log: `notebooklm-podcast-auto/personlighedspsykologi/output/W##/*.mp3.request.error.json`
- With `--output-profile-subdir`, outputs are nested under `.../output/<profile>/W##/`.
- Collision handling: if an output file exists and appears tied to a different auth, a ` [<profile>]` suffix is added automatically to avoid overwrites.

## Await + download (per week)
Use request logs to wait for completion and download MP3s, skipping already-downloaded files:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01
```

Multiple weeks:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W01,W02
```

Optional flags:
- `--timeout SECONDS` / `--interval SECONDS` for wait polling.
- `--dry-run` to print what would run.
- `--output-profile-subdir` to read outputs from a profile-based subdirectory (requires `--profile` or `--storage`).
- Auth resolution:
  - Uses per-log `auth.storage_path` when present.
  - Overrides: `--storage PATH` or `--profile NAME` (with `--profiles-file`).
  - If auth is missing or fails, automatically tries all profiles in `profiles.json`, then falls back to default `~/.notebooklm/storage_state.json`.

## Validation checklist
- Generate a single week with `--profile` and confirm `*.request.json` includes `auth.storage_path`.
- Run `download_week.py --dry-run` and verify the `AUTH:` line points at the expected storage file.
- If using `--output-profile-subdir`, confirm outputs land under `.../output/<profile>/W##/`.

## Test log
- 2026-02-04: Ran `generate_week.py` with a temporary test week (W99) and three PDFs.
  - Weekly overview + per-reading + brief generation requests were successfully created (non-blocking).
  - One run timed out at 120s; rerun with 300s completed.
  - Output folder created at `tmp/personlighedspsykologi-test/output/W99/` with `sources_week.txt`.
- 2026-02-04: Downloaded W99 test audio artifacts into `tmp/personlighedspsykologi-test/output/W99/`.
  - First `download audio` for `W99 - Alle kilder.mp3` reported a temp rename error, but the file was created successfully.
