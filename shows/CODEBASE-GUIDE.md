# Shows Directory Codebase Guide
This guide is for coding LLMs working in `shows/`.
This directory is not “just content”.
It is a critical data/config boundary that many runtime subsystems depend on.

## 1. Business purpose
Each show directory is where the repo ties generated media and academic/source structure to a named publication surface.

`shows/` contains a mix of:
- canonical configuration
- docs
- assets
- generated publication artifacts
- mapping/index sidecars
- subject-specific source intelligence artifacts

It is where several other systems meet:
- queue automation
- feed generation
- portal subject views
- transcript sync
- course-specific printout and semantic pipelines

## 2. Important architectural warning
`shows/` mixes source-of-truth inputs and derived outputs in the same tree.
This is one of the most important non-idiomatic repo traits.

A coding model must constantly distinguish:
- canonical inputs you edit
- generated outputs you regenerate

If you do not make that distinction, you will “fix” the wrong file.

## 3. Top-level structure
Examples of show directories:
- `shows/personlighedspsykologi-en/`
- `shows/bioneuro/`
- `shows/social-psychology/`
- `shows/personal/`

Each show may differ in complexity, but the general pattern is:
- config
- assets
- docs
- feed outputs
- episode inventory / metadata
- optional subject/course artifacts

## 4. The most important show in this repo
For most active work, `shows/personlighedspsykologi-en/` is the densest and most important example.

Read:
- `shows/README.md`
- `shows/personlighedspsykologi-en/README.md`
- `shows/personlighedspsykologi-en/config.template.json`

## 5. What `shows/README.md` is really doing
This file is a naming and lifecycle contract, not just a folder intro.
It explains:
- how show directories are organized
- what status markers mean
- cover-art conventions
- publication expectations

Treat it as a source-of-truth doc for show-level structure.

## 6. Config contract example
Source: `shows/personlighedspsykologi-en/config.template.json`

This file is one of the clearest windows into how many subsystems depend on show config.

Snippet:
```json
{
  "publication": { "owner": "queue" },
  "subject_slug": "personlighedspsykologi",
  "output_feed": "shows/personlighedspsykologi-en/feeds/rss.xml",
  "output_inventory": "shows/personlighedspsykologi-en/episode_inventory.json",
  "quiz": {
    "links_file": "shows/personlighedspsykologi-en/quiz_links.json",
    "base_url": "https://freudd.dk/q/"
  }
}
```

This is not a small config.
It is a system contract for:
- publication ownership
- media handling
- feed generation
- quiz integration
- summary attachment
- filtering behavior

## 7. Canonical input versus derived output
Examples of likely canonical inputs:
- `config*.json`
- docs under `docs/`
- assets under `assets/`
- source catalogs and policy files

Examples of likely derived outputs:
- `feeds/rss.xml`
- `episode_inventory.json`
- `episode_metadata.json`
- `quiz_links.json`
- regenerated registries
- source-intelligence outputs

When in doubt, check the producing script before editing the file.

## 8. Show-level README files matter
Example: `shows/personlighedspsykologi-en/README.md`

These files are often operational contracts, not marketing docs.
The `personlighedspsykologi-en` README explains:
- rollout conventions
- summary workflows
- quiz-link sync
- Spotify map sync
- reading key sync
- slide mapping policy
- feed behavior

That means a show README may be more useful than scanning code first.

## 9. Why `shows/` is so central
Many runtime systems read paths from here:
- `podcast-tools` for feed/inventory generation
- `notebooklm_queue` for discovery and publication
- `freudd_portal` for subject content manifests
- `spotify_transcripts` for inventory/mapping input
- `printout_review` and source-intelligence pipelines for course-specific work

So `shows/` is effectively shared schema territory.

## 10. Common failure classes
- editing a derived file instead of the canonical source
- stale generated sidecars after config changes
- path drift between show config and consumers
- naming mismatches that break cross-linking
- assuming all show directories follow identical conventions

## 11. Important non-idiomatic traits
- data and generated artifacts coexist
- naming conventions carry semantic meaning
- one show directory may contain both publication and pedagogy artifacts
- not every file in a show directory should be hand-edited

## 12. Safe change strategy
When changing anything under `shows/`:
1. determine whether the file is canonical input or derived output
2. find the producer/consumer scripts
3. change the canonical file, not the generated artifact, unless the task is explicitly a regeneration artifact patch
4. check all consumers that read that path or convention

If you are unsure where to start, start with the show README and config template before touching code.

