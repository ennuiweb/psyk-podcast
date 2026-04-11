# Regeneration Plan (Socialpsykologi Deep Dives)

## Goal

Regenerate the `shows/social-psychology` feed in a controlled way, replacing the current mixed historical output with a canonical, auditable set of episodes and then republishing `shows/social-psychology/feeds/rss.xml`.

Assumption for this plan:
- Scope is `shows/social-psychology` only.
- `shows/social-psychology-tts` is out of scope unless explicitly added later.

## Current repo state

- The live show is still the older Drive-first feed flow:
  - Feed config: `shows/social-psychology/config.local.json`
  - Feed output: `shows/social-psychology/feeds/rss.xml`
  - Drive root folder: `1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI`
  - Auto dating: `shows/social-psychology/auto_spec.json`
  - Reading map / important-reading source: `shows/social-psychology/docs/reading-file-key.md`
- Current published feed contains 45 items dated from September 2, 2024 through December 9, 2024.
- `episode_metadata.json` has only one manual override under `by_id`, so almost all dating/titling is inferred from Drive state plus `auto_spec.json`.
- The repo does not currently contain a dedicated `notebooklm-podcast-auto/social-psychology/` generation pipeline similar to `personlighedspsykologi` or `bioneuro`.

## What is wrong with the current state

- The feed is not obviously a canonical "one episode per planned source" build.
- `docs/reading-file-key.md` lists 55 canonical readings across W1-W14, but the live feed only has 45 items total, including weekly recap items and brief variants.
- The current feed also contains ad hoc or suspicious entries that should be reviewed before a full rerun:
  - duplicate `Alle kilder (undtagen slides)` in W7
  - `Obaidi - Living under threat - 2018 (Theis)`
  - `Slides`
  - `Slides fra lektion 2`
  - `Van Lange - Self-interest and beyond (f u c k e d udgave)`
- Brief coverage is inconsistent: only 3 `[Kort podcast]` items exist.

## Recommended target state

Recommended default: treat this as a canonical reset, not a bit-for-bit rebuild of the existing 45 published items.

Canonical output policy:
- One main episode per reading in `docs/reading-file-key.md`.
- One `Alle kilder` episode per course week where the source set is complete enough to justify it.
- Brief variants only when they are intentionally part of the format, not because they happen to exist historically.
- No slide-only episodes unless explicitly whitelisted.
- No one-off duplicate speaker/version uploads unless explicitly whitelisted.

Recommended preservation policy:
- Keep the existing 2024 release calendar pattern from `auto_spec.json`.
- Preserve week/topic mapping unless there is a deliberate curriculum correction.
- Preserve public-facing show identity (`title`, artwork, feed URL) unless this becomes a rebrand task.

## Scope decision still needed

Before execution, confirm which of these two interpretations should govern "regenerate all":

1. Historical parity
- Recreate only the currently published episode set, anomalies included unless explicitly removed.
- Lower content-planning effort.
- Bakes in today’s inconsistencies.

2. Canonical rebuild
- Rebuild from the reading key and teaching plan as source of truth.
- Produces a cleaner feed and a reproducible target.
- Requires explicit decisions on brief coverage and weekly recap coverage.

Recommended choice: canonical rebuild.

## Proposed execution phases

### Phase 1: Freeze and inventory

- Snapshot the current feed item list and keep it as a rollback/comparison artifact.
- Inventory the Drive folder tree under `1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI`.
- Export a week-by-week table with:
  - Drive filename
  - Drive file ID
  - folder path
  - inferred week from `auto_spec.json`
  - whether the item maps to a reading-key entry
  - whether it is a brief / weekly recap / duplicate / slide item / anomaly
- Decide which existing Drive files are canonical, replaceable, or should be removed from the feed.

### Phase 2: Lock the content spec

- Create a canonical inventory for W1-W14 from `docs/reading-file-key.md`.
- Decide whether `Alle kilder` should exist for all weeks or only selected weeks.
- Decide whether textbook readings should also get `[Kort podcast]` variants.
- Write down filename rules before any generation starts:
  - stable week prefix
  - stable reading title block
  - stable brief marker
  - no ad hoc suffixes like `(Theis)` unless they represent intentional alternates
- Expand `episode_metadata.json` if manual pinning is needed for titles, descriptions, or explicit exceptions.

### Phase 3: Choose the regeneration path

There are two viable paths:

1. One-off manual rerun
- Regenerate audio in NotebookLM manually.
- Download artifacts manually.
- Upload canonical MP3s back into the Drive week folders.
- Faster to start, weak on repeatability.

2. Reproducible repo workflow
- Scaffold a `notebooklm-podcast-auto/social-psychology/` workflow modeled on the newer subject pipelines.
- Add week-level generation/download scripts and prompt config to the repo.
- Use repo-tracked config as the source of truth for future reruns.

Recommended choice: reproducible repo workflow if the target is a full canonical rebuild, because 55+ source readings plus weekly recap logic is too large for a clean manual process.

### Phase 4: Regenerate audio

- Generate the canonical episode set week by week.
- Keep outputs grouped by course week.
- Review failed or weak generations before upload instead of pushing everything forward automatically.
- Do not upload alternates or retries into the same Drive week folder without a naming rule, or the feed will pick them up as separate episodes.

### Phase 5: Clean and repopulate Drive

- Remove or archive non-canonical files from the Drive source folders before final feed generation.
- Upload the canonical audio set only.
- Ensure folder names still match `auto_spec.json` aliases (`w1` .. `w14` / `week 1` .. `week 14`).
- If any week structure changes, update `auto_spec.json` before the final feed build.

### Phase 6: Local validation

- Install local dependencies first:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Run a dry check:

```bash
python3 podcast-tools/gdrive_podcast_feed.py --config shows/social-psychology/config.local.json --dry-run
```

- Run the actual local feed build:

```bash
python3 podcast-tools/gdrive_podcast_feed.py --config shows/social-psychology/config.local.json
```

- Validate:
  - item count matches the canonical inventory
  - no duplicate weekly recap items
  - no accidental slide episodes
  - no malformed titles
  - publish dates align with `auto_spec.json`
  - important readings are highlighted only where intended by `docs/reading-file-key.md`

### Phase 7: Publish

- Commit the repo changes.
- Push to `main`.
- Trigger feed regeneration in GitHub Actions:

```bash
gh workflow run generate-feed.yml --ref main
```

- Confirm the resulting `shows/social-psychology/feeds/rss.xml` is the expected final state.

## Concrete checks to perform during planning

- Compare current feed coverage vs reading-key coverage week by week.
- Decide whether W14 should remain recap-only or also include per-reading episodes.
- Decide whether W10 should stay as a small week or absorb `Ahmadu 2017` as part of W9/W10 policy.
- Decide whether old slide-derived items should be retired entirely.
- Decide whether brief episodes are a format feature or just a legacy artifact from early weeks.

## Known risks

- Because the show is Drive-first, duplicate uploads or old leftovers in Drive will silently become feed items.
- The current repo has almost no metadata pinning for this show, so filename instability will leak directly into RSS titles.
- Without a dedicated local generation pipeline, a full rerun can become partially manual and difficult to reproduce.
- If the canonical inventory is not frozen before generation starts, the rerun will drift week by week.

## Definition of done

- A written canonical inventory exists for all W1-W14 episodes in scope.
- The Drive source folders contain only the intended canonical audio files.
- `shows/social-psychology/feeds/rss.xml` matches the canonical inventory after a local build.
- The repo changes are committed and pushed.
- `generate-feed.yml` has been triggered against `main`.
