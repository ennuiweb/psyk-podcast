# Podcast Flow Operations

Dette dokument beskriver drift og ændringsforløb for Personlighedspsykologi-flowet.
Det supplerer `podcast-flow-artifacts.md`, som kun beskriver ejerskab, artefakttyper
og afledningskæden.

## Canonical Sequence

1. Opdatér autoritative inputs i OneDrive, `slides_catalog.json`, canonical config eller manuelle summary-filer.
2. Sync `reading-file-key.md` til det primære repo-spejl, hvis OneDrive-kilden har ændret sig.
3. Generér eller download NotebookLM outputs efter behov.
4. Upload audio til Drive og quiz/slides til droplet efter de respektive flows.
5. Kør feed-build eller `generate-feed.yml`, så `rss.xml` og `episode_inventory.json` bliver genopbygget.
6. Sync `spotify_map.json`.
7. Rebuild `content_manifest.json`.
8. Deploy kun de downstream systemer, som faktisk er berørt.

## NotebookLM Generation And Download

Standard lecture dry-run:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
```

Standard download from request logs:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01L1
```

Operational notes:

- Week selectors such as `W01` expand to matching lecture folders (`W01L#`).
- `generate_week.py`, `download_week.py`, and `sync_reading_summaries.py`
  honor `PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT` and `--output-root`.
- If the configured output root is a macOS Alias file, the scripts resolve it to
  the target directory before reading or writing artifacts.
- `download_week.py` cleans up matching `*.request.json` and
  `*.request.error.json` after successful download or when the target output
  already exists. Use `--no-cleanup-requests` only for debugging.
- NotebookLM can return an empty generation response for account-gated or
  temporarily unavailable artifact types. The client classifies this as
  `EMPTY_GENERATION_RESPONSE`; retry later or use another account/profile before
  treating it as a local parser bug.

## Ved Titel- Eller Order-Ændringer

Når navigationstitler eller rækkefølge ændres, er disse artefakter normalt relevante:

1. `shows/personlighedspsykologi-en/config.github.json`
2. `shows/personlighedspsykologi-en/episode_metadata.json`
3. `podcast-tools/gdrive_podcast_feed.py`
4. `shows/personlighedspsykologi-en/feeds/rss.xml`
5. `shows/personlighedspsykologi-en/episode_inventory.json`
6. `shows/personlighedspsykologi-en/spotify_map.json`
7. `shows/personlighedspsykologi-en/content_manifest.json`
8. Spotify ingestion/cache
9. Freudd manifest reload eller deploy, hvis portal-outputtet ændres

Hvis kun labels i source docs ændres, påvirker det ikke nødvendigvis RSS. Hvis
RSS-titlen ændres, skal feed workflow køres, og Spotify kan stadig være forsinket.

## Ved Nye Eller Manglende Episoder

Tjek normalt i denne rækkefølge:

1. Findes kilden i OneDrive `Readings/` eller slides-mappen?
2. Findes korrekt mapping i det primære `reading-file-key.md`-spejl eller `slides_catalog.json`?
3. Er NotebookLM-output genereret og downloadet lokalt?
4. Er audio/quiz uploadet eller spejlet til Drive/droplet?
5. Finder `generate-feed.yml` filen i Drive?
6. Er `feeds/rss.xml` og `episode_inventory.json` opdateret?
7. Er `quiz_links.json`, `spotify_map.json` og `content_manifest.json` opdateret?
8. Er nødvendigt downstream deploy kørt, og har Spotify nået at ingest'e RSS?

## Feed Validation

Use local dry-run validation before publishing:

```bash
./.venv/bin/python podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.github.json --dry-run
```

Known non-blocking warnings can include duplicate Drive audio sources collapsed
by the feed builder or missing content that is already tracked as a backlog.
Structural errors, invariant failures, or unexpected item-count regressions are
blockers.

## Safe Change Rules

- Redigér kun canonical config (`config.github.json`). `config.local.json` er en kompatibilitetskopi og skal forblive identisk.
- Redigér kun det primære repo-spejl `shows/personlighedspsykologi-en/docs/reading-file-key.md`.
- Brug `python3 scripts/check_personlighedspsykologi_artifact_invariants.py` før commit, når du ændrer docs, config eller mirror-struktur.
- Fjern ikke kompatibilitetsfiler eller gamle path-referencer uden først at opdatere scripts, docs og hooks.
