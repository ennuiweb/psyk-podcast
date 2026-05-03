# NotebookLM Queue Operations

This runbook documents the Hetzner runtime for the queue-owned NotebookLM publication path.

Current live scope:

- `bioneuro` is the first queue-owned, R2-backed live show.
- The queue runtime is designed as a server-managed `systemd` timer that repeatedly drains one show through discovery, generation, publish, repo push, and downstream validation.

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

## Required env for `bioneuro`

Minimum required env file: `/etc/podcasts/notebooklm-queue/bioneuro.env`

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
NOTEBOOKLM_QUEUE_MAX_STAGE_RUNS=50
NOTEBOOKLM_QUEUE_REMOTE=origin
NOTEBOOKLM_QUEUE_BRANCH=main
GH_TOKEN=...
```

Notes:

- `NOTEBOOKLM_AUTH_JSON` may be replaced with the wrapper's existing auth-home contract if that is what the server already uses.
- `GH_TOKEN` is only needed if the server-side `gh` CLI is not already authenticated in the service user's home.
- The wrapper reads `NOTEBOOKLM_QUEUE_SHOW_CONFIG` only when you intentionally want a non-live config override.

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
sudo install -m 0755 /opt/podcasts/notebooklm_queue/deploy/bin/notebooklm-queue-drain-show.sh /opt/podcasts/notebooklm_queue/deploy/bin/notebooklm-queue-drain-show.sh
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.service /etc/systemd/system/podcasts-notebooklm-queue@.service
sudo install -m 0644 /opt/podcasts/notebooklm_queue/deploy/systemd/podcasts-notebooklm-queue@.timer /etc/systemd/system/podcasts-notebooklm-queue@.timer
```

3. Write the env file for the live show:

```bash
sudo install -d -m 0755 /etc/podcasts/notebooklm-queue
sudoedit /etc/podcasts/notebooklm-queue/bioneuro.env
```

4. Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now podcasts-notebooklm-queue@bioneuro.timer
sudo systemctl list-timers | rg 'podcasts-notebooklm-queue@bioneuro'
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

## Operational notes

- The timer is intentionally conservative: every 30 minutes with persistence and jitter.
- `drain-show` prioritizes later publication stages before starting new generation work, so unfinished publish backlog is cleared before the queue creates more output.
- The service is designed to be rerun safely. It performs discovery on each cycle, requeues due retry jobs, and then advances any ready stage until the show is idle or the configured stage-run cap is hit.
- Discovery skips lecture keys that already exist in the configured `episode_inventory.json` by default, so installing the service on a fresh queue store does not automatically regenerate the entire historical live catalog.
