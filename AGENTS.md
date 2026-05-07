## Repo Identity

- Name: `podcasts`
- Type: `repo`
- Absolute path: `/Users/oskar/repo/podcasts`
- Role: `Podcast feed automation, NotebookLM subject automation, and Freudd learning portal`
- Global reference: `/Users/oskar/.agents/AGENTS.md`

## Inheritance From Global AGENTS

- Global rules in `/Users/oskar/.agents/AGENTS.md` apply by default in this repo.
- This file adds only repo-local deltas and routing for `podcasts`.

## Repo-local Rules

- Always deploy after implementing changes; implementation is not complete until the required deploy step has succeeded.
- `freudd_portal` changes: deploy to `freudd-portal` as the final step.
- Podcast repo changes:
  - queue-owned publication/runtime changes: commit + push, deploy the relevant host/runtime, and run the required queue or service smoke checks
  - `legacy_workflow` show changes, shared feed/workflow changes, or explicit cross-show validation changes: also run `gh workflow run generate-feed.yml --ref main`
- `freudd_portal` model/schema changes: always run `makemigrations` + `migrate`.

## Local Context Map

- Repo-local durable memory: `.aimemory/memory.md`
- Root technical index: `TECHNICAL.md`
- Top-level operational docs: `docs/`
- Feed automation docs: `docs/feed-automation.md`, `podcast-tools/`, `shows/README.md`, and `shows/<show>/docs/`
- NotebookLM automation docs: `docs/notebooklm-automation.md`, `notebooklm-podcast-auto/README.md`, `notebooklm-podcast-auto/personlighedspsykologi/docs/`, and `notebooklm-podcast-auto/notebooklm-py/docs/`
- Freudd portal docs: `docs/freudd-portal.md`, `freudd_portal/README.md`, and `freudd_portal/docs/`
- Freudd deploy/smoke runbook: this file and `freudd_portal/docs/deploy-and-smoke.md`
- Apps Script trigger docs: `apps-script/README.md` and `apps-script/drive_change_trigger.gs`

## Self-maintenance Rules

- When Freudd deploy/smoke behavior changes, update this file and `freudd_portal/docs/deploy-and-smoke.md` together.
- When top-level repo structure changes, update `TECHNICAL.md`, `docs/README.md`, and this context map if routing changes.
- If this repo identity, role, absolute path, or global registry mapping changes, update `~/.agents/AGENTS.md` and this file in the same task.

Freudd remote deploy runbook, verified 2026-05-07:

- Deploy must run over SSH from local machine (local has no `systemctl` and no `/opt/podcasts`).
- SSH target: `digitalocean-ennui-droplet-01` (`root@64.226.79.109`, key `~/.ssh/digitalocean_ed25519`).
- Production repo: `/opt/podcasts`; service: `freudd-portal.service`.
- Precondition: changes already committed and pushed to `origin/main`.

Standard deploy (non-destructive):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git checkout main; git pull --ff-only origin main; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal; systemctl status freudd-portal --no-pager -n 25'`

Fallback if `git pull --ff-only` fails due to dirty server repository state (only with explicit approval):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git reset --hard origin/main; git clean -fd; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal'`

Post-deploy smoke check:
- If the smoke check runs immediately after restart, first wait for `http://127.0.0.1:8001/accounts/login` to return `200`; `systemctl is-active` can report `active` before Gunicorn is actually listening.
- `ssh digitalocean-ennui-droplet-01 'echo \"gunicorn_login $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/accounts/login)\"; echo \"gunicorn_settings $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/settings)\"; echo \"public_login $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/accounts/login)\"; echo \"public_settings $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/settings)\"'`
- Expected: `login=200`, `settings=302` (anonymous redirect to login). `/progress` is a legacy redirect to `/settings` and should return `301`.
- Detailed runbook: `freudd_portal/docs/deploy-and-smoke.md`.
