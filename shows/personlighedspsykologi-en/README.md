# Personlighedspsykologi

Scaffolding for the "Personlighedspsykologi" feed.

- `config.github.json` - canonical config for both CI and local runs.
- `config.local.json` - compatibility copy kept identical to `config.github.json`.
- `auto_spec.json` - W01-W22 schedule derived from the 2026 forelaesningsplan.
- `episode_metadata.json` - optional per-file overrides.
- `regeneration_registry.json` - tracked A/B rollout state for original (`A`) vs regenerated (`B`) variants per logical episode.
- `reading_summaries.json` - cached per-reading summary + key-points blocks for episode descriptions.
- `assets/cover-new.png` - square artwork (min. 1400x1400) referenced by the feed.
- `docs/` - planning material and any "important text" docs.

Feed note: generated episode `title` and `description` are block-composed. Use `feed.title_blocks` / `feed.description_blocks` (and optional `*_by_kind`) for formatting control.
Block note: this show uses compact title form `U12F1 · <emne>` via `course_week_lecture` + `audio_category_prefix_position: after_first_block`; short and lydbog variants are marked as `[Kort]` / `[Lydbog]`, while normal/lang podcasts have no extra prefix. `feed.description_prepend_semester_week_lecture: true` prepends `Semesteruge X, Forelæsning Y` as a heading with a blank line before the next description block. `feed.semester_week_number_source: "lecture_key"` keeps title/description week labels aligned to the `W##L#` token.
Title alias note: `feed.compact_grundbog_subjects: true` first rewrites `Grundbog kapitel N - ...` to `Grundbog N: ...`, and `feed.title_subject_aliases` can then shorten listener-facing subjects further without changing source filenames, for example `Grundbog 8: Personlighed, subjektivitet og historicitet` -> `Grundbog 8: Historicitet`.
Spotify note: `feed.description_blank_line_marker: "·"` converts blank lines in descriptions to a visible separator line (`·`) for apps that collapse empty lines.
Description order note: for `reading`, `short`, and `weekly_overview`, `feed.description_blocks_by_kind` is set to `quiz -> summary -> key points`; when no quiz link exists, the summary/key-points blocks render without the quiz block.
Quiz localization note: `quiz.labels` controls heading and difficulty labels in descriptions (currently `Quizzer` with `Let/Mellem/Svær`).
Feed ordering note: `feed.sort_mode: "wxlx_source_pair_priority"` groups by `W#L#` and orders each lecture block as `ALLE KILDER -> [Kort] + full reading pairs -> [Kort] + full Forelæsningsslides pair -> [Lydbog] tail`; source pairs use natural reading order with Grundbog chapters sorted by chapter number.
Regeneration note: feed generation now selects the public A/B variant directly from `regeneration_registry.json` per `logical_episode_id`. Active regenerated `B` variants render with `✦` prepended to the title. Regex excludes are no longer the rollout mechanism.
Slide short note: short generation is intentionally limited to all readings plus lecture slides (`short.apply_to: "readings_and_lecture_slides"`; the older config key is still accepted). Exercise slides keep their full podcast variants but do not get `Kort podcast` entries under the shared `Forelæsningsslides` label.
Slide short audit note: the queue-owned publish path still fails closed on
slide-brief coverage gaps. Code changes alone do not make the feed compliant;
missing lecture-slide short MP3s must still be generated, downloaded, and
published before the queue can complete the expected `Kort podcast ·
Forelæsningsslides` entries.
Unassigned TTS note: audio files without week tokens (for example in Drive folder `grundbog-tts/`) are auto-scheduled before week 1 and therefore render at the end of the feed.
Grundbog tail note: `feed.tail_grundbog_lydbog` is enabled for this show and synthesizes a canonical tail block of `[Lydbog]` entries for `forord` plus configured Grundbog chapters. `drop_source_lydbog_items: true` keeps the canonical `[Lydbog]` RSS items and suppresses the redundant lecture-context `Lydbog` items for the same Grundbog sources. These tail items are feed-level constructs, not extra uploads: each item reuses the underlying published enclosure URL but gets a synthetic GUID suffix like `<base-guid>#tail-grundbog-chapter-8` so podcast clients treat the tail entry as a distinct feed item.
Feed pubDate note: `feed.pubdate_year_rewrite` rewrites only item `<pubDate>` year tokens during generation (for this show: `2026 -> 2025`) and does not change channel `<lastBuildDate>`.

Reading-summary workflow:
- Policy: all `summary_lines` and `key_points` content in this show is written manually. No auto-summary generation step is used or permitted in the normal workflow.
- Script scope: `sync_reading_summaries.py` is only for scaffolding missing entries, migrating stale keys, building weekly overview drafts from existing manual reading summaries, and validating coverage.
- Scaffold/update cached entries from local episodes:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py`
- Manually write the missing prose directly in `shows/personlighedspsykologi-en/reading_summaries.json`.
- Scaffold/update per-lecture `Alle kilder` cache from reading-summary coverage + draft aggregate:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview`
- Manually finalize the weekly overview prose directly in `shows/personlighedspsykologi-en/weekly_overview_summaries.json`.
- Validate completeness (warn-only):
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly`
- Build feed after sync:
  - `./notebooklm-podcast-auto/.venv/bin/python podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.github.json`
- Validate registry vs. generated inventory:
  - `./notebooklm-podcast-auto/.venv/bin/python scripts/validate_regeneration_inventory.py --show-slug personlighedspsykologi-en`
- Sync behavior:
  - uses local audio files (`.mp3`/`.wav`) to discover non-weekly episode keys, including reading, slide, short, and `TTS` variants.
  - excludes `Alle kilder` / `All sources` files from the reading summary inventory.
  - preserves existing filled entries and only adds missing placeholders in `reading_summaries.json`.
  - auto-migrates stale cache keys when episode filenames change but the lecture/title identity is still the same (for example `Alle kilder` -> `Alle kilder (undtagen slides)` or long-title -> short-title reading renames).
  - does not generate summary prose; placeholder rows must be filled by hand.
  - run scaffold/update before validation when checking a fresh cache (`--validate-only` reads current file contents only).
  - manual fill targets are `2-4` summary lines and `3-5` key points per entry.
  - language rule: when the source text is Danish, write both `summary_lines` and `key_points` in Danish (otherwise keep English).
  - `shows/personlighedspsykologi-en/reading_summaries.json` is the combined file to edit and commit.
  - `Alle kilder` cache is `shows/personlighedspsykologi-en/weekly_overview_summaries.json`; entries are lecture-level (`W#L#`) and scaffolded from all source summaries for that lecture, then manually finalized in Danish.
  - weekly validation is warn-only for missing entries, incomplete fields, non-Danish content, and source coverage gaps.

Feed build prerequisites: install the repo requirements, then run the feed
generator or queue commands against the R2-backed show config.
Troubleshooting: if system Python shows `Missing Google API dependencies`, run
with `./notebooklm-podcast-auto/.venv/bin/python` or install deps via `pip
install -r requirements.txt`.
Troubleshooting: warning `missing Grundbog lydbog tail source(s)` means one or
more expected tail chapters are absent in the published inventory; feed
generation still completes, but those tail entries are skipped.
Troubleshooting: when comparing RSS items to storage inventory, expect the
synthetic Grundbog tail items to look like feed-only entries because their GUIDs
append `#tail-grundbog-*` to the base item identity by design.

Inventory-first note:
- Feed generation now writes both `feeds/rss.xml` and `episode_inventory.json`.
- Freudd manifest rebuilds consume `episode_inventory.json` as the primary podcast source and only fall back to RSS if the inventory file is unavailable.
- This keeps manifest generation aligned with the published storage inventory even when Spotify mappings are incomplete.

Quiz link sync note:
- `scripts/sync_quiz_links.py` and `podcast-tools/sync_drive_quiz_links.py` use quiz JSON exports as the source of truth.
- Slide-only quiz exports should be synced with fallback-derived names so they still get quiz IDs and appear on Freudd even when no matching MP3 exists (`--fallback-derive-mp3-names` for sync workflows).
- `shows/personlighedspsykologi-en/quiz_links.json` intentionally keeps `.html` relative paths so public links remain `/q/<id>.html`, and all entries include `subject_slug`.
- Feed generation uses `quiz.base_url = https://freudd.dk/q/` so podcast descriptions link to the domain (not raw IP).
- Feed transcode now also covers `audio/wav` and `audio/x-wav`, so lydbog/TTS uploads are converted to MP3 before RSS generation instead of being published as raw WAV files.

Spotify map sync note:
- `scripts/sync_spotify_map.py` syncs `shows/personlighedspsykologi-en/spotify_map.json` from `episode_inventory.json`.
- The file format is version `2` with `by_episode_key` as the primary map and `by_rss_title` retained as a compatibility fallback.
- Existing valid Spotify episode mappings are preserved.
- If Spotify show lookup succeeds (`--spotify-show-url` + `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET`), matching inventory episodes are mapped to direct episode URLs.
- Non-episode mappings are rejected.
- Unresolved inventory episodes fail sync by default (no Spotify search fallback is allowed).
- With `--allow-unresolved`, sync writes resolved episode URLs and records unresolved entries under `unresolved_episode_keys` / `unresolved_rss_titles`.
- Workflow sync runs with `--prune-stale`, so removed inventory episodes are also removed from `by_episode_key`.
- Workflow `generate-feed.yml` runs this sync automatically for `personlighedspsykologi-en`.

Reading key sync note:
- Source of truth file: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/.ai/reading-file-key.md`
- Primary repo mirror used by feed config: `shows/personlighedspsykologi-en/docs/reading-file-key.md`
- Sync commands:
  - Dry-run: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py`
  - Apply: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --apply`
  - Optional compatibility target: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --secondary-target <path> --apply`
  - Stable fallback mode is default: if OneDrive source is unavailable, primary repo mirror is used as source.
  - Strict mode (fail when source missing): `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --strict-source --apply`
  - One-time bootstrap source from current repo file: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --bootstrap-source-from-repo --apply`
  - Invariant check: `python3 scripts/check_personlighedspsykologi_artifact_invariants.py`

Slides mapping note (manual only):
- Slide mapping til `W##L#` + underkategori skal udføres manuelt.
- Automatisk mapping med script er ikke tilladt.
- Fag-runbook: `shows/personlighedspsykologi-en/docs/slides-sync.md`
- Global policy: `freudd_portal/docs/slides-mapping-policy.md`
- Catalog: `shows/personlighedspsykologi-en/slides_catalog.json`
- Upload target: `/var/www/slides/personlighedspsykologi`
