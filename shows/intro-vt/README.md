# Intro + VT Deep Dives - Hold 1 - 2024

This show is live. Published audio now comes from Cloudflare R2, while the legacy GitHub Actions workflow still imports source files from Drive before regenerating the feed.

Primary files:

- `config.github.json` - live workflow config; `storage.provider = "r2"` with workflow-managed Drive source import.
- `config.local.json` - local test config matching the live publication model.
- `config.template.json` - template for rebuilding local or CI config variants.
- `media_manifest.r2.json` - canonical published-object inventory for the R2-backed feed.
- `auto_spec.json` - optional mapping of source folders to canonical publish dates.
- `episode_metadata.json` - optional per-file overrides.
- `feeds/rss.xml` - generated live RSS feed.
- `assets/cover.png` - square artwork referenced by the feed.

Operational note:

- Drive is still the source-side ingest path for this show.
- R2 is now the public audio hosting layer.
- The show remains `publication.owner = "legacy_workflow"`.
