# Spotify Transcripts

## Scope

This document covers the local-first Spotify transcript downloader for show episodes
that already have direct Spotify episode mappings in `spotify_map.json`.

Phase 1 only downloads and normalizes transcript artifacts. It does not change
Freudd rendering or the feed workflow.

## Why this is separate

- Feed generation is deterministic and CI-friendly.
- Spotify transcript capture is browser-authenticated and session-sensitive.
- The downloader therefore runs as a standalone local tool, not inside
  `.github/workflows/generate-feed.yml`.

## Code layout

- `spotify_transcripts/` - package for discovery, auth paths, storage, normalization, and sync orchestration.
- `scripts/spotify_transcripts.py` - thin CLI wrapper.
- `requirements-spotify-transcripts.txt` - optional dependency set for Playwright.

## Artifact layout

Artifacts are written per show under:

- `shows/<show-slug>/spotify_transcripts/manifest.json`
- `shows/<show-slug>/spotify_transcripts/queue.json`
- `shows/<show-slug>/spotify_transcripts/raw/<episode_key>.json`
- `shows/<show-slug>/spotify_transcripts/normalized/<episode_key>.json`
- `shows/<show-slug>/spotify_transcripts/vtt/<episode_key>.vtt`
- `shows/<show-slug>/spotify_transcripts/exports/<show-slug>.combined.json`

`manifest.json` is the status ledger. Raw payloads are stored unchanged, while
normalized payloads and VTT exports are repo-owned formats that shield future
consumers from Spotify schema churn.

The entire `shows/**/spotify_transcripts/` tree is ignored by git. Queue state
and downloaded transcript payloads are local operational artifacts, not tracked
repo source files.

## Local auth state

Local browser state is kept outside the repo:

- Home dir: `~/.spotify-transcripts` or `$SPOTIFY_TRANSCRIPTS_HOME`
- Browser profile: `browser_profile/`
- Saved state: `storage_state.json`

The tool uses `0700` permissions for directories and `0600` for saved state.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -r requirements-spotify-transcripts.txt
.venv/bin/playwright install chromium
```

## Login

```bash
python3 scripts/spotify_transcripts.py login
python3 scripts/spotify_transcripts.py auth-status
```

`login` opens Spotify Web in a persistent Playwright profile. Complete login in
the browser window, then press Enter in the terminal to save session state.

The wrapper script auto-reexecs into `./.venv/bin/python` when that venv exists,
so `python3 scripts/spotify_transcripts.py ...` will use the repo venv by default.

## Sync

Example:

```bash
python3 scripts/spotify_transcripts.py sync --show-slug personlighedspsykologi-en
python3 scripts/spotify_transcripts.py sync --show-slug bioneuro --limit 5
python3 scripts/spotify_transcripts.py sync --show-slug bioneuro --episode-key 1m2pnGMr6HHg4hYqo6T257f2882RsVGlg
```

Behavior:

- Reads `episode_inventory.json` and `spotify_map.json`
- Requires a direct `by_episode_key` Spotify episode URL
- Marks unmapped inventory episodes as `missing_mapping`
- Skips already downloaded episodes unless `--force` is used
- Captures the live transcript response from Spotify rather than scraping DOM text

## Queue workflow

Build or refresh the queue from the current inventory + Spotify map:

```bash
python3 scripts/spotify_transcripts.py queue-build --show-slug personlighedspsykologi-en
python3 scripts/spotify_transcripts.py queue-report --show-slug personlighedspsykologi-en
```

Drain pending queue entries:

```bash
python3 scripts/spotify_transcripts.py queue-run --show-slug personlighedspsykologi-en
python3 scripts/spotify_transcripts.py queue-run --show-slug personlighedspsykologi-en --limit 10
```

Queue behavior:

- `pending` means mapped and not yet downloaded
- `done_downloaded` means a normalized transcript artifact already exists
- `blocked_missing_mapping` means the episode has no direct Spotify episode URL
- `failed` means the last queue attempt failed and should be retried explicitly by running `queue-run` again

The queue runner is intentionally single-worker by default. Parallel workers are
not enabled yet because Spotify Web session state and transcript loading are
still browser/session-sensitive, and a single-worker queue is the safer baseline.

## Status model

Effective entry statuses:

- `downloaded`
- `missing_mapping`
- `no_transcript_available`
- `auth_required`
- `playback_required`
- `market_restricted`
- `schema_changed`
- `network_error`
- `unknown_failure`

`last_attempt_status` records the latest sync outcome even when an older
successful transcript artifact is still present.

## Reporting

```bash
python3 scripts/spotify_transcripts.py report --show-slug personlighedspsykologi-en
```

This summarizes the per-show manifest without touching Spotify.

## Export

```bash
python3 scripts/spotify_transcripts.py export-show --show-slug personlighedspsykologi-en
python3 scripts/spotify_transcripts.py export-show --show-slug personlighedspsykologi-en --output-name personality.json
```

This combines the normalized per-episode transcript artifacts into one show-level
JSON file under `spotify_transcripts/exports/`.

Export behavior:

- preserves inventory order from `episode_inventory.json`
- includes full segment arrays plus a flattened `transcript_text` field per episode
- includes `omitted_episodes` with explicit reasons when some inventory episodes
  are not exportable, such as missing Spotify mappings or missing manifest entries

## Operational boundaries

- Do not add this downloader to the feed CI workflow in its current form.
- Do not store Spotify auth cookies in the repo, `.aimemory/`, or CI secrets.
- If Spotify episode mappings are incomplete, fix `spotify_map.json` first with
  `scripts/sync_spotify_map.py`; transcript sync will not guess missing URLs.
