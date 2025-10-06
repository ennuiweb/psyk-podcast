# Socialpsykologi oplæst - 1. sem 2025

Scaffolding for the "Socialpsykologi oplæst - 1. sem 2025" feed. Prepare these files before enabling automation:

- `config.local.json` – local test run against the Drive folder that stores oplæste episoder.
- `config.github.json` – committed config for CI once the Drive secrets are available.
- `auto_spec.json` – copies the deep-dive schedule so each uge folder maps to the right publish date.
- `episode_metadata.json` – optional per-fil overrides for titles, beskrivelser, publiceringstidspunkter og artwork.
- `assets/cover.png` – kvadratisk artwork (min. 1400×1400) som feedet henviser til.

Kopiér `.template.json`-filerne og udfyld dem med rigtige værdier, opdater Drive-mappen og upload servicekontoen, før workflowet kører.
