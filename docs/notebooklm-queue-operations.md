# NotebookLM Queue Operations

This runbook documents the Hetzner runtime for the queue-owned NotebookLM publication path.

Current live scope:

- `bioneuro` is the first queue-owned, R2-backed live show.
- `personlighedspsykologi-en` is now also queue-owned and R2-backed on the Hetzner runtime.
- `personlighedspsykologi-da` now has a queue/runtime contract as a feed-first Danish mirror of the shared `personlighedspsykologi` subject surface. Its publication path is intentionally audio-only, keeps Spotify-map sync enabled for episode links, and skips Freudd portal sidecars by config.
- The queue runtime is designed as a server-managed `systemd` timer whose service drains one show through timed backlog within a bounded wall-clock budget, waits through retry windows only while budget remains, and exits cleanly so the timer can schedule the next pass.

Repository deploy artifacts:

- `notebooklm_queue/deploy/bin/notebooklm-queue-drain-show.sh`
- `notebooklm_queue/deploy/bin/notebooklm-profile-refresh.sh`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.service`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.timer`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-profile-refresh.service`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-profile-refresh.timer`

## Runtime contract

The queue service is intended to run on Hetzner as `root`.

That is deliberate:

- NotebookLM auth and browser state are easier to manage in one server-owned home directory.
- repo push, SSH sidecars, and queue state live under server-owned paths
- `bioneuro` quiz sync already depends on SSH credentials for the DigitalOcean quiz host

Default paths:

- repo root: `/opt/podcasts`
- queue storage root: `/var/lib/podcasts/notebooklm-queue`
- env file per show: `/etc/podcasts/notebooklm-queue/<show>.env`

## Required env for queue-owned shows

Minimum required env file: `/etc/podcasts/notebooklm-queue/<show>.env`

```bash
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
NOTEBOOKLM_AUTH_JSON=/root/.config/notebooklm/auth.json
NOTEBOOKLM_QUEUE_DROPLET_SSH_KEY=/root/.ssh/digitalocean_ed25519
```

Optional but recommended:

```bash
NOTEBOOKLM_QUEUE_STORAGE_ROOT=/var/lib/podcasts/notebooklm-queue
NOTEBOOKLM_QUEUE_DOWNSTREAM_TIMEOUT_SECONDS=900
NOTEBOOKLM_QUEUE_DOWNSTREAM_POLL_SECONDS=10
NOTEBOOKLM_QUEUE_EXECUTION_PHASE_TIMEOUT_SECONDS=7200
NOTEBOOKLM_QUEUE_ARTIFACT_WAIT_TIMEOUT_SECONDS=60
NOTEBOOKLM_QUEUE_ARTIFACT_POLL_INTERVAL_SECONDS=60
NOTEBOOKLM_QUEUE_TRANSIENT_RETRY_SECONDS=900
NOTEBOOKLM_QUEUE_RETRY_BACKOFF_MULTIPLIER=1.5
NOTEBOOKLM_QUEUE_RETRY_BACKOFF_MAX_SECONDS=3600
NOTEBOOKLM_QUEUE_RATE_LIMIT_RETRY_SECONDS=3600
NOTEBOOKLM_QUEUE_RATE_LIMIT_RETRY_BACKOFF_MULTIPLIER=2
NOTEBOOKLM_QUEUE_RATE_LIMIT_RETRY_MAX_SECONDS=21600
NOTEBOOKLM_PROFILE_RATE_LIMIT_COOLDOWN_SECONDS=3600
NOTEBOOKLM_QUEUE_METADATA_PHASE_TIMEOUT_SECONDS=1800
NOTEBOOKLM_QUEUE_GIT_TIMEOUT_SECONDS=300
NOTEBOOKLM_QUEUE_GH_TIMEOUT_SECONDS=60
NOTEBOOKLM_QUEUE_ALERT_GITHUB_TIMEOUT_SECONDS=30
NOTEBOOKLM_QUEUE_MAX_STAGE_RUNS=1
NOTEBOOKLM_QUEUE_PROFILE_LOCK_WAIT_SECONDS=60
NOTEBOOKLM_QUEUE_REMOTE=origin
NOTEBOOKLM_QUEUE_BRANCH=main
GH_TOKEN=...
```

Temporary prioritization mode for Personlighedspsykologi short podcasts:

```bash
NOTEBOOKLM_QUEUE_ONLY_SHORT_OUTPUTS=1
```

When enabled, the hosted queue passes `--only-short` to the Personlighedspsykologi
generator. The claimed lecture only requests `[Short]`/brief artifacts and
skips weekly overview plus full per-source outputs. Use this for short-first
catch-up campaigns; remove it before returning the same queue to normal long
podcast generation.

NotebookLM profile rotation on Hetzner:

```bash
NOTEBOOKLM_PROFILES_FILE=/etc/podcasts/notebooklm-queue/profiles.host.json
NOTEBOOKLM_PROFILE_PRIORITY=freudagsbaren,oskarvedel,tjekdepotadmin,nopeeeh,vedeloskar,stanhawkservices,oskarhoegsgaard
```

`personlighedspsykologi-en` and `personlighedspsykologi-da` forward these
environment values into their queue-owned generate commands as
`--profiles-file` and `--profile-priority`. `bioneuro` does not forward them
because its current generator wrapper does not accept those flags.
Do not reintroduce `baduljen` or `djspindoctor` to the committed profile map,
hosted profile bundle, or priority lists; those accounts are intentionally
retired from queue rotation.

Queue alerting for stale auth and repeated rate-limit exhaustion:

```bash
NOTEBOOKLM_QUEUE_ALERT_DEDUP_SECONDS=21600
NOTEBOOKLM_QUEUE_RATE_LIMIT_ALERT_ATTEMPTS=3
```

Choose at least one delivery path:

```bash
# JSON POST
NOTEBOOKLM_QUEUE_ALERT_WEBHOOK_URL=https://example.com/notebooklm-alerts

# Email via Resend
NOTEBOOKLM_QUEUE_ALERT_EMAIL_TO=oskar@ennui.dk
NOTEBOOKLM_QUEUE_ALERT_EMAIL_FROM=noreply@freudd.dk
NOTEBOOKLM_QUEUE_RESEND_API_KEY=...

# Or a custom shell hook that receives alert JSON on stdin
NOTEBOOKLM_QUEUE_ALERT_COMMAND=/opt/podcasts/scripts/handle_queue_alert.sh

# Or use the built-in GitHub issue handler on hosts where `gh` is authenticated
NOTEBOOKLM_QUEUE_ALERT_COMMAND=/opt/podcasts/scripts/handle_queue_alert_github.py
NOTEBOOKLM_QUEUE_ALERT_GITHUB_REPO=ennuiweb/psyk-podcast
```

Notes:

- `NOTEBOOKLM_AUTH_JSON` may be replaced with the wrapper's existing auth-home contract if that is what the server already uses.
- `GH_TOKEN` is only needed if the server-side `gh` CLI is not already authenticated in the service user's home.
- The wrapper reads `NOTEBOOKLM_QUEUE_SHOW_CONFIG` only when you intentionally want a non-live config override.
- Alert events are always persisted under `<storage-root>/alerts/` even when no external delivery path is configured.
- `drain-show` remains the single-cycle primitive. The hosted wrapper now runs `serve-show`, which repeatedly calls `drain-show`, waits through `retry_scheduled` cooldowns and `waiting_for_artifact` poll windows, and exits cleanly with `profile_capacity_wait` when the active NotebookLM profile pool has no immediately usable account.
- `refresh-profiles` is the queue-owned profile freshness primitive. It runs the `notebooklm-py` token/cookie keepalive path, then probes the same storage file with a real `notebooklm list --json` call before clearing `last_error=auth`. A keepalive success without a successful probe is still treated as auth-stale.
- `reclaim-notebooks` is the bounded profile capacity cleanup primitive. It lists owned NotebookLM notebooks for selected profiles and deletes only the oldest safe candidates until the configured free-slot target is met; it skips shared notebooks, notebooks with pending artifacts, and notebooks referenced by local request logs whose target output is still missing. Manual CLI runs default to dry-run and require `--apply` to delete. `refresh-profiles` can optionally trigger the same reclaim after auth or cooldown recovery through `--reclaim-on-recovery`; the older `--reclaim-on-auth-recovery` flag remains available for auth-only recovery.
- The hosted profile-refresh timer shares the same global `notebooklm-capacity` lock as generation, so a refresh run and a queue generation run cannot mutate the same NotebookLM storage/profile-state files concurrently.
- The hosted profile-refresh timer runs shortly after boot and then every 12 minutes with a small randomized delay. It skips unrecovered auth-stale profiles until their storage file changes or an operator passes `--force`, so stale accounts do not get hammered while valid accounts stay warm.
- `NOTEBOOKLM_PROFILE_MAX_VALIDATION_AGE_SECONDS` makes the queue stop before generation when the latest successful profile probe is too old. This is an automatic wait state, not a manual auth failure; the refresh timer is expected to validate the profile and reopen capacity.
- `profile_capacity_wait` exits success only for timed/automatic waits such as rate-limit cooldowns or another show holding the global NotebookLM lock. If every active profile needs operator action, such as stale auth or missing storage files, `serve-show` exits nonzero so systemd and monitoring can surface the intervention.
- The `serve-show` wall-clock budget is controlled by `NOTEBOOKLM_QUEUE_DOWNSTREAM_TIMEOUT_SECONDS` in the hosted wrapper path today. That value now limits the overall service loop as well as downstream polling, so a timer-triggered worker cannot stay in `activating` forever while only sleeping between retries.
- NotebookLM execution is guarded by a global queue lock named `__global__-notebooklm-capacity`, so two show workers cannot concurrently claim generation work against the same profile pool.
- Hosted queue workers should use `NOTEBOOKLM_QUEUE_MAX_STAGE_RUNS=1` unless there is a deliberate maintenance reason to drain multiple stages in one service invocation. This keeps timer-triggered work bounded and lets profile capacity recover between passes.
- Full-profile cooldown exhaustion now also maps to `retry_scheduled`, so a lecture that temporarily runs out of usable NotebookLM profiles is retried automatically instead of sticking in `failed_retryable`.
- Queue-owned Personlighedspsykologi generation uses strict profile exclusion: once every configured rotation profile is cooling inside a lecture run, `generate_week.py` stops before the next NotebookLM call and `generate_podcast.py` treats an all-profile `--exclude-profiles` set as a hard automation error.
- Queue discovery now dead-letters stale non-terminal queue records for the same
  show, subject, lecture, and content types when the current config hash
  supersedes them. This also covers stale records whose lectures are already
  published and therefore skipped by normal discovery.
- Current operator policy: do not bulk-reschedule `dead_letter` records without
  inspecting the reason. Superseded config cohorts should stay terminal; only
  genuine failed jobs should be considered for targeted requeue. Keep the
  dead-letter feature enabled because it prevents stale queue records from
  running after config changes.
- NotebookLM auth expiry now maps to `blocked_auth_stale`, which is treated as an operator-owned blocker instead of a timed retry. The queue keeps draining unrelated `retry_scheduled` and `waiting_for_artifact` queue records for the same show and only exits with `blocked_backlog_remaining` when blocked auth is all that remains.
- Generic `failed_retryable` backlog still exits nonzero for manual intervention. Only explicit operator-owned blocked states such as `blocked_auth_stale` produce the clean degraded `blocked_backlog_remaining` stop reason.
- NotebookLM source-ingestion stalls now also map to `retry_scheduled`: if generation ends with `Sources not ready after waiting`, the queue schedules a retry instead of leaving the lecture in a blocking failed state.
- `drain-show` now performs a repair sweep for stale `failed_retryable` queue records whose stored error text matches a retryable pattern. That lets older backlog created before classifier changes recover into timed retries automatically instead of forcing manual intervention.
- Queue-level retry windows now back off progressively for repeated NotebookLM cooldown, rate-limit, and transient RPC failures instead of reusing a flat retry delay forever. Transient NotebookLM failures still default to `15m` base, `1.5x` multiplier, capped at `60m`; rate-limit and profile-cooldown failures now default to `60m` base, `2x` multiplier, capped at `6h`. The per-profile NotebookLM cooldown written by the generator also defaults to `60m`, so other queued jobs respect the shared account pool instead of retrying after the old five-minute local cooldown.
- Queue-owned generate phases no longer run NotebookLM with `--wait`. They stop after durable `.request.json` logs exist, then bounded download polls move queue records between `downloading`, `waiting_for_artifact`, and `awaiting_publish`.
- For `personlighedspsykologi-en` and `personlighedspsykologi-da`, download polls prefer the profile recorded in each `.request.json` through the current hosted profiles file before falling back to the global profile priority list. NotebookLM `Permission denied`, `status code 7`, `account-routing mismatch`, `authuser`, sign-in redirects, and HTML-media responses are treated as profile/auth-routing failures so the downloader tries the next candidate instead of stalling on the wrong account.
- Queue-owned metadata rebuild is now bundle-aware: audio-only publish bundles do not block on quiz sync or quiz-asset validation, but quiz bundles still fail closed if refreshed `quiz_links.json` or `content_manifest` quiz assets are missing.
- For `personlighedspsykologi-en`, audio-only bundles still bypass the manual-summary and slide-brief portal gates, but they now rebuild `content_manifest.json` too, so queue-owned audio publishes can flow into Freudd without waiting for a later quiz or infographic bundle.
- Queue-owned lecture records can now publish incrementally: if one episode finishes downloading while sibling request logs for the same lecture are still pending, the queue uploads and publishes the finished episode(s), then returns the same lecture record to `waiting_for_artifact` for the remaining outputs.
- Incremental publish cycles skip unchanged R2 objects, so a whole-show regeneration does not re-upload already published episodes on every later poll.
- `serve-show` now keeps waiting and draining whenever timed backlog (`retry_scheduled` or `waiting_for_artifact`) still exists, even if blocked queue records are also present.
- If the next retry/poll window would exceed the remaining service budget, `serve-show` exits with `service_timeout_reached` and a zero process exit code so the systemd timer can resume the show on the next tick.
- Invalid retry timestamps still fail closed for manual intervention, but mixed blocked+timed backlog no longer stalls the whole show.
- Keep `NOTEBOOKLM_PROFILE_PRIORITY` ordered so accounts that can still create notebooks and artifacts are tried first. The generator now rotates on transient NotebookLM create/list/get RPC failures as well as explicit auth/rate-limit faults, but a good priority order still reduces churn during partial account outages.
- Queue-managed subprocesses now fail closed on timeout instead of waiting forever. Tune the timeout env vars above if a show has legitimately longer-running phases.
- The templated `systemd` service now disables `TimeoutStartSec` so long queue backlogs are not cut off mid-run. The queue loop itself is responsible for exiting on its own wall-clock budget instead of relying on systemd to kill it.

## Queue state notes

- When Oskar asks for the state of the queue, include both: episode-level jobs
  created/generated and uploaded/published in the past 48 hours, grouped by
  show, and the current NotebookLM profile report with
  usable/cooldown/auth-stale counts.
- `queued` means a job is eligible to be claimed as soon as profile capacity is available.
- `retry_scheduled` means the job is waiting for a timestamped retry window, usually profile cooldown, rate limit, or transient NotebookLM failure recovery.
- `waiting_for_artifact` means NotebookLM generation has been requested and the queue is polling for the generated file.
- `blocked_auth_stale` means an operator must reauth or replace the profile before that job can continue.
- `dead_letter` means the queue has intentionally stopped retrying the job. In this repo it currently includes both genuinely failed terminal jobs and superseded config/hash jobs; check the `note`, `error`, and config hash before deciding whether anything should be requeued.
- Superseded `dead_letter` records should not remain in the live `jobs/` store
  once inspected; archive them outside `jobs/` and reconcile indexes so queue
  totals reflect actionable backlog.

## Install on Hetzner

1. Ensure the repo is current on the server:

```bash
cd /opt/podcasts
git fetch origin main
git checkout main
git pull --ff-only origin main
```

2. Install the wrapper and units:

```bash
sudo install -d -m 0755 /etc/podcasts/notebooklm-queue
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.service /etc/systemd/system/podcasts-notebooklm-queue@.service
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.timer /etc/systemd/system/podcasts-notebooklm-queue@.timer
sudo install -m 0755 /opt/podcasts/notebooklm_queue/deploy/bin/notebooklm-profile-refresh.sh /opt/podcasts/notebooklm_queue/deploy/bin/notebooklm-profile-refresh.sh
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-profile-refresh.service /etc/systemd/system/podcasts-notebooklm-profile-refresh.service
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-profile-refresh.timer /etc/systemd/system/podcasts-notebooklm-profile-refresh.timer
```

3. Write the env file for the live show:

```bash
sudo install -d -m 0755 /etc/podcasts/notebooklm-queue
sudoedit /etc/podcasts/notebooklm-queue/<show>.env
```

4. Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now podcasts-notebooklm-queue@<show>.timer
sudo systemctl list-timers | rg 'podcasts-notebooklm-queue@<show>'
```

Current deployed examples:

- `/etc/podcasts/notebooklm-queue/bioneuro.env`
- `/etc/podcasts/notebooklm-queue/personlighedspsykologi-en.env`
- `/etc/podcasts/notebooklm-queue/personlighedspsykologi-da.env`
- `/etc/podcasts/notebooklm-queue/profile-refresh.env`

Profile refresh env:

```bash
NOTEBOOKLM_PROFILES_FILE=/etc/podcasts/notebooklm-queue/profiles.host.json
NOTEBOOKLM_PROFILE_STATE_FILE=/root/.notebooklm/profile_state.json
NOTEBOOKLM_PROFILE_PRIORITY=default,nopeeeh,oskarvedel,freudagsbaren,oskarhoegsgaard,stanhawkservices,tjekdepotadmin,vedeloskar,g2a_geminiaiadvanced_kimngan12795
NOTEBOOKLM_PROFILE_REFRESH_MIN_AGE_SECONDS=600
NOTEBOOKLM_PROFILE_MAX_VALIDATION_AGE_SECONDS=1800
NOTEBOOKLM_PROFILE_REFRESH_PROBE=1
NOTEBOOKLM_PROFILE_REFRESH_PROBE_TIMEOUT_SECONDS=60
NOTEBOOKLM_PROFILE_REFRESH_NOTEBOOKLM_BIN=/opt/podcasts/.venv/bin/notebooklm
```

Enable the profile-refresh timer after a manual `refresh-profiles` run has produced the expected state transitions:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now podcasts-notebooklm-profile-refresh.timer
sudo systemctl list-timers | rg 'podcasts-notebooklm-profile-refresh'
```

## Sync NotebookLM profiles from the workstation

When the hosted queue should rotate across the same NotebookLM accounts as the local machine, use the repo helper instead of editing committed `profiles.json` paths for the host.

From the workstation:

```bash
cd /Users/oskar/repo/podcasts
./scripts/sync_notebooklm_profiles_to_hetzner.py
```

By default this is bundle-only: it rewrites `/etc/podcasts/notebooklm-queue/profiles.host.json` from the committed local profile list without overwriting remote storage-state files. Use that default after changing which profiles are active or retired.

Storage-state uploads are explicit:

```bash
./scripts/sync_notebooklm_profiles_to_hetzner.py --profile default --profile oskarvedel
./scripts/sync_notebooklm_profiles_to_hetzner.py --upload-all
```

Selected uploads copy storage-state files to:

- `/etc/podcasts/notebooklm-queue/profiles/`
- `/etc/podcasts/notebooklm-queue/profiles.host.json`

The install step preserves timestamped backups under `/etc/podcasts/notebooklm-queue/profiles/.backups/` before overwriting storage files. It also refuses to overwrite a newer remote storage file unless `--force-overwrite-newer` is passed; use that only when the selected local browser login is known to be fresher than the hosted copy.

After uploading a reauth, validate with the refresh/probe primitive instead of `notebooklm status`:

```bash
ssh hetzner-ennui-vps-01-root 'bash -lc '\''cd /opt/podcasts; set -a; . /etc/podcasts/notebooklm-queue/profile-refresh.env; set +a; /opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py refresh-profiles --profile default --force --actor operator-reauth && /opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py profile-status'\'''
```

## Manual commands

Run one immediate cycle:

```bash
sudo systemctl start podcasts-notebooklm-queue@bioneuro.service
```

Run the wrapper directly:

```bash
cd /opt/podcasts
sudo /opt/podcasts/notebooklm_queue/deploy/bin/notebooklm-queue-drain-show.sh bioneuro
```

Inspect queue state:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py report --show-slug bioneuro
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py list --show-slug bioneuro
```

Refresh and inspect NotebookLM profile capacity:

```bash
cd /opt/podcasts
set -a
. /etc/podcasts/notebooklm-queue/profile-refresh.env
set +a
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py refresh-profiles
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py profile-status
```

Manual targeted repair for a single profile:

```bash
cd /opt/podcasts
set -a
. /etc/podcasts/notebooklm-queue/profile-refresh.env
set +a
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py refresh-profiles --profile default --force --actor operator
```

Use `--no-probe` only for debugging the token/cookie keepalive path. Normal operations should keep probing enabled so a profile is not marked usable until NotebookLM accepts it.

Dry-run bounded notebook reclaim for a single profile before deleting anything:

```bash
cd /opt/podcasts
set -a
. /etc/podcasts/notebooklm-queue/profile-refresh.env
set +a
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py reclaim-notebooks --profile default --target-free-slots 25 --max-deletions 25 --actor operator
```

Apply the same bounded reclaim after reviewing the dry-run report under `/var/lib/podcasts/notebooklm-queue/notebook-reclaim/`:

```bash
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py reclaim-notebooks --profile default --target-free-slots 25 --max-deletions 25 --apply --actor operator
```

To reclaim automatically when `refresh-profiles` repairs auth-stale storage or validates a profile whose cooldown has expired, set `NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_ON_RECOVERY=1`; keep `NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_APPLY=0` for dry-run reports, or set it to `1` only after dry-runs have shown safe candidates. `NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_ON_AUTH_RECOVERY=1` remains accepted for old deployments, but new configuration should use the broader recovery flag.

Refresh existing scheduled retry windows after changing retry policy. This also moves already re-queued retry backlog back into `retry_scheduled` when the previous failure history is classifiable:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py refresh-retry-schedules --show-slug bioneuro
```

Inspect profile capacity without claiming queue jobs:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py profile-status
```

For shadow evaluation under rate pressure, prefer a single lecture batch before widening the scope. That keeps failures attributable and lets the queue's retry scheduling work on a small surface area first.

## Logs and health checks

Check timer and service:

```bash
sudo systemctl status podcasts-notebooklm-queue@bioneuro.timer
sudo systemctl status podcasts-notebooklm-queue@bioneuro.service
```

Read recent logs:

```bash
sudo journalctl -u podcasts-notebooklm-queue@bioneuro.service -n 200 --no-pager
```

Sanity-check the queue lock path and storage root:

```bash
sudo ls -la /var/lib/podcasts/notebooklm-queue
```

Inspect persisted alerts:

```bash
sudo find /var/lib/podcasts/notebooklm-queue/alerts -maxdepth 2 -type f | sort | tail
```

## Failure playbook

1. Inspect the latest queue summary:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py report --show-slug bioneuro
```

2. Inspect the failing queue record. The CLI flag is still named `--job-id`:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py list --show-slug bioneuro
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py inspect --show-slug bioneuro --job-id <job_id>
```

3. Requeue retryable queue records whose retry window has arrived:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py retry-ready --show-slug bioneuro
```

4. If retry policy changed while jobs were already `retry_scheduled` or already re-queued from an older retry window, extend active retry windows without claiming work:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py refresh-retry-schedules --show-slug bioneuro
```

5. Replay one full cycle after fixing env or auth:

```bash
sudo systemctl start podcasts-notebooklm-queue@bioneuro.service
```

6. For a specific stage recovery, use the stage entrypoints directly:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py run-once --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py prepare-publish --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py upload-r2 --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py rebuild-metadata --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py push-repo --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py sync-downstream --repo-root /opt/podcasts --show-slug bioneuro --job-id <job_id>
```

If the worker process died mid-stage, retrying `drain-show` is usually enough now because resumable in-progress states are claimed automatically.

## Operational notes

- The timer is intentionally conservative: every 30 minutes with persistence and jitter.
- `drain-show` prioritizes later publication stages before starting new generation work, so unfinished publish backlog is cleared before the queue creates more output.
- The service is designed to be rerun safely. Within one service invocation it now performs repeated drain cycles, sleeps until the earliest `retry_scheduled` window when quota is the only blocker, and exits only when the non-terminal backlog is cleared or the remaining queue records need manual intervention.
- Discovery skips lecture keys that already exist in the configured `episode_inventory.json` by default, so installing the service on a fresh queue store does not automatically regenerate the entire historical live catalog.
