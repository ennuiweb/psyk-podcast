# NotebookLM Queue Operations

This runbook documents the Hetzner runtime for the queue-owned NotebookLM publication path.

Current live scope:

- `bioneuro` is the first queue-owned, R2-backed live show.
- `personlighedspsykologi-en` is now also queue-owned and R2-backed on the Hetzner runtime.
- The queue runtime is designed as a server-managed `systemd` timer whose service now stays alive through quota cooldowns, waits for the next retry window, and keeps draining one show until the active backlog is cleared or manual intervention is required.

Repository deploy artifacts:

- `notebooklm_queue/deploy/bin/notebooklm-queue-drain-show.sh`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.service`
- `notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.timer`

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
NOTEBOOKLM_QUEUE_METADATA_PHASE_TIMEOUT_SECONDS=1800
NOTEBOOKLM_QUEUE_GIT_TIMEOUT_SECONDS=300
NOTEBOOKLM_QUEUE_GH_TIMEOUT_SECONDS=60
NOTEBOOKLM_QUEUE_ALERT_GITHUB_TIMEOUT_SECONDS=30
NOTEBOOKLM_QUEUE_MAX_STAGE_RUNS=50
NOTEBOOKLM_QUEUE_REMOTE=origin
NOTEBOOKLM_QUEUE_BRANCH=main
GH_TOKEN=...
```

NotebookLM profile rotation on Hetzner:

```bash
NOTEBOOKLM_PROFILES_FILE=/etc/podcasts/notebooklm-queue/profiles.host.json
NOTEBOOKLM_PROFILE_PRIORITY=default,oskarvedel,tjekdepotadmin,nopeeeh,vedeloskar,stanhawkservices,baduljen,oskarhoegsgaard,djspindoctor,psykku,freudagsbaren
```

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
- `drain-show` remains the single-cycle primitive. The hosted wrapper now runs `serve-show`, which repeatedly calls `drain-show`, waits through `retry_scheduled` cooldowns, and continues automatically when NotebookLM profile quota becomes available again.
- `serve-show` now waits only when `retry_scheduled` jobs are the sole remaining active backlog. Mixed blocked+retry backlog or invalid retry timestamps stop the worker for manual intervention instead of hiding the problem behind more sleeping.
- Keep `NOTEBOOKLM_PROFILE_PRIORITY` ordered so accounts that can still create notebooks and artifacts are tried first. The generator now rotates on transient NotebookLM create/list/get RPC failures as well as explicit auth/rate-limit faults, but a good priority order still reduces churn during partial account outages.
- Queue-managed subprocesses now fail closed on timeout instead of waiting forever. Tune the timeout env vars above if a show has legitimately longer-running phases.
- The templated `systemd` service now disables `TimeoutStartSec` so long queue backlogs are not cut off mid-run while waiting through retry windows.

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

## Sync NotebookLM profiles from the workstation

When the hosted queue should rotate across the same NotebookLM accounts as the local machine, use the repo helper instead of editing committed `profiles.json` paths for the host.

From the workstation:

```bash
cd /Users/oskar/repo/podcasts
./scripts/sync_notebooklm_profiles_to_hetzner.py
```

This uploads the selected storage-state files to:

- `/etc/podcasts/notebooklm-queue/profiles/`
- `/etc/podcasts/notebooklm-queue/profiles.host.json`

Default behavior syncs every profile from `notebooklm-podcast-auto/profiles.json`. To limit the bundle:

```bash
./scripts/sync_notebooklm_profiles_to_hetzner.py --profile default --profile oskarvedel --profile tjekdepotadmin
```

Sanity-check the host bundle:

```bash
ssh hetzner-ennui-vps-01-root 'bash -lc '\''for f in /etc/podcasts/notebooklm-queue/profiles/*.json; do echo "== $(basename "$f" .json) =="; PYTHONPATH=/opt/podcasts/notebooklm-podcast-auto/notebooklm-py/src /opt/podcasts/.venv/bin/python -m notebooklm --storage "$f" status | sed -n "1,2p"; echo; done'\'''
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

2. Inspect the failing job:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py list --show-slug bioneuro
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py inspect --show-slug bioneuro --job-id <job_id>
```

3. Requeue retryable jobs whose retry window has arrived:

```bash
cd /opt/podcasts
/opt/podcasts/.venv/bin/python /opt/podcasts/scripts/notebooklm_queue.py retry-ready --show-slug bioneuro
```

4. Replay one full cycle after fixing env or auth:

```bash
sudo systemctl start podcasts-notebooklm-queue@bioneuro.service
```

5. For a specific stage recovery, use the stage entrypoints directly:

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
- The service is designed to be rerun safely. Within one service invocation it now performs repeated drain cycles, sleeps until the earliest `retry_scheduled` window when quota is the only blocker, and exits only when the active backlog is cleared or the remaining jobs need manual intervention.
- Discovery skips lecture keys that already exist in the configured `episode_inventory.json` by default, so installing the service on a fresh queue store does not automatically regenerate the entire historical live catalog.
