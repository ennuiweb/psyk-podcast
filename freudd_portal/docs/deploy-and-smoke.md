# Freudd Deploy And Smoke Checks

This runbook documents the current production deploy and smoke-check behavior for
the Django portal.

## Production Target

- Host: `digitalocean-ennui-droplet-01`
- Production repo: `/opt/podcasts`
- Service: `freudd-portal.service`
- App bind: `127.0.0.1:8001`
- Public HTTP path is proxied through Caddy.

## Standard Deploy

Run from the local repo after changes have been committed and pushed to
`origin/main`:

```bash
ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git checkout main; git pull --ff-only origin main; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal; systemctl status freudd-portal --no-pager -n 25'
```

## Smoke Checks

Use the canonical routes:

```bash
ssh digitalocean-ennui-droplet-01 'echo "gunicorn_login $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/accounts/login)"; echo "gunicorn_settings $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/settings)"; echo "public_login $(curl -s -o /dev/null -w "%{http_code}" http://64.226.79.109/accounts/login)"; echo "public_settings $(curl -s -o /dev/null -w "%{http_code}" http://64.226.79.109/settings)"'
```

Expected:

- `accounts/login` returns `200`.
- `settings` returns `302` for anonymous users and redirects to
  `/accounts/login?next=/settings`.
- `progress` is a legacy route and returns `301` to `/settings`; do not use it
  as the primary smoke assertion.

## Troubleshooting

- If `git pull --ff-only` fails, inspect the server worktree first. Do not run a
  destructive reset unless explicitly approved.
- If login is `200` but settings is not `302`, inspect Django URL routing and
  auth middleware before checking Caddy.
- If gunicorn routes work but public routes fail, inspect Caddy routing and
  service health separately.
