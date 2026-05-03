# NotebookLM Automation

## Scope

This document covers the repo-level NotebookLM automation layout and the subject wrappers that depend on it.

Current migration program:

- The cross-cutting implementation plan for moving NotebookLM orchestration to a Hetzner-owned queue and moving published audio off Google Drive lives in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).
- The current shipped checkpoint for that migration lives in [notebooklm-queue-current-state.md](notebooklm-queue-current-state.md).

Current operational note:

- Shared NotebookLM generation now tries to reclaim per-account notebook capacity on `CREATE_NOTEBOOK` failures by deleting the oldest safe owned notebook on that account and retrying once before profile rotation takes over; reclaim skips notebooks with pending artifacts or local request logs whose target output is still missing.

## Layout

- `notebooklm-podcast-auto/personlighedspsykologi/` - Personlighedspsykologi wrapper scripts, docs, tests, and evaluation assets.
- `notebooklm-podcast-auto/bioneuro/` - Bioneuro wrapper scripts and output flow.
- `notebooklm-podcast-auto/notebooklm-py/` - tracked submodule with the underlying client, docs, and test surface.
- `notebooklm_queue/` - queue-core package for the Hetzner migration path: durable job store, state machine, lock handling, and CLI.
- `scripts/notebooklm_queue.py` - local wrapper that re-execs into `.venv` and exposes the queue CLI.

## Primary commands

Personlighedspsykologi:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

Bioneuro:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

## Output and mirrors

Default output roots:

- `notebooklm-podcast-auto/personlighedspsykologi/output`
- `notebooklm-podcast-auto/bioneuro/output`

Mirror helper:

- `scripts/mirror_output_dirs.py`
- `scripts/notebooklm_queue.py`

Examples:

```bash
python3 scripts/mirror_output_dirs.py --subject bioneuro --dry-run
python3 scripts/mirror_output_dirs.py --subject personlighedspsykologi --dry-run
python3 scripts/mirror_output_dirs.py --subject all
```

Pre-push currently mirrors both subjects, but mirror failures are warning-only.

Queue-core note:

- the first queue-core implementation now exists, but it is intentionally only the control-plane foundation
- current scope is durable job persistence, idempotent enqueue, state transitions, show locks, indexes, adapter-based discovery, and a management CLI
- current scope now also includes real queue-owned generate/download execution for supported shows, with per-run manifests and state transitions up to `awaiting_publish`
- current scope now also includes publish-bundle preparation: `prepare-publish` validates the local week output, blocks on leftover request logs or missing required artifacts, persists a publish manifest, and advances successful jobs to `approved_for_publish`
- current scope now also includes the first real publication stage: `upload-r2` claims jobs in `approved_for_publish`, uploads media artifacts to deterministic R2 object keys, verifies each uploaded object with `head_object`, refreshes the repo-side R2 media manifest, and advances successful jobs to `objects_uploaded`
- current scope now also includes repo metadata rebuild: `rebuild-metadata` claims jobs in `objects_uploaded`, refreshes queue-owned quiz links for supported shows, regenerates RSS and episode inventory from the R2 manifest, runs show-specific sidecars such as Spotify sync and Freudd content-manifest rebuild, validates the resulting repo artifacts, and advances successful jobs to `committing_repo_artifacts`
- current scope now also includes allowlisted repo publication: `push-repo` claims jobs in `committing_repo_artifacts`, fails closed on tracked repo dirtiness outside the generated-file allowlist, keeps queue-generated artifacts on allowlisted rebase conflicts, pushes with bounded retries, and advances successful jobs to `repo_pushed`
- current scope now also includes downstream completion: `sync-downstream` claims jobs in `repo_pushed`, waits for expected push-triggered downstream workflows such as `deploy-freudd-portal.yml`, and advances successful jobs to `completed`
- current scope now also includes pilot-safe config binding: `discover`, `prepare-publish`, `upload-r2`, `rebuild-metadata`, and `push-repo` accept `--show-config`, and publish manifests now pin the selected config path so later stages cannot silently drift back to the live `config.github.json`
- pilot-safe artifact routing now also covers Freudd sidecars: queue metadata rebuild and repo publication derive `quiz_links.json`, `spotify_map.json`, `content_manifest.json`, RSS, inventory, and R2 media-manifest paths from the selected show config instead of hardcoded live show paths
- storage root defaults to `/var/lib/podcasts/notebooklm-queue` and can be overridden with `NOTEBOOKLM_QUEUE_STORAGE_ROOT` or `--storage-root`
- supported discovery adapters currently cover `bioneuro` and `personlighedspsykologi-en`
- `run-dry` resolves the exact generate/download commands for the next queued lecture without touching NotebookLM or publication state
- `run-once` claims or resumes a job, executes the real generate/download wrappers, persists a run manifest under the queue storage root, and moves successful jobs to `awaiting_publish`
- `prepare-publish` claims or resumes a job in `awaiting_publish`, scans the canonical output directory for that lecture, writes a durable publish manifest under the queue storage root, and moves successful jobs to `approved_for_publish`
- `upload-r2` is intentionally R2-only for now; Drive-backed shows are blocked explicitly until their show config is migrated to `storage.provider = "r2"`
- `sync-downstream` currently validates the existing Freudd deploy workflow for `bioneuro` and `personlighedspsykologi-en` when queue-owned pushes touch `content_manifest.json`, `quiz_links.json`, or `spotify_map.json`; explicit show-ownership gating in `generate-feed.yml` still belongs to a later migration phase

Queue CLI examples:

```bash
./.venv/bin/python scripts/notebooklm_queue.py discover --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue discover --repo-root . --show-slug bioneuro --enqueue
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-dry --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-once --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue prepare-publish --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue upload-r2 --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue rebuild-metadata --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue push-repo --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue sync-downstream --repo-root . --show-slug bioneuro
```

Pilot-safe example:

```bash
cp shows/bioneuro/config.r2-pilot.template.json /tmp/bioneuro-r2-pilot.json
# fill in storage.public_base_url before use
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue discover --repo-root . --show-slug bioneuro --show-config /tmp/bioneuro-r2-pilot.json --enqueue
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue prepare-publish --repo-root . --show-slug bioneuro --show-config /tmp/bioneuro-r2-pilot.json
```

Important operational note:

- `notebooklm-podcast-auto/personlighedspsykologi/output` must be a real directory, not a macOS Alias file. Alias files break the shared mirror step and create noisy pre-push warnings.
- `scripts/mirror_output_dirs.py` reflects the current local Drive-mount era. It should be treated as transitional infrastructure for subjects that have not yet migrated to object storage.

## Personlighedspsykologi source rules

The canonical reading source is the absolute OneDrive Readings root:

- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

Relevant sync utilities:

- `scripts/sync_personlighedspsykologi_reading_file_key.py`
- `scripts/sync_personlighedspsykologi_readings_to_droplet.py`
- `notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py`

## Manual summary policy

Hand-authored summary sources:

- `shows/personlighedspsykologi-en/reading_summaries.json`
- `shows/personlighedspsykologi-en/weekly_overview_summaries.json`

`sync_reading_summaries.py` validates and scaffolds, but it is not the source of final summary prose.

## Related docs

- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
- [../notebooklm-podcast-auto/notebooklm-py/docs/README.md](../notebooklm-podcast-auto/notebooklm-py/docs/README.md)
- [README.md](README.md)
