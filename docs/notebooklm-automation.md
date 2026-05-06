# NotebookLM Automation

## Scope

This document covers the repo-level NotebookLM automation layout and the subject wrappers that depend on it.

Naming note:

- `Freudd Content Engine` is the canonical umbrella for the course-material
  system described here. Its point is not only to generate outputs, but to
  create the best possible conditions for strong learning material before,
  during, and after generation.
- `Freudd Generation Queue` names the Hetzner-owned orchestration/runtime layer
  under `notebooklm_queue/`.
- `Course Understanding Pipeline` names the pre-output subset of the content
  engine that processes source files and builds source-, lecture-, and
  course-level understanding before prompt assembly or output-specific artifact
  generation. Its two main layers are `Source Intelligence Layer` and `Course
  Context Layer`.
- `Source Intelligence Layer` builds source-, lecture-, and course-level
  artifacts. `Course Context Layer` selects and compiles the relevant slice of
  those artifacts for a concrete lecture/source/output situation.
- `Prompt Assembly Layer` is downstream of the `Course Understanding Pipeline`;
  it turns selected context into actual prompts.

Design principle:

- The content engine should be treated as a decomposed substitute for a
  hypothetical full-course reasoning pass. That means the `Course Understanding
  Pipeline` should produce explicit bottom-up grounding, top-down framing, and
  sideways comparison artifacts before later layers assemble local prompts or
  output-specific files.

Current migration program:

- The cross-cutting implementation plan for moving NotebookLM orchestration to a Hetzner-owned queue and moving published audio off Google Drive lives in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).
- The current shipped checkpoint for that migration lives in [notebooklm-queue-current-state.md](notebooklm-queue-current-state.md).

Current operational note:

- Shared NotebookLM generation now tries to reclaim per-account notebook capacity on `CREATE_NOTEBOOK` failures by deleting the oldest safe owned notebook on that account and retrying once before profile rotation takes over; reclaim skips notebooks with pending artifacts or local request logs whose target output is still missing.

## Layout

- `notebooklm-podcast-auto/personlighedspsykologi/` - Personlighedspsykologi wrapper scripts, docs, tests, and evaluation assets.
- `notebooklm-podcast-auto/bioneuro/` - Bioneuro wrapper scripts and output flow.
- `notebooklm-podcast-auto/notebooklm-py/` - tracked submodule with the underlying client, docs, and test surface.
- `notebooklm_queue/` - queue-core package for the Hetzner migration path: durable job store, state machine, lock handling, CLI, and the shared prompt-assembly module used by generation wrappers.
- `scripts/notebooklm_queue.py` - local wrapper that re-execs into `.venv` and exposes the queue CLI.

## Primary commands

Personlighedspsykologi:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

Bioneuro:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

## Output and mirrors

Default output roots:

- `notebooklm-podcast-auto/personlighedspsykologi/output`
- `notebooklm-podcast-auto/bioneuro/output`

Mirror helper:

- `scripts/mirror_output_dirs.py`
- `scripts/notebooklm_queue.py`

Examples:

```bash
python3 scripts/mirror_output_dirs.py --subject bioneuro --dry-run
python3 scripts/mirror_output_dirs.py --subject personlighedspsykologi --dry-run
python3 scripts/mirror_output_dirs.py --subject all
```

Pre-push currently mirrors both subjects, but mirror failures are warning-only.

Queue-core note:

- the first queue-core implementation now exists, but it is intentionally only the control-plane foundation
- current scope is durable job persistence, idempotent enqueue, state transitions, show locks, indexes, adapter-based discovery, and a management CLI
- current scope now also includes real queue-owned generate/download execution for supported shows, with per-run manifests and state transitions up to `awaiting_publish`
- current scope now also includes publish-bundle preparation: `prepare-publish` validates the local week output, allows partial lecture bundles when required artifacts already exist, persists a publish manifest, and advances successful jobs to `approved_for_publish`
- current scope now also includes the first real publication stage: `upload-r2` claims jobs in `approved_for_publish`, uploads media artifacts to deterministic R2 object keys, verifies each uploaded object with `head_object`, refreshes the repo-side R2 media manifest, and advances successful jobs to `objects_uploaded`
- current scope now also includes repo metadata rebuild: `rebuild-metadata` claims jobs in `objects_uploaded`, refreshes queue-owned quiz links only when the publish bundle actually contains quiz artifacts, regenerates RSS and episode inventory from the R2 manifest, runs show-specific sidecars such as Spotify sync and Freudd content-manifest rebuild, validates the resulting repo artifacts, and advances successful jobs to `committing_repo_artifacts`
- `personlighedspsykologi-en` queue metadata rebuild now also runs strict manual-summary coverage validation before feed generation, syncs `regeneration_registry.json` as part of the publish contract, validates registry/inventory alignment after feed generation, and fails closed on slide-brief coverage gaps instead of treating them as warn-only queue output
- current scope now also includes allowlisted repo publication: `push-repo` claims jobs in `committing_repo_artifacts`, fails closed on tracked repo dirtiness outside the generated-file allowlist, keeps queue-generated artifacts on allowlisted rebase conflicts, pushes with bounded retries, and advances successful jobs to `repo_pushed`
- current scope now also includes downstream completion: `sync-downstream` claims jobs in `repo_pushed`, waits for expected push-triggered downstream workflows such as `deploy-freudd-portal.yml`, and advances successful jobs to `completed`
- current scope now also includes service-oriented draining: `drain-show` remains the single-cycle primitive, while `serve-show` is the Hetzner entrypoint that keeps invoking drain cycles, waits through `retry_scheduled` cooldowns only when they are the sole remaining active backlog, stops for manual intervention on mixed blocked+retry backlog, and continues automatically when NotebookLM profile quota becomes available again
- queue discovery now skips lecture keys that already exist in the configured `episode_inventory.json` by default, so a fresh queue store does not automatically regenerate a show's full published back-catalog; operators can still override this with `discover --include-published` when intentionally backfilling or forcing regeneration
- current scope now also includes pilot-safe config binding: `discover`, `prepare-publish`, `upload-r2`, `rebuild-metadata`, and `push-repo` accept `--show-config`, and publish manifests now pin the selected config path so later stages cannot silently drift back to the live `config.github.json`
- pilot-safe artifact routing now also covers Freudd sidecars: queue metadata rebuild and repo publication derive `quiz_links.json`, `spotify_map.json`, `content_manifest.json`, RSS, inventory, and R2 media-manifest paths from the selected show config instead of hardcoded live show paths
- storage root defaults to `/var/lib/podcasts/notebooklm-queue` and can be overridden with `NOTEBOOKLM_QUEUE_STORAGE_ROOT` or `--storage-root`
- supported discovery adapters currently cover `bioneuro` and `personlighedspsykologi-en`
- `run-dry` resolves the exact generate/download commands for the next queued lecture without touching NotebookLM or publication state
- `run-once` claims or resumes a job, executes the real generate/download wrappers, persists a run manifest under the queue storage root, and moves successful jobs either to `awaiting_publish` for newly downloaded artifacts or back to `waiting_for_artifact` when no unpublished outputs were added in that poll cycle
- hosted generation wrappers now honor `NOTEBOOKLM_PROFILES_FILE` and `NOTEBOOKLM_PROFILE_PRIORITY`, so Hetzner can rotate across a host-local bundle of NotebookLM storage states instead of depending on workstation profile paths committed in the repo
- `scripts/sync_notebooklm_profiles_to_hetzner.py` is the canonical helper for copying the local NotebookLM profile bundle to Hetzner and rebuilding `/etc/podcasts/notebooklm-queue/profiles.host.json`
- queue execution now upgrades rate-limit failures with a retry window into `retry_scheduled`, so the hosted `serve-show` worker can wait through cooldowns and continue draining partial lecture runs instead of leaving them stranded as generic retryable failures; invalid retry schedules now fail closed instead of degrading into a hot poll loop
- queue execution now emits durable alert events under the queue storage root for stale-auth failures and repeated rate-limit exhaustion, with optional webhook/email/command delivery configured by env
- shared queue indexes and alert dedupe state are now protected by global queue locks rather than only per-show locks, so concurrent show drains do not clobber `indexes/jobs.json` or `alerts/state.json`
- queue-owned stage services now auto-resume interrupted in-progress jobs for execution, bundle preparation, R2 upload, metadata rebuild, and downstream validation instead of requiring an explicit `--job-id` rescue path after a crash
- queue subprocess boundaries are now bounded by env-configurable timeouts for execution, metadata rebuild, downstream `gh` polling, repo Git operations, and the GitHub alert handler, so a wedged external command fails closed instead of holding a show lock indefinitely
- `prepare-publish` claims or resumes a job in `awaiting_publish`, scans the canonical output directory for that lecture, writes a durable publish manifest under the queue storage root, and moves successful jobs to `approved_for_publish`; after downstream validation, partial lecture publishes can return the same job to `waiting_for_artifact` for the remaining request logs
- metadata validation is now bundle-aware: audio-only publishes can complete with an unchanged or missing `quiz_links.json`, while bundles that actually include quiz artifacts still require refreshed quiz links and non-empty quiz assets in `content_manifest.json`
- `personlighedspsykologi-en` metadata is now split between podcast-critical and portal-only sidecars: audio-only bundles still rebuild and publish RSS/inventory immediately, but they skip manual-summary gates, slide-brief audits, content-manifest rebuilds, and learning-material registry sync until a bundle actually contains quiz or infographic artifacts
- `upload-r2` is intentionally R2-only for now; Drive-backed shows are blocked explicitly until their show config is migrated to `storage.provider = "r2"`
- `sync-downstream` currently validates the existing Freudd deploy workflow for `bioneuro` and `personlighedspsykologi-en` when queue-owned pushes touch `content_manifest.json`, `quiz_links.json`, or `spotify_map.json`; explicit show-ownership gating in `generate-feed.yml` still belongs to a later migration phase

Queue CLI examples:

```bash
./.venv/bin/python scripts/notebooklm_queue.py discover --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue discover --repo-root . --show-slug bioneuro --enqueue
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-dry --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-once --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue prepare-publish --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue upload-r2 --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue rebuild-metadata --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue push-repo --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue sync-downstream --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue drain-show --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue serve-show --repo-root . --show-slug bioneuro
```

Pilot-safe example:

```bash
cp shows/bioneuro/config.r2-pilot.template.json /tmp/bioneuro-r2-pilot.json
# fill in storage.public_base_url before use
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue discover --repo-root . --show-slug bioneuro --show-config /tmp/bioneuro-r2-pilot.json --enqueue
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue prepare-publish --repo-root . --show-slug bioneuro --show-config /tmp/bioneuro-r2-pilot.json
```

Important operational note:

- `notebooklm-podcast-auto/personlighedspsykologi/output` must be a real directory, not a macOS Alias file. Alias files break the shared mirror step and create noisy pre-push warnings.
- `scripts/mirror_output_dirs.py` reflects the current local Drive-mount era. It should be treated as transitional infrastructure for subjects that have not yet migrated to object storage.
- When the hosted queue needs real profile rotation, sync the workstation bundle first instead of editing committed `profiles.json` paths for the server:

```bash
./scripts/sync_notebooklm_profiles_to_hetzner.py
```

- On Hetzner, point the queue env file at that host-local bundle:

```bash
NOTEBOOKLM_PROFILES_FILE=/etc/podcasts/notebooklm-queue/profiles.host.json
NOTEBOOKLM_PROFILE_PRIORITY=default,oskarvedel,tjekdepotadmin,nopeeeh,vedeloskar,stanhawkservices,baduljen,oskarhoegsgaard,djspindoctor,psykku,freudagsbaren
```

- To be notified when NotebookLM auth goes stale, configure at least one queue alert delivery path in the same env file. Supported paths are:
  - `NOTEBOOKLM_QUEUE_ALERT_WEBHOOK_URL`
  - `NOTEBOOKLM_QUEUE_ALERT_EMAIL_TO` plus either `NOTEBOOKLM_QUEUE_RESEND_API_KEY` or SMTP env
  - `NOTEBOOKLM_QUEUE_ALERT_COMMAND`

- Alerts are always written durably under `<queue-storage-root>/alerts/` even if no external delivery is configured yet.
- Useful timeout env knobs on Hetzner:
  - `NOTEBOOKLM_QUEUE_EXECUTION_PHASE_TIMEOUT_SECONDS`
  - `NOTEBOOKLM_QUEUE_METADATA_PHASE_TIMEOUT_SECONDS`
  - `NOTEBOOKLM_QUEUE_GIT_TIMEOUT_SECONDS`
  - `NOTEBOOKLM_QUEUE_GH_TIMEOUT_SECONDS`
  - `NOTEBOOKLM_QUEUE_ALERT_GITHUB_TIMEOUT_SECONDS`

- For shadow evaluation runs under tight NotebookLM capacity, prefer one lecture and one content family at a time before scaling back up to full backlog draining. The queue now supports automatic retry scheduling for rate-limit failures, but smaller shadow batches still make debugging and quality comparison materially easier.
- The Hetzner runtime contract for the queue now lives in [notebooklm-queue-operations.md](notebooklm-queue-operations.md).

## Personlighedspsykologi source rules

The canonical reading source is the absolute OneDrive Readings root:

- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

Relevant sync utilities:

- `scripts/sync_personlighedspsykologi_reading_file_key.py`
- `scripts/sync_personlighedspsykologi_readings_to_droplet.py`
- `notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py`

## Manual summary policy

Hand-authored summary sources:

- `shows/personlighedspsykologi-en/reading_summaries.json`
- `shows/personlighedspsykologi-en/weekly_overview_summaries.json`

`sync_reading_summaries.py` validates and scaffolds, but it is not the source of final summary prose.

Queue hardening note:

- local/manual workflows can still use warn-only validation during drafting
- the queue-owned metadata path for `personlighedspsykologi-en` now uses `--fail-on-validation-issues` so missing or incomplete manual summary content blocks publication instead of producing a retryable publish failure later

Prompt assembly note:

- `generate_week.py` now compiles a course-aware lecture context from `shows/<show>/content_manifest.json` and `shows/<show>/docs/overblik.md` before building prompts.
- For `personlighedspsykologi`, that deterministic context layer now also pulls in compact semantic guidance from `course_glossary.json`, `course_theory_map.json`, `source_weighting.json`, and `course_concept_graph.json` when those artifacts exist.
- That semantic guidance is now intentionally conservative: the goal is to use
  those artifacts to improve selection while keeping the final NotebookLM
  prompt surface relatively thin.
- In `short` mode, the course-context note is now also trimmed more
  aggressively: local course arc, narrower reading map, and less duplicated
  grounding prose.
- When the course arc must be trimmed, the selected arc is anchored around the
  target lecture instead of taking the first themes from the semester.
- The final `short` audio wrapper is also thinner now: fewer focus bullets,
  fewer priority-lens bullets, and a smaller generation-rules block.
- Audio prompts with compiled course context now include a small Course
  Understanding usage contract: use the context/substrate as prioritization,
  keep it distinct from source evidence, and do not narrate internal artifacts.
- That context layer is deterministic and artifact-neutral, and it now feeds both audio prompts and NotebookLM `report` artifacts surfaced as study-guide style Markdown outputs.
- Current report usage is the first concrete non-audio consumer: abridged preparatory guides for readings, slide decks, lecture-level reading sets, and short variants.
- Prompt assembly now also injects explicit source-role guidance for normal prompt types so readings, lecture slides, and seminar slides contribute different kinds of signal instead of being blended implicitly.
- The legacy `exam_focus` config key now acts as a priority lens: it should steer importance and tensions without branding the audio prompts around the exam.
- For `personlighedspsykologi`, legacy `meta_prompting` sidecars remain
  supported but are disabled in `prompt_config.json` for Course
  Understanding-backed podcast candidate runs. Re-enable them only for an
  intentional comparison.

Prompt-system ambitions that should not drift:

- The system should synthesize each lecture block from all relevant readings plus both forelaesning and seminar slide context before producing downstream prompts.
- It should situate every lecture in the full course progression, not treat lecture prompts as isolated one-off jobs.
- It should keep source roles explicit so course framing does not overwrite source-grounded claims.
- It should not lean on explicit exam talk in the podcast prompts; importance and prioritization should come from course framing, source structure, and teaching emphasis instead.
- It should avoid explicit "be engaging" prompt text for NotebookLM audio; quality should improve through better context compilation and focus selection, not by telling NotebookLM to perform enthusiasm.
- It should remain reusable across multiple output families, with report/study-guide artifacts already live and future preparatory study artifacts building on the same compiled lecture context instead of inventing a separate prompt path.

Preprocessing maturity note:

- `personlighedspsykologi` now also has a first deterministic file-level preprocessing artifact at `shows/personlighedspsykologi-en/source_catalog.json`.
- This catalog is intentionally richer than `content_manifest.json`: it tracks source hashes, page counts, text-length estimates, language heuristics, simple source-priority signals, and prompt-sidecar presence for raw readings/slides.
- `personlighedspsykologi` now also has an explicit course-tuned preprocessing policy at `shows/personlighedspsykologi-en/source_intelligence_policy.json`, which controls how `grundbog`, lecture slides, seminar slides, and exercise slides should count inside the `Source Intelligence Layer`.
- The catalog is currently built locally from the raw source tree and committed to the repo; GitHub Actions cannot rebuild it yet because the workflow does not have the OneDrive-backed source files.
- `personlighedspsykologi` now also has a deterministic `lecture_bundles/`
  layer built from `source_catalog.json`, `content_manifest.json`, and any
  local analysis sidecars.
- `personlighedspsykologi` now also has course-level semantic artifacts:
  `course_glossary.json`, `course_theory_map.json`, and a first
  `source_intelligence_staleness.json` index built from the lecture-bundle
  layer plus a committed semantic seed file.
- `personlighedspsykologi` now also has a first deterministic
  `source_weighting.json` layer that ranks lecture sources using source family,
  bundle priority, summary/analysis coverage, term coverage, theory
  coverage, and course-specific evidence-origin roles.
- `personlighedspsykologi` now also has a first `course_concept_graph.json`
  artifact that makes sideways relations explicit through term/theory nodes,
  graph edges, seeded course distinctions, and supporting evidence-origin
  labels.
- The canonical local rebuild entrypoint for that full stack is now
  `./.venv/bin/python scripts/build_personlighedspsykologi_source_intelligence.py`,
  which runs source catalog -> lecture bundles -> semantic artifacts ->
  weighting -> concept graph -> invariants in order.
- The next preprocessing layer is now implemented as a Gemini-driven recursive
  course pass, not more prompt-only tweaks and not primarily more hand-coded
  semantic inference.
- The implemented recursive pass is: source cards for all available readings
  and slide decks -> lecture substrates -> course synthesis -> downward lecture
  revision -> compact podcast substrates.
- Python should own orchestration, caching, validation, retries, staleness, and
  artifact writing; Gemini 3.1 Pro should do most semantic interpretation.
- Source-card generation uploads the actual PDF/source file to Gemini. The
  lecture-substrate pass also uploads the lecture's raw source PDFs by default,
  so Gemini can read the material directly when synthesizing the lecture.
- The podcast prompt path should consume compact podcast substrates rather than
  exposing the whole internal artifact stack to NotebookLM.

Recursive preprocessing implementation:

- Shared Gemini preprocessing client:
  `notebooklm_queue/gemini_preprocessing.py`.
- Course-specific builders:
  `scripts/build_personlighedspsykologi_source_cards.py`,
  `scripts/build_personlighedspsykologi_lecture_substrates.py`,
  `scripts/build_personlighedspsykologi_course_synthesis.py`,
  `scripts/build_personlighedspsykologi_revised_lecture_substrates.py`,
  and `scripts/build_personlighedspsykologi_podcast_substrates.py`.
- Wrapper command:
  `scripts/build_personlighedspsykologi_recursive_source_intelligence.py`,
  with `--lectures`, `--all`, `--dry-run`, `--skip-existing`, `--force`, and
  `--fail-on-missing-key`.
- For safer live runs, use `--stop-after source-cards` for the first pass,
  inspect source cards, then resume with `--start-at lecture-substrates`.
  `--continue-on-error` collects item-level failures inside a stage and then
  blocks downstream work.
- The wrapper runs a small Gemini JSON preflight before live source uploads;
  use `--preflight-only` to test model/quota access without uploading course
  files.
- Gemini preprocessing calls use `gemini-3.1-pro-preview`, explicit
  `thinking_level=high`, default Gemini 3 temperature behavior, and
  stage-specific `response_json_schema` contracts with
  `response_mime_type="application/json"`.
- LLM-derived artifacts live under
  `shows/personlighedspsykologi-en/source_intelligence/` so they remain
  visually distinct from deterministic artifacts.
- `scripts/check_personlighedspsykologi_recursive_artifacts.py` validates
  recursive artifacts, writes `source_intelligence/index.json`, and reports
  coverage plus stale dependency hashes.
- Podcast-substrate injection is gated behind `course_context.podcast_substrate`
  so test generations can compare substrate-enabled prompts against the current
  baseline.
- Treat `W05L1`, `W06L1`, one early lecture, and one late lecture as the first
  readiness batch before running all lectures.
- Current runtime status: the code path is ready and `--preflight-only`
  succeeds for `gemini-3.1-pro-preview` using the local secret-store key. The
  first live `W05L1,W06L1` recursive batch has generated source cards,
  lecture substrates, partial course synthesis, revised lecture substrates,
  and podcast substrates. The next gate is podcast-output quality testing
  before scaling.

Printable reading scaffolds:

- `scripts/build_personlighedspsykologi_reading_scaffolds.py` is the first
  explicit Source Intelligence consumer for non-podcast study material.
- It generates three per-reading artifacts for offline use while reading:
  abridged preparatory guide, chronological unit-test questions, and
  cloze/diagram scaffolding sheet.
- It uploads the actual source PDF to Gemini 3.1 Pro and uses source cards,
  revised lecture substrates, and course synthesis only as prioritization
  context. It must not locally extract/OCR/read the source PDF for semantic
  understanding.
- Outputs are written under
  `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/scaffolding/<source_id>/`
  as JSON, Markdown, and PDFs rendered from Gemini's JSON.

## Related docs

- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
- [../notebooklm-podcast-auto/notebooklm-py/docs/README.md](../notebooklm-podcast-auto/notebooklm-py/docs/README.md)
- [README.md](README.md)
