## Deployment Policy

- Når ændringer i `freudd_portal` er færdigimplementerede, skal der altid deployes til freudd-portal-miljøet som sidste trin.

## Podcast Workflow Policy

- Når der er lavet ændringer i podcasts, skal ændringerne altid committes og pushes.
- Efter push skal der altid køres et `Generate Podcast Feed` workflow run (`.github/workflows/generate-feed.yml`).
- Standard kommando: `gh workflow run generate-feed.yml --ref main`

## Migration Policy

- Ved model-/schemaændringer i `freudd_portal` skal migrations altid oprettes og køres (`makemigrations` + `migrate`) som en fast del af implementeringen.

## Freudd Remote Deploy Runbook (operational, verified 2026-02-25)

- Lokal maskine (`/Users/oskar/repo/podcasts`) har ikke `systemctl` og ikke `/opt/podcasts`; deploy skal køres via SSH på dropletten.
- SSH target fra lokal `~/.ssh/config`: host alias `digitalocean-ennui-droplet-01`, host `64.226.79.109`, user `root`, key `~/.ssh/digitalocean_ed25519`.
- Produktionsrepo path: `/opt/podcasts`.
- Produktion service: `freudd-portal.service`.
- Sørg for at ændringer er committed og pushed til `origin/main` før remote deploy.

Standard deploy (non-destructive):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git checkout main; git pull --ff-only origin main; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal; systemctl status freudd-portal --no-pager -n 25'`

Hvis `git pull --ff-only` fejler pga dirty worktree på serveren (kun når eksplicit godkendt):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git reset --hard origin/main; git clean -fd; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal'`

Post-deploy smoke checks:
- `ssh digitalocean-ennui-droplet-01 'echo \"gunicorn_login $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/accounts/login)\"; echo \"gunicorn_progress $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/progress)\"; echo \"public_login $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/accounts/login)\"; echo \"public_progress $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/progress)\"'`
- Forventet: login `200`, progress `302` (redirect til login ved anonym adgang).

UI-specific verification (course progress-view):
- `ssh digitalocean-ennui-droplet-01 \"cd /opt/podcasts/freudd_portal && /opt/podcasts/.venv/bin/python manage.py shell <<'PY'`
- `from django.test import Client; from django.urls import reverse; from django.contrib.auth.models import User`
- `u = User.objects.filter(username='deploysmoke').first() or User.objects.create_user('deploysmoke', password='Secret123!!')`
- `c = Client(HTTP_HOST='127.0.0.1'); c.force_login(u); r = c.get(reverse('subject-detail', kwargs={'subject_slug':'personlighedspsykologi'})); b = r.content.decode('utf-8')`
- `print(r.status_code, 'lecture-details' in b, \"What's next\" in b, 'Start nu' in b)`
- `PY\"`
- Forventet: `200 True True True` når ny timeline/hero UI er deployed.

## README Command Inventory (checked 2026-02-12)

### Selected explicit runnable commands

`shows/berlingske/README.md`
- `python podcast-tools/ingest_manifest_to_drive.py --manifest /Users/oskar/repo/avisartikler-dl/downloads/manifest.tsv --downloads-dir /Users/oskar/repo/avisartikler-dl/downloads --config shows/berlingske/config.local.json`

`shows/personal/README.md`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json --dry-run`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json`

`notebooklm-podcast-auto/personlighedspsykologi/README.md`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --profile default`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W1 --content-types quiz`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html`
- `python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi --dry-run`
- `python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi`
- `cd freudd_portal && ../.venv/bin/python manage.py rebuild_content_manifest --subject personlighedspsykologi`
