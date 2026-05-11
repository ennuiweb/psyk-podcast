# Personlighedspsykologi (Dansk Mirror)

This folder owns the Danish publication surface for `personlighedspsykologi`.

Shared subject inputs are intentionally reused from the canonical
`personlighedspsykologi-en` substrate:

- lecture schedule via `shows/personlighedspsykologi-en/auto_spec.json`
- episode metadata via `shows/personlighedspsykologi-en/episode_metadata.json`
- important-text docs under `shows/personlighedspsykologi-en/docs/`

This folder owns only Danish mirror publication artifacts and show config.

Current mirror contract:

- queue-owned
- R2-backed
- audio-first
- no Freudd portal sidecars
- Spotify episode-link indexing enabled via the Danish Spotify show
- no Danish summary cache yet; feed descriptions intentionally use text links
  only to avoid mixed-language summary prose

Runtime layer:

- prompt config: `notebooklm-podcast-auto/personlighedspsykologi-da/prompt_config.json`
- output root: `notebooklm-podcast-auto/personlighedspsykologi-da/output`

Publication outputs:

- `config.github.json` - canonical queue/feed config
- `config.local.json` - compatibility copy kept identical to `config.github.json`
- `media_manifest.r2.json` - queue-managed published audio manifest
- `spotify_map.json` - generated direct Spotify episode-link index once
  Spotify has ingested matching Danish feed episodes

Spotify map note:

- Danish show URL:
  `https://open.spotify.com/show/19kk5Oj0ftw4RdQIP46nB4`
- `scripts/sync_spotify_map.py` syncs
  `shows/personlighedspsykologi-da/spotify_map.json` from
  `episode_inventory.json`.
- The file format matches the English show: version `2`, with
  `by_episode_key` as the primary map and `by_rss_title` as a compatibility
  fallback.
