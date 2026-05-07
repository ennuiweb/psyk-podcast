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

If you are checking the service immediately after a restart, wait for local login
readiness before asserting the smoke routes:

```bash
ssh digitalocean-ennui-droplet-01 '
  set -euo pipefail
  probe_code() {
    code="$(curl -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null || true)"
    if [[ "$code" =~ ^[0-9]{3}$ ]]; then
      echo "$code"
    else
      echo "000"
    fi
  }
  for i in $(seq 1 30); do
    code="$(probe_code http://127.0.0.1:8001/accounts/login)"
    echo "readiness attempt=${i}/30 code=${code}"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  echo "gunicorn_login $(probe_code http://127.0.0.1:8001/accounts/login)"
  echo "gunicorn_settings $(probe_code http://127.0.0.1:8001/settings)"
  echo "public_login $(probe_code http://64.226.79.109/accounts/login)"
  echo "public_settings $(probe_code http://64.226.79.109/settings)"
'
```

Use the canonical routes for the final assertions:

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
- If `systemctl is-active freudd-portal` returns `active` but local login is
  still `000`, the process is not ready yet; keep waiting on
  `127.0.0.1:8001/accounts/login` instead of treating that as a route failure.
- If login is `200` but settings is not `302`, inspect Django URL routing and
  auth middleware before checking Caddy.
- If gunicorn routes work but public routes fail, inspect Caddy routing and
  service health separately.
