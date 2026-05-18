# Course Understanding Review

Review date: 2026-05-05

Scope: `personlighedspsykologi` core `Course Understanding Pipeline` only.
This excludes the `Output Adaptation Layer` and `Prompt Assembly Layer`.

## Decision

Accepted for output-specific adaptation work.

The core substrate is complete, fresh, and structurally aligned:

- `source_cards`: 91/91
- `lecture_substrates`: 22/22
- `course_synthesis`: full scope, all 22 lecture keys
- `revised_lecture_substrates`: 22/22
- core stale artifacts: 0
- core validation errors: 0

Do not regenerate the core unless a source file, source/slide mapping, prompt
version, model config, or explicit quality finding requires it.

## Acceptance Checks

Commands run:

```bash
./.venv/bin/python scripts/audit_personlighedspsykologi_source_alignment.py
./.venv/bin/python scripts/audit_personlighedspsykologi_slide_mapping.py
./.venv/bin/python scripts/check_personlighedspsykologi_recursive_artifacts.py
```

Results:

- Source alignment is clean: 58 non-missing reading entries, 58 resolved,
  0 unresolved, 0 unexpected unmapped reading PDFs.
- Slide mapping is structurally clean: 34 catalog slide entries, 41 expected
  manifest slide links, 41 actual manifest slide links.
- Seven seminar slide decks are intentionally mapped across multiple lectures.
- Recursive core index validates cleanly after the `W03L2` dependency fix.

Representative artifacts reviewed:

- `W01L1`: intro/meta-theory and orientation points
- `W03L2`: personality functioning/pathology and dimensional diagnosis
- `W05L1`: psychoanalytic empirical method
- `W07L2`: humanistic psychology
- `W10L2`: sociocultural/poststructural approaches
- `W12L1`: synthesis, historicity, and exam comparison

The reviewed artifacts are coherent enough to proceed. They preserve lecture
questions, source roles, core concepts, warnings, and top-down/sideways
relations at a useful level for downstream adaptation.

## Fixes Made During Review

The review found one real freshness-check oversight:

- `W03L2` had gained the shared seminar 3 slide deck in the current lecture
  bundle, but its existing lecture substrate did not include that source card
  in `provenance.input_source_ids`.
- The old checker compared source-card signatures only against the artifact's
  own recorded source ids, so it did not detect that a current bundle source was
  missing from the artifact.

Fix:

- `lecture_substrate_is_fresh` and the recursive index now verify that a
  lecture substrate's `input_source_ids` exactly match the current existing
  sources in the lecture bundle.
- Revised lecture substrates are also checked against their source lecture
  substrate input ids.
- A regression test covers this case.

Regeneration performed:

- Rebuilt `W03L2` lecture substrate.
- Rebuilt full `course_synthesis.json`.
- Rebuilt all 22 revised lecture substrates because they depend on the course
  synthesis hash.

## Caveats

The `missing_sources` field in some lecture substrates contains semantic caveats
about external material referenced inside slides, not unresolved mapped course
files:

- `W03L2`: `Lu et al. (2023)` is referenced by the shared seminar deck; the
  paper exists elsewhere in the course as a `W03L1` reading, but is not a direct
  `W03L2` source.
- `W04L1`: `kristian-ditlev-jensen-det-bliver-sagt` refers to a case text used
  in seminar work, not a missing mapped reading/slide file.

Treat these as warnings for downstream adaptation, not as source-alignment
blockers.

Partial/stale `podcast_substrates` still exist under `source_intelligence/`, but
they are output-specific artifacts and are intentionally excluded from core
acceptance.

## Next Step

Proceed to the `Output Adaptation Layer` for the first concrete output family.
For the current study need, the best next target is printable reading scaffolds,
not NotebookLM podcast substrates.
