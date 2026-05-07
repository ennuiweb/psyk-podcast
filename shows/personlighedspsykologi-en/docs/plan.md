# Personlighedspsykologi Show Plan

This file is the compact show-level plan for `shows/personlighedspsykologi-en`.
NotebookLM generation mechanics live in
`notebooklm-podcast-auto/personlighedspsykologi/docs/plan.md`.

## Source Of Truth

| Area | Canonical file |
|---|---|
| Show config | `shows/personlighedspsykologi-en/config.github.json` |
| Local compatibility config | `shows/personlighedspsykologi-en/config.local.json` must remain identical to `config.github.json` |
| Lecture and feed matching | `shows/personlighedspsykologi-en/auto_spec.json` |
| Manual episode overrides | `shows/personlighedspsykologi-en/episode_metadata.json` |
| Reading summaries | `shows/personlighedspsykologi-en/reading_summaries.json` |
| Weekly overview summaries | `shows/personlighedspsykologi-en/weekly_overview_summaries.json` |
| Reading key mapping | `shows/personlighedspsykologi-en/docs/reading-file-key.md` |
| Slide mapping | `shows/personlighedspsykologi-en/slides_catalog.json` |
| Learning-material output scope and evaluation | `shows/personlighedspsykologi-en/docs/learning-material-outputs.md` |
| Artifact ownership | `shows/personlighedspsykologi-en/docs/podcast-flow-artifacts.md` |
| Operational runbook | `shows/personlighedspsykologi-en/docs/podcast-flow-operations.md` |

## Storage And Publication

- `storage.provider` is now `r2`, and `publication.owner` is now `queue`.
- `shows/personlighedspsykologi-en/media_manifest.r2.json` is the canonical
  published-audio inventory.
- Preserved `source_drive_file_id` fields in the manifest and generated
  inventory are now historical compatibility metadata for regeneration
  validation, not an active ingest contract.
- Live publication no longer depends on Drive source import or service-account
  credentials.

## Public Output Policy

- Feed-visible episodes are lecture-key based (`W##L#`).
- `Alle kilder (undtagen slides)` is a lecture-level overview and excludes
  slides from its source count.
- Feed ordering uses `feed.sort_mode: "wxlx_kind_priority"` with this priority
  inside each lecture block: `Short -> Alle kilder -> Oplæst/TTS readings ->
  other readings`.
- Semester labels use `feed.semester_week_number_source: "lecture_key"` so
  listener-facing `Semesteruge X` stays aligned with each `W##L#`.
- Public slide shorts are lecture-slide shorts only. Exercise slides may exist
  as local generation inputs, but must not publish as `Kort podcast ·
  Forelæsningsslides`.
- Feed title cleanup is handled by `podcast-tools/gdrive_podcast_feed.py`; do
  not rename source files solely to change public prefixes.

## Reading And Summary Maintenance

- The canonical reading-key source of truth is
  `shows/personlighedspsykologi-en/docs/reading-file-key.md`.
- The OneDrive `.ai/reading-file-key.md` copy is an exported mirror for
  non-repo workflows and should not be edited during normal operation.
- Important readings are marked by filenames starting with `W##L# X` and are
  surfaced through show metadata as `[Gul tekst]` / important reading context.
- Reading summary cache is manual and local-first:
  `shows/personlighedspsykologi-en/reading_summaries.json`.
- Weekly overview summaries are manual Danish summaries in
  `shows/personlighedspsykologi-en/weekly_overview_summaries.json`.
- Legacy workflow coverage validation is still warn-only for day-to-day feed
  generation. The queue-owned publication path is stricter and may block on
  missing manual summary content before any future ownership cutover.

## Quiz Links

- Quiz uploads are subject-isolated under the `personlighedspsykologi` slug.
- `shows/personlighedspsykologi-en/quiz_links.json` maps audio/episode names to
  quiz URLs and difficulty metadata.
- The local sync path remains:

```bash
python3 scripts/sync_quiz_links.py --quiz-difficulty any --dry-run
python3 scripts/sync_quiz_links.py --quiz-difficulty any
```

- Feed item links prefer the medium quiz URL when multiple difficulties exist.

## Standard Validation

Run these before committing show-level contract changes:

```bash
python3 scripts/check_personlighedspsykologi_artifact_invariants.py
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
./.venv/bin/python podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.github.json --dry-run
```

Expected non-blocking warnings may include missing reading summaries or existing
content gaps. Treat new structural, import, or
inventory-mismatch errors as blockers.

## Publishing

After show-level docs/config/feed changes:

1. Commit and push to `origin/main`.
2. Run `gh workflow run generate-feed.yml --ref main`.
3. Confirm queue publication or queue downstream validation succeeds for `personlighedspsykologi-en`.
4. Deploy Freudd only when the portal, manifest, quiz hosting, or served assets
   changed.
