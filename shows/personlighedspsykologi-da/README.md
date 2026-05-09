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
- no Spotify sync by default
- no Danish summary cache yet; feed descriptions intentionally use text links
  only to avoid mixed-language summary prose

Runtime layer:

- prompt config: `notebooklm-podcast-auto/personlighedspsykologi-da/prompt_config.json`
- output root: `notebooklm-podcast-auto/personlighedspsykologi-da/output`

Publication outputs:

- `config.github.json` - canonical queue/feed config
- `config.local.json` - compatibility copy kept identical to `config.github.json`
- `media_manifest.r2.json` - queue-managed published audio manifest
