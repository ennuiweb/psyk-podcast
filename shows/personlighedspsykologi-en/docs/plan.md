# Implementation Plan (Personlighedspsykologi F26)

## Status summary
- Show scaffolding already exists (`config.*`, `auto_spec.json`, `episode_metadata.json`).
- Socialpsykologi feed review confirms a mixed output pattern:
  - Lecture-overview episodes (kind: `weekly_overview`, e.g., "Alle kilder")
  - Per-reading episodes
  - Short "[Brief]" variants for some readings
- Local feed build requires `shows/personlighedspsykologi-en/service-account.json` plus Google dependencies (`google-auth`, `google-api-python-client`); run with `python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json`.

## Output policy (decisions)
- Weekly overview kind: **"Alle kilder"** episode per lecture (`W#L#`; two lectures per week).
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
  - Source filename marker: `[Brief]`
- Language variants: generate **Danish + English** for all episodes.
   - Config: `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` → `languages`
   - English naming: adds suffix ` [EN]` to file names and notebook titles.
- Feed output (audio only): `gdrive_podcast_feed.py` strips `[EN]`; for `shows/personlighedspsykologi-en` it inserts `[Lydbog]`/`[Kort podcast]`/`[Podcast]` after the first title block (for other shows, default remains leading prefix), and falls back to `[Podcast]` for any other audio episode.
- Feed copy cleanup removes `Reading:` and `Forelæsning x · Semesteruge x` patterns from episode titles/descriptions.
- Feed ordering uses `feed.sort_mode: "wxlx_kind_priority"` and applies per-`W#L#` priority: `Brief -> Alle kilder -> Oplæst/TTS readings -> other readings` (block order remains recency-based).
- Semester week alignment still follows `feed.semester_week_start_date` (2026-02-02), so lectures 1+2 are both Semesteruge 1. `Uge` labels reflect calendar weeks.
- Filename hygiene: always keep week tokens zero-padded (`W##L#`). If outputs contain unpadded tokens (e.g. `W6L1`), normalize via:
  - `python3 scripts/rename_personlighedspsykologi_outputs.py --root notebooklm-podcast-auto/personlighedspsykologi/output --apply --rewrite-request-json`

## Automation scope (decisions)
- **Per-episode notebooks only.** We are **not** using single-notebook + source-ID selection for now.
- **Source de-duplication on reuse.** When reusing a notebook, already-uploaded sources are skipped to avoid duplicates.

## Reading summaries (decisions)
- Source of truth is manual `shows/personlighedspsykologi-en/reading_summaries.json` (`by_name` map keyed by filename).
- Summary maintenance is local-only via `notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py` (no request-log/NotebookLM summary generation path).
- Local inventory includes reading/brief/TTS audio files (`.mp3` + `.wav`) and excludes weekly overview files matching `Alle kilder` / `All sources`.
- Workflow order is scaffold/update first, then `--validate-only`; coverage validation is warn-only for missing/incomplete entries.
- Target fill levels are 2-4 `summary_lines` and 3-5 `key_points` per episode.
- Language rule: if a source text is Danish, keep both `summary_lines` and `key_points` in Danish (otherwise keep English).
- `Alle kilder` source of truth is manual `shows/personlighedspsykologi-en/weekly_overview_summaries.json` (one entry per lecture, `W#L#`).
- `Alle kilder` summaries are scaffolded from all source summaries for the same lecture via `--sync-weekly-overview`, then manually finalized in Danish.
- `--validate-weekly` is warn-only and reports missing entries, incomplete fields, non-Danish content, and source coverage gaps.

## Highlighting / important readings
- `important_text_mode` is `week_x_only`.
- Only file names starting with `W##L# X` will be highlighted as `[Gul tekst]`.
- Reading map uses `W##L# X` prefixes; rename files to match when ready.
- Important readings currently prefixed with `X` in OneDrive are overridden in `shows/personlighedspsykologi-en/episode_metadata.json` to add an `X` to titles and append an "Important reading" note.

## Missing-file skip policy
- Skip audio generation for any episode whose source file is missing.
- Skip the **lecture-level "Alle kilder"** episode if any reading in that lecture is missing.

Single-file skips:
- W11: Funch & Roald (2014)
- W17: Jensen (2014)
- W20: Staunæs & Juelskjær (2014)
- W22: Køppe (2014)
- W22: Køppe & Dammeyer (2014b)

Lecture-level "Alle kilder" skips:
- W11
- W17
- W20
- W22

## Reading map
- The authoritative per-week reading list is in:
  - OneDrive source: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/.ai/reading-file-key.md`
  - Repo mirror for feed automation: `shows/personlighedspsykologi-en/docs/reading-file-key.md`
  - Repo mirror for NotebookLM docs: `notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md`
- Source inventory currently lives in:
  - OneDrive: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

## Socialpsykologi reference used
- Drive structure: week folders containing `kilder/` + MP3s at week root.
- Feed file: `shows/social-psychology/feeds/rss.xml` (shows mixed per-week + per-reading + brief pattern).

## Next execution steps (pending)
1. Sync OneDrive readings into `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings/W## …`.
2. Apply filename renames for `W##L# X` highlights and `[Brief]` variants.
3. Generate audio via NotebookLM (non-blocking) and record `artifact_id`s.
4. Download completed MP3s.
5. Upload MP3s to Drive week folders.
6. Run local feed build for validation.
7. Sync quiz HTML exports to the droplet and update quiz links.

## Quiz links (IP-first)
- Quiz HTMLs are hosted at:
  `http://64.226.79.109/quizzes/personlighedspsykologi/<Week>/<Filename>.html`
- GitHub Actions now generates quiz links from Drive HTML files (and uploads to the
  droplet if `DIGITALOCEAN_SSH_KEY` is configured). The Apps Script trigger must
  include `text/` in `mimePrefixes` to detect quiz HTML changes.
- Backward-compatibility rollout: keep a server alias from
  `/quizzes/personlighedspsykologi-en/` to `/quizzes/personlighedspsykologi/`
  during transition so previously published quiz links continue to resolve.

- Use the sync script locally to upload and update the mapping:

```bash
python3 scripts/sync_quiz_links.py --quiz-difficulty any --dry-run
python3 scripts/sync_quiz_links.py --quiz-difficulty any
```

- The mapping file is `shows/personlighedspsykologi-en/quiz_links.json`.
- Feed descriptions append all available quiz links per episode (`easy`, `medium`, `hard`) when mapping entries exist.
- Feed item `<link>` still prefers the `medium` quiz URL when available.

## Week generation command
Command (non-blocking by default, add `--wait` to block):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W02L2
```

Multiple weeks in one command:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --weeks W01,W02
```

This command:
- Uses `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` for prompts/lengths.
- Skips lecture-level “Alle kilder” for lecture keys with missing readings.
- Emits MP3s to `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/`.
- Writes a request log per non-blocking episode: `*.mp3.request.json`.
- Empty prompts are allowed (no validation).
- Continues on per-episode failures and prints a failure summary at the end (non-zero exit).
 
Note: passing `--week W01` (or `--weeks W01,W02`) expands to all matching `W01L#` folders.

Optional flags:
- `--skip-existing` (default) to skip outputs that already exist.
- `--no-skip-existing` to force re-generation.
- `--print-downloads` (default) to print wait/download commands.
- `--no-print-downloads` to disable printing.
- `--source-timeout SECONDS` / `--generation-timeout SECONDS` to override timeouts.
- `--artifact-retries N` / `--artifact-retry-backoff SECONDS` to retry artifact creation (default retries: 2).
- `--sleep-between SECONDS` to pause between generation requests (default: 2).
- `--dry-run` to print planned outputs and exit without generating audio.
- `--print-downloads` to print `artifact wait` + `download audio` commands for this run (requires non-blocking mode).
- `--output-profile-subdir` to nest outputs under a profile-based subdirectory (profile name or storage file stem).
- Auth pass-through:
  - `--profile NAME` (uses `profiles.json` from `notebooklm-podcast-auto/` or `--profiles-file`)
  - `--profiles-file PATH` (custom profile map)
  - `--storage PATH` (explicit storage file; cannot be combined with `--profile`)
- Auto-selection: if no profile is provided, `default` (or the only profile) from `profiles.json` is used automatically. If multiple profiles exist and no default is set, the first profile (or one matching the default storage path) is selected with a warning.
- Rate-limit/auth rotation: by default, generation retries with the next available profile on rate-limit/auth errors (auto-profile only). Disable with `--no-rotate-on-rate-limit`.
- Source readiness: generation waits for sources to appear and become ready before creating artifacts. Disable with `--no-ensure-sources-ready`.
- Notebook titles: when rotating, profile labels are appended to notebook titles. Disable with `--no-append-profile-to-notebook-title`.
- Request logs: when `--skip-existing` is enabled (default), generation also skips outputs that already have a `.request.json` with an `artifact_id` and no error log.

## Output placement
- Weekly overview kind (lecture-level): `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/W##L# - Alle kilder.mp3`
- Per-reading: `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/W##L# - <reading>.mp3`
- Brief (Grundbog): `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/[Brief] W##L# - <reading>.mp3`
- English variants add ` [EN]` before `.mp3`.
- Non-blocking request log: `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/*.mp3.request.json`
- Failed generation error log: `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/*.mp3.request.error.json`
- With `--output-profile-subdir`, outputs are nested under `.../output/<profile>/W##L#/`.
- Collision handling: if an output file exists and appears tied to a different auth, a ` [<profile>]` suffix is added automatically to avoid overwrites.

## Await + download (week or lecture selectors)
Use request logs to wait for completion and download artifacts (audio + infographic + quiz by default), skipping already-downloaded files:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01L1
```

Multiple weeks:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W01,W02
```

Optional flags:
- `--content-types audio|infographic|quiz[,..]` to limit downloads to specific artifact types.
- `--timeout SECONDS` / `--interval SECONDS` for wait polling (defaults: 1800 / 15).
- The downloader now checks artifact status before waiting, and will skip artifacts already marked failed.
- `--dry-run` to print what would run.
- Request logs are archived to `*.request.done.json` after a successful download (or when the target file already exists); use `--no-archive-requests` to keep them in place.
- `--output-profile-subdir` to read outputs from a profile-based subdirectory (requires `--profile` or `--storage`).
- Auth resolution:
  - Uses per-log `auth.storage_path` when present.
  - Overrides: `--storage PATH` or `--profile NAME` (with `--profiles-file`).
  - If auth is missing or fails, automatically tries all profiles in `profiles.json`, then falls back to default `~/.notebooklm/storage_state.json`.
  - If no request logs are found under the chosen output root, automatically searches legacy output roots.

## Validation checklist
- Generate a single week with `--profile` and confirm `*.request.json` includes `auth.storage_path`.
- Run `download_week.py --dry-run` and verify the `AUTH:` line points at the expected storage file.
- If using `--output-profile-subdir`, confirm outputs land under `.../output/<profile>/W##L#/`.

## Test log
- 2026-02-04: Ran `generate_week.py` with a temporary test week (W99) and three PDFs.
  - Lecture-level Alle kilder + per-reading + brief generation requests were successfully created (non-blocking).
  - One run timed out at 120s; rerun with 300s completed.
  - Output folder created at `tmp/personlighedspsykologi-test/output/W99/` with `sources_week.txt`.
- 2026-02-04: Downloaded W99 test audio artifacts into `tmp/personlighedspsykologi-test/output/W99/`.
  - First `download audio` for `W99 - Alle kilder.mp3` reported a temp rename error, but the file was created successfully.
