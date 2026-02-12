# Personlighedspsykologi

Scaffolding for the "Personlighedspsykologi" feed.

- `config.local.json` - local test run against a Drive folder.
- `config.github.json` - committed config for CI once secrets exist.
- `auto_spec.json` - W01-W22 schedule derived from the 2026 forelaesningsplan.
- `episode_metadata.json` - optional per-file overrides.
- `assets/cover.png` - square artwork (min. 1400x1400) referenced by the feed.
- `docs/` - planning material and any "important text" docs.

Feed note: `feed.reading_description_mode` is set to `topic_only` so per-reading episode descriptions are emitted as `Emne: <topic>`.

Update the Drive folder ID, owner email, and upload the service account credentials before enabling automation.
