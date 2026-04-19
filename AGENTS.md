## Core Policies

- Always deploy after implementing changes; implementation is not complete until the required deploy step has succeeded.
- `freudd_portal` changes: deploy to `freudd-portal` as the final step.
- Podcast repo changes: commit + push, then run `gh workflow run generate-feed.yml --ref main`.
- `freudd_portal` model/schema changes: always run `makemigrations` + `migrate`.

## Freudd Remote Deploy Runbook (verified 2026-02-25)

- Deploy must run over SSH from local machine (local has no `systemctl` and no `/opt/podcasts`).
- SSH target: `digitalocean-ennui-droplet-01` (`root@64.226.79.109`, key `~/.ssh/digitalocean_ed25519`).
- Production repo: `/opt/podcasts`; service: `freudd-portal.service`.
- Precondition: changes already committed and pushed to `origin/main`.

Standard deploy (non-destructive):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git checkout main; git pull --ff-only origin main; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal; systemctl status freudd-portal --no-pager -n 25'`

Fallback if `git pull --ff-only` fails due to dirty server repository state (only with explicit approval):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git reset --hard origin/main; git clean -fd; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal'`

Post-deploy smoke check:
- `ssh digitalocean-ennui-droplet-01 'echo \"gunicorn_login $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/accounts/login)\"; echo \"gunicorn_settings $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/settings)\"; echo \"public_login $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/accounts/login)\"; echo \"public_settings $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/settings)\"'`
- Expected: `login=200`, `settings=302` (anonymous redirect to login). `/progress` is a legacy redirect to `/settings` and should return `301`.
- Detailed runbook: `freudd_portal/docs/deploy-and-smoke.md`.
