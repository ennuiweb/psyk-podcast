# Quiz Portal

Django portal for authentication + per-user quiz progress on top of existing static NotebookLM quiz exports.

## Current decisions
- Auth: Django session auth with open signup (`/accounts/signup`).
- UI language: Danish only (`da`) for now; English is intentionally disabled.
- Multi-language readiness: internal IDs/status codes remain language-neutral (`quiz_id`, `in_progress`, `completed`) so additional UI languages can be added later without data migration.
- Quiz access: `/q/<id>.html` is login-protected and renders a wrapper page.
- Raw quiz HTML: served via login-protected `/q/raw/<id>.html`.
- Public static quiz files still exist at `/quizzes/personlighedspsykologi/<id>.html` (Caddy static route).
- Progress key: per `(user, quiz_id)`.
- Completion rule: `currentView == "summary"` and `answers_count == question_count`.
- Theme direction: dark mode UI (Space Grotesk + Manrope); wrapper responds `ThemeChange: "dark"`.

## Routes
- `GET/POST /accounts/signup`
- `GET/POST /accounts/login`
- `POST /accounts/logout`
- `GET /q/<quiz_id>.html`
- `GET /q/raw/<quiz_id>.html`
- `GET/POST /api/quiz-state/<quiz_id>`
- `GET/POST /api/quiz-state/<quiz_id>/raw`
- `GET /progress`

`quiz_id` format is strict 8-char hex (`^[0-9a-f]{8}$`).

## Local run
```bash
cd /Users/oskar/repo/podcasts
source .venv/bin/activate
pip install -r requirements.txt
cd quiz_portal
python3 manage.py migrate
python3 manage.py test
python3 manage.py runserver 0.0.0.0:8000
```

## Production (current droplet setup)
- Code path: `/opt/podcasts`
- Service: `quiz-portal.service`
- Gunicorn bind: `127.0.0.1:8001`
- Env file: `/etc/quiz-portal.env`
- Caddy routes to portal: `/accounts/*`, `/api/*`, `/progress*`, `/q/*`

Service commands:
```bash
sudo systemctl status quiz-portal
sudo systemctl restart quiz-portal
sudo journalctl -u quiz-portal -n 100 --no-pager
```

Deploy update:
```bash
cd /opt/podcasts
git fetch origin main
git checkout main
git pull --ff-only origin main
/opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/quiz_portal/manage.py migrate
sudo systemctl restart quiz-portal
```

## Operational notes
- Health checks: use `GET` endpoints. `HEAD` on auth endpoints may return `405` because views allow `GET/POST`.
- If `/q/*` should be public static again, switch Caddy `/q/*` back to file serving from `/var/www/quizzes/personlighedspsykologi` and reload Caddy.
