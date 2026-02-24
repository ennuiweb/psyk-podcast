# freudd

Django portal for authentication, quiz state, and quiz-driven gamification on top of static NotebookLM quiz exports.

## Current decisions
- Auth: Django session auth with open signup (`/accounts/signup`).
- UI language: Danish only (`da`) for now; English is intentionally disabled.
- Multi-language readiness: internal IDs/status codes remain language-neutral (`quiz_id`, `in_progress`, `completed`) so additional UI languages can be added later without data migration.
- Runtime naming: service/env/config namespace is `freudd` (`freudd-portal.service`, `/etc/freudd-portal.env`, `FREUDD_PORTAL_*`).
- Rollout compatibility: old `QUIZ_PORTAL_*` env names are still accepted temporarily.
- Locale stack is active (`LocaleMiddleware` + `LOCALE_PATHS`) but currently constrained to Danish in `LANGUAGES`.
- Quiz access: `/q/<id>.html` is public and renders a JSON-driven quiz UI (NotebookLM-like flow).
- Raw quiz HTML: served publicly via `/q/raw/<id>.html`.
- Quiz data source: portal reads `<id>.json` when available and falls back to parsing `<id>.html`.
- Anonymous quiz state is kept locally in browser storage; logged-in users persist state in DB via state API.
- Anonymous users are prompted to log in when they reach quiz summary/completion.
- Quiz files directory must be readable by `www-data`; sync uploads now avoid owner/group preservation and enforce root dir mode `755`.
- Public static quiz files still exist at `/quizzes/personlighedspsykologi/<id>.html` (Caddy static route).
- Score key: per `(user, quiz_id)`.
- Semester is stored globally per user (`UserPreference.semester`), and rendered as a fixed dropdown sourced from `subjects.json`.
- Subjects are loaded from `freudd_portal/subjects.json`; first active subject is `personlighedspsykologi`.
- Subject enrollment is per `(user, subject_slug)` in `SubjectEnrollment`.
- Subject learning path is lecture-first: each lecture node contains readings, plus lecture-level assets (for example `Alle kilder`).
- Subject content is compiled from reading master key + quiz links + local RSS into `content_manifest.json`.
- Podcast links on subject pages are Spotify-only (`spotify_map.json` matched by RSS title); unmapped podcast items are hidden.
- Completion rule: `currentView == "summary"` and `answers_count == question_count`.
- Gamification core is quiz-driven and always available for authenticated users (`/progress`, `/api/gamification/me`).
- Learning path on subject pages (`/subjects/<subject_slug>`) is lecture-first with nested reading status (`locked|active|completed|no_quiz`) and quiz/podcast navigation.
- `quiz_links.json` entries must include `subject_slug` so unit progression can be computed per subject.
- Optional extensions (`habitica`, `anki`) are disabled by default and must be enabled per account via management command.
- Extension sync is server-driven (`manage.py sync_extensions`) and runs only for enabled users with stored per-user credentials.
- Credentials are encrypted at rest with Fernet via `FREUDD_CREDENTIALS_MASTER_KEY`.
- Habitica server sync is active; Anki remains gated but server sync is deferred.
- Theme direction: dark mode UI (Space Grotesk + Manrope); wrapper responds `ThemeChange: "dark"`.

## Routes
- `GET/POST /accounts/signup`
- `GET/POST /accounts/login`
- `POST /accounts/logout`
- `GET /q/<quiz_id>.html`
- `GET /q/raw/<quiz_id>.html`
- `GET /api/quiz-content/<quiz_id>`
- `GET/POST /api/quiz-state/<quiz_id>`
- `GET/POST /api/quiz-state/<quiz_id>/raw`
- `GET /api/gamification/me`
- `GET /progress`
- `POST /preferences/semester`
- `GET /subjects/<subject_slug>`
- `POST /subjects/<subject_slug>/enroll`
- `POST /subjects/<subject_slug>/unenroll`

Enrollment UX rule: enroll/unenroll actions are only shown on the bottom `Indstillinger` section of `GET /progress`; subject detail is read-only for enrollment state.

`quiz_id` format is strict 8-char hex (`^[0-9a-f]{8}$`).

## Data model
- `QuizProgress` (existing): per-user quiz completion/score state.
- `UserPreference`: one-to-one with user (`semester`, `updated_at`).
- `SubjectEnrollment`: per-user subject enrollment keyed by `(user, subject_slug)`.
- `UserGamificationProfile`: per-user XP/streak/level aggregates.
- `UserUnitProgress`: per-user learning path unit status (`locked`, `active`, `completed`).
- `DailyGamificationStat`: per-user daily answer/completion deltas + goal state.
- `UserLectureProgress`: per-user lecture status (`locked|active|completed`) and quiz totals.
- `UserReadingProgress`: per-user reading status (`locked|active|completed|no_quiz`) and quiz totals.
- `UserExtensionAccess`: per-user enablement and last sync status for optional extensions.
- `UserExtensionCredential`: per-user encrypted extension credentials (`habitica` now, `anki` deferred).
- `ExtensionSyncLedger`: per-user/per-extension/per-day idempotent sync log (`ok|error|skipped`).
- `UserUnitProgress`: legacy/compat path model kept temporarily for API compatibility.

## Subject catalog (`subjects.json`)
```json
{
  "version": 1,
  "semester_choices": ["F26"],
  "subjects": [
    {
      "slug": "personlighedspsykologi",
      "title": "Personlighedspsykologi",
      "description": "Personlighedspsykologi F26",
      "active": true
    }
  ]
}
```

## Quiz links contract (`quiz_links.json`)
- `by_name.<episode>.subject_slug` is required for learning path calculations.
- `links[].subject_slug` is optional fallback; entry-level `subject_slug` is canonical.

## Subject content manifest contract (`content_manifest.json`)
- `subject_slug`: canonical slug for the subject manifest.
- `source_meta`: source paths + generation metadata (`reading master`, `rss`, `quiz_links`).
- `lectures[]`: lecture-first tree with `lecture_key`, `lecture_title`, `sequence_index`, `readings[]`, `lecture_assets`, `warnings[]`.
- `readings[]`: each reading has stable `reading_key`, `reading_title`, `is_missing`, and `assets` (`quizzes[]`, `podcasts[]`).
- `lecture_assets`: lecture-level assets for items like `Alle kilder`.
- `podcasts[]`: Spotify-resolved assets with `url` (Spotify episode), `platform="spotify"`, and `source_audio_url` (original RSS enclosure/link).

## Spotify map contract (`spotify_map.json`)
- Path default: `shows/personlighedspsykologi-en/spotify_map.json`
- Lookup key: exact RSS `<item><title>` after trim + whitespace normalization.
- Value: full Spotify episode URL (`https://open.spotify.com/episode/...`).

```json
{
  "version": 1,
  "subject_slug": "personlighedspsykologi",
  "by_rss_title": {
    "Uge 12, Forelæsning 1 · Podcast · Alle kilder": "https://open.spotify.com/episode/..."
  }
}
```

Operational behavior:
- Mapped RSS titles render Spotify links on `/subjects/<subject_slug>`.
- Unmapped RSS titles are omitted from UI and emitted as manifest warnings (non-fatal).
- Keep `spotify_map.json` updated when new RSS episodes are published, then rebuild manifest.

## New env configuration
- `FREUDD_SUBJECTS_JSON_PATH` (default: `freudd_portal/subjects.json`)
- `FREUDD_READING_MASTER_KEY_PATH` (default: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/.ai/reading-file-key.md`)
- `FREUDD_READING_MASTER_KEY_FALLBACK_PATH` (default: `shows/personlighedspsykologi-en/docs/reading-file-key.md`)
- `FREUDD_SUBJECT_FEED_RSS_PATH` (default: `shows/personlighedspsykologi-en/feeds/rss.xml`)
- `FREUDD_SUBJECT_SPOTIFY_MAP_PATH` (default: `shows/personlighedspsykologi-en/spotify_map.json`)
- `FREUDD_SUBJECT_CONTENT_MANIFEST_PATH` (default: `shows/personlighedspsykologi-en/content_manifest.json`)
- `FREUDD_GAMIFICATION_DAILY_GOAL` (default: `20`)
- `FREUDD_GAMIFICATION_XP_PER_ANSWER` (default: `5`)
- `FREUDD_GAMIFICATION_XP_PER_COMPLETION` (default: `50`)
- `FREUDD_GAMIFICATION_XP_PER_LEVEL` (default: `500`)
- `FREUDD_CREDENTIALS_MASTER_KEY` (required for credential encrypt/decrypt)
- `FREUDD_CREDENTIALS_KEY_VERSION` (default: `1`)
- `FREUDD_EXT_SYNC_TIMEOUT_SECONDS` (default: `20`)

## Management commands (no admin panel required)
Prerequisite: der skal eksistere en brugerkonto (via signup eller `createsuperuser`) før per-user extension-commands kan køres.

```bash
cd /Users/oskar/repo/podcasts/freudd_portal
../.venv/bin/python manage.py extension_access --user <username> --extension <habitica|anki> --enable
../.venv/bin/python manage.py extension_access --user <username> --extension <habitica|anki> --disable
../.venv/bin/python manage.py extension_credentials --user <username> --extension habitica --set --habitica-user-id <id> --habitica-api-token <token> --habitica-task-id <task_id>
../.venv/bin/python manage.py extension_credentials --user <username> --extension habitica --show-meta
../.venv/bin/python manage.py extension_credentials --user <username> --extension habitica --rotate-key-version
../.venv/bin/python manage.py extension_credentials --user <username> --extension habitica --clear
../.venv/bin/python manage.py sync_extensions --extension habitica
../.venv/bin/python manage.py sync_extensions --extension all --dry-run
../.venv/bin/python manage.py gamification_recompute --user <username>
../.venv/bin/python manage.py gamification_recompute --all
../.venv/bin/python manage.py rebuild_content_manifest --subject personlighedspsykologi
../.venv/bin/python manage.py rebuild_content_manifest --subject personlighedspsykologi --strict
```

Cron example:
```bash
0 2 * * * cd /opt/podcasts && /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica
```

Detailed operations runbook (systemd timer + cron + failure playbook):
- `freudd_portal/docs/extension-sync-operations.md`
- Ready-to-copy unit files: `freudd_portal/deploy/systemd/freudd-extension-sync.service` and `freudd_portal/deploy/systemd/freudd-extension-sync.timer`
- Ready-to-copy cron line: `freudd_portal/deploy/cron/freudd-extension-sync.cron`

## Local run
```bash
cd /Users/oskar/repo/podcasts
source .venv/bin/activate
pip install -r requirements.txt
cd freudd_portal
python3 manage.py migrate
python3 manage.py test
python3 manage.py runserver 0.0.0.0:8000
```

## Production (current droplet setup)
- Code path: `/opt/podcasts`
- Service: `freudd-portal.service`
- Gunicorn bind: `127.0.0.1:8001`
- Env file: `/etc/freudd-portal.env`
- Caddy routes to portal: `/accounts/*`, `/api/*`, `/progress*`, `/q/*`, `/subjects/*`, `/preferences/*`

Service commands:
```bash
sudo systemctl status freudd-portal
sudo systemctl restart freudd-portal
sudo journalctl -u freudd-portal -n 100 --no-pager
```

Deploy update:
```bash
cd /opt/podcasts
git fetch origin main
git checkout main
git pull --ff-only origin main
/opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate
sudo systemctl restart freudd-portal
```

## Operational notes
- Health checks: use `GET` endpoints. `HEAD` on auth endpoints may return `405` because views allow `GET/POST`.
- If upgrading from pre-rename deployments, move `/opt/podcasts/quiz_portal/db.sqlite3` to `/opt/podcasts/freudd_portal/db.sqlite3` and ensure `/opt/podcasts/freudd_portal` is writable by `www-data`.
- If deploying via `rsync`, avoid preserving foreign UID/GID ownership from another machine (`--no-owner --no-group`), otherwise Django writes can fail with `sqlite3.OperationalError: attempt to write a readonly database`. Recovery:
  ```bash
  sudo chown -R www-data:www-data /opt/podcasts/freudd_portal
  sudo find /opt/podcasts/freudd_portal -type d -exec chmod 755 {} +
  sudo find /opt/podcasts/freudd_portal -type f -exec chmod 644 {} +
  sudo chmod 664 /opt/podcasts/freudd_portal/db.sqlite3
  sudo systemctl restart freudd-portal
  ```
- If uploading quiz files manually, verify `/var/www/quizzes/personlighedspsykologi` has execute/read for `www-data` (for example mode `755` on directories, `644` on files), otherwise content endpoints can fail with permission errors.
- If `/q/*` should be public static again, switch Caddy `/q/*` back to file serving from `/var/www/quizzes/personlighedspsykologi` and reload Caddy.
