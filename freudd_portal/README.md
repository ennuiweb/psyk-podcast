# freudd

Django portal for authentication, quiz state, and quiz-driven gamification on top of static NotebookLM quiz exports.

## Current decisions
- Auth: Hybrid login (`brugernavn/adgangskode` + optional Google OAuth), med open signup (`/accounts/signup`) bevaret.
- Signup policy: `email` er obligatorisk; `brugernavn` er valgfrit og autogenereres unikt ved tomt felt.
- Google OAuth er feature-flagged via `FREUDD_AUTH_GOOGLE_ENABLED`; når aktiv eksponeres allauth Google-login + konto-linking flows.
- Existing password users linker Google eksplicit via `Forbind Google` (`/accounts/3rdparty/`) efter login.
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
- Quiz flow enforces a per-question timer (`FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS`, default `30s`); timeout auto-marks the question wrong and advances.
- Quiz retry cooldown is per `(user, quiz_id)` with tiering: `1m x2`, `5m x3`, then `10m`; streak resets after `1h` inactivity (`FREUDD_QUIZ_RETRY_COOLDOWN_RESET_SECONDS`).
- Quiz files directory must be readable by `www-data`; sync uploads now avoid owner/group preservation and enforce root dir mode `755`.
- Public static quiz files still exist at `/quizzes/personlighedspsykologi/<id>.html` (Caddy static route).
- Score key: per `(user, quiz_id)`.
- Subjects are loaded from `freudd_portal/subjects.json`; first active subject is `personlighedspsykologi`.
- Subject enrollment is per `(user, subject_slug)` in `SubjectEnrollment`.
- Topmenu shows direct links for the authenticated user’s enrolled active subjects.
- Subject learning path is lecture-first: each lecture node contains tekster, plus lecture-level assets (for example `Alle kilder`).
- Subject content is compiled from tekst master key + quiz links + local RSS into `content_manifest.json`.
- Podcast links on subject pages are Spotify-only and episode-only. Unmapped RSS items are hidden from the podcast list until a direct Spotify episode URL exists. Direct source/Drive audio links are never exposed in UI.
- Subject detail includes inline Spotify playback via embedded episode player plus the external Spotify link for each visible podcast row.
- Completion rule: `currentView == "summary"` and `answers_count == question_count`; timed-out questions count as answered/wrong.
- Gamification core is quiz-driven and always available for authenticated users (`/progress`, `/api/gamification/me`).
- `/progress` is split in two tracks: private personal tracking and public quizliga preview.
- Private personal tracking is manual for tekster/podcasts (`mark/unmark`) and keeps quiz completion as-is from `QuizProgress`.
- Public quizliga is opt-in and alias-based; public view shows `alias + rank + score point + quiz count`.
- Quizliga score per quiz is based on correctness plus speed bonus (`score = correct*100 + speed_bonus`), with correctness weighted highest.
- Quizliga tie-break is `correct_answers`, then earliest `reached_at`, then alias alphabetic.
- Quizliga seasons reset every half year in UTC: `H1 = [Jan 1, Jul 1)`, `H2 = [Jul 1, Jan 1 next year)`.
- Learning path on subject pages (`/subjects/<subject_slug>`) is lecture-first with nested tekststatus (`active|completed|no_quiz`) and quiz/podcast navigation.
- Subject detail UI is mobile-first and uses a left lecture rail + single active lecture card (no multi-panel accordion).
- Subject detail removes KPI strip and global `Udvid alle`/`Luk alle`; lecture switching is via rail links (`?lecture=<lecture_key>`).
- Subject detail spacing uses a local responsive scale (`section/block/tight`) to keep vertical rhythm consistent across rail, card header, and section blocks.
- Active lecture card is partitioned into three fixed sibling sections in this order: `Tekster`, `Podcasts`, `Quiz for alle kilder`.
- Quiz assets are surfaced only in `Quiz for alle kilder`, podcast assets only in `Podcasts`, and tekststatus/progress only in `Tekster`.
- Section-level empty states are shown per section; one populated section does not hide the others.
- Tekstkort always render L/M/S difficulty indicators in subject detail.
- Lecture rail rows render both numbered marker and lecture copy (week label + cleaned lecture title).
- Module headers in subject detail are rendered as a combined headline (`Uge x, forelæsning x: <titel>`), with cleaned lecture title metadata.
- Quiz labels are rendered from cleaned `episode_title` metadata (`modul` + `titel`) instead of raw file/tag strings.
- Quiz wrapper header uses a structured identity block (module label + title) and includes in-flow progress feedback per question step.
- `quiz_links.json` entries must include `subject_slug` so unit progression can be computed per subject (auto-populated by quiz-link sync scripts).
- Optional extensions (`habitica`, `anki`) are disabled by default and must be enabled per account via management command.
- Extension sync is server-driven (`manage.py sync_extensions`) and runs only for enabled users with stored per-user credentials.
- Credentials are encrypted at rest with Fernet via `FREUDD_CREDENTIALS_MASTER_KEY`.
- Habitica server sync is active; Anki remains gated but server sync is deferred.
- Theme governance: `paper-studio` is the redesign baseline; `classic` and `night-lab` remain runtime compatibility/preview systems.
- Default design system is `paper-studio` (`FREUDD_DESIGN_SYSTEM_DEFAULT`), with selector placed on `mit overblik` (`GET /progress`).
- Active design system resolution order: query (`?ds=`) -> session preview -> authenticated user preference -> cookie -> configured default.
- Headings/titles in the portal UI are rendered in lower-case for consistent visual tone.
- Shared primitives in `templates/base.html` enforce radius/spacing/depth rules portal-wide, while page templates apply local layout detail.
- Design system source of truth: `freudd_portal/docs/design-guidelines.md` (anchored to `docs/non-technical-overview.md`).
- Expressive design system spec: `freudd_portal/docs/design-system-v2-expressive.md` (Paper Studio locked + lecture partitioning rules).

## Routes
- `GET/POST /accounts/signup`
- `GET/POST /accounts/login`
- `POST /accounts/logout`
- `GET/POST /accounts/google/login/` (feature-flagged)
- `GET /accounts/google/login/callback/` (feature-flagged)
- `GET/POST /accounts/3rdparty/*` (feature-flagged social account linking)
- `GET /q/<quiz_id>.html`
- `GET /q/raw/<quiz_id>.html`
- `GET /api/quiz-content/<quiz_id>`
- `GET/POST /api/quiz-state/<quiz_id>`
- `GET/POST /api/quiz-state/<quiz_id>/raw`
- `GET /api/gamification/me`
- `GET /progress`
- `GET /leaderboard/<subject_slug>`
- `POST /leaderboard/profile`
- `GET /subjects/<subject_slug>`
- `GET /subjects/<subject_slug>/readings/open/<reading_key>` (login-required tekst-fil adgang)
- `POST /subjects/<subject_slug>/enroll`
- `POST /subjects/<subject_slug>/unenroll`
- `POST /subjects/<subject_slug>/tracking/reading`
- `POST /subjects/<subject_slug>/tracking/podcast`
- `POST /preferences/design-system`

Enrollment UX rule: `Mine fag` on `GET /progress` is read-only (open + status), while enroll/unenroll actions live in the bottom `Tilmeld og afmeld fag` module; subject detail remains read-only for enrollment state.

Leaderboard alias UX rule: if a user already has an alias, it is shown locked on `GET /progress` and can only be changed via explicit `Ændr alias` mode (`allow_alias_change=1` on submit).

`quiz_id` format is strict 8-char hex (`^[0-9a-f]{8}$`).

## Data model
- `QuizProgress` (existing): per-user quiz completion/score state.
- `SubjectEnrollment`: per-user subject enrollment keyed by `(user, subject_slug)`.
- `UserGamificationProfile`: per-user XP/streak/level aggregates.
- `UserUnitProgress`: per-user learning path unit status (`active`, `completed`).
- `DailyGamificationStat`: per-user daily answer/completion deltas + goal state.
- `UserLectureProgress`: per-user lecture status (`active|completed`) and quiz totals.
- `UserReadingProgress`: per-user tekststatus (`active|completed|no_quiz`) and quiz totals.
- `UserExtensionAccess`: per-user enablement and last sync status for optional extensions.
- `UserExtensionCredential`: per-user encrypted extension credentials (`habitica` now, `anki` deferred).
- `ExtensionSyncLedger`: per-user/per-extension/per-day idempotent sync log (`ok|error|skipped`).
- `UserInterfacePreference`: per-user interface settings (`design_system`) for persistent theme selection.
- `UserReadingMark`: per-user private tekst tracking marks (`mark/unmark`) on subject detail.
- `UserPodcastMark`: per-user private podcast tracking marks (`mark/unmark`) on subject detail.
- `UserLeaderboardProfile`: per-user public alias and visibility settings for quizliga leaderboard (case-insensitive unique alias).
- `UserUnitProgress`: legacy/compat path model kept temporarily for API compatibility.

## Subject catalog (`subjects.json`)
```json
{
  "version": 1,
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
- `source_meta`: source paths + generation metadata (`tekst master`, `rss`, `quiz_links`).
- `lectures[]`: lecture-first tree with `lecture_key`, `lecture_title`, `sequence_index`, `readings[]`, `lecture_assets`, `warnings[]`.
- `readings[]`: each tekst has deterministic `reading_key`, `reading_title`, optional `source_filename`, `is_missing`, and `assets` (`quizzes[]`, `podcasts[]`). Duplicate tekst titles in the same lecture are disambiguated with `-2`, `-3`, etc.
- `lecture_assets`: lecture-level assets for items like `Alle kilder`.
- `podcasts[]`: Spotify-only episode assets with `url`, `platform`, and `source_audio_url` (original RSS enclosure/link).
- `platform`: always `spotify` (`url` must be a Spotify episode URL).

## Tekst download exclusions contract (`reading_download_exclusions.json`)
- Path default: `shows/personlighedspsykologi-en/reading_download_exclusions.json`
- Used by `GET /subjects/<subject_slug>/readings/open/<reading_key>` and subject detail link rendering.
- `excluded_reading_keys` blocks selected `reading_key` values from being opened/downloaded.
- Keys must match the manifest `readings[].reading_key` values exactly.

```json
{
  "version": 1,
  "subjects": {
    "personlighedspsykologi": {
      "excluded_reading_keys": [
        "w01l1-example-reading-abcd1234"
      ]
    }
  }
}
```

## Spotify map contract (`spotify_map.json`)
- Path default: `shows/personlighedspsykologi-en/spotify_map.json`
- Lookup key: exact RSS `<item><title>` after trim + whitespace normalization.
- Value: Spotify episode URL only (`https://open.spotify.com/episode/...`).

```json
{
  "version": 1,
  "subject_slug": "personlighedspsykologi",
  "by_rss_title": {
    "Uge 12, Forelæsning 1 · Podcast · Alle kilder": "https://open.spotify.com/episode/..."
  },
  "unresolved_rss_titles": []
}
```

Operational behavior:
- Mapped RSS titles render Spotify links on `/subjects/<subject_slug>`.
- Unmapped RSS titles are skipped from manifest podcast assets and emit warnings until a direct episode mapping exists.
- Inline embed playback is always enabled for visible podcast rows (because only episode URLs are accepted).
- `scripts/sync_spotify_map.py` auto-syncs RSS titles into `spotify_map.json` with direct Spotify episode URLs only.
- Default behavior fails when unresolved titles remain; use `--allow-unresolved` to persist resolved episode URLs and list unresolved titles in `unresolved_rss_titles`.
- Direct show lookup uses `--spotify-show-url` and Spotify client credentials (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`) to resolve episode URLs by title.
- Manifest refresh is automatic on next subject load when source files are newer; CI feed workflow also rebuilds `content_manifest.json` for `personlighedspsykologi-en`.

## New env configuration
- `FREUDD_PORTAL_SITE_ID` (default: `1`)
- `FREUDD_AUTH_GOOGLE_ENABLED` (default: `0`)
- `FREUDD_GOOGLE_CLIENT_ID` (required when `FREUDD_AUTH_GOOGLE_ENABLED=1`)
- `FREUDD_GOOGLE_CLIENT_SECRET` (required when `FREUDD_AUTH_GOOGLE_ENABLED=1`)
- `FREUDD_PORTAL_TRUST_X_FORWARDED_PROTO` (default: `0`; set `1` behind proxy TLS termination)
- `FREUDD_PORTAL_CSRF_TRUSTED_ORIGINS` (comma-separated, for example `https://freudd.dk,https://www.freudd.dk`)
- `FREUDD_PORTAL_SESSION_COOKIE_SECURE` (default: `0`; set `1` in production HTTPS)
- `FREUDD_PORTAL_CSRF_COOKIE_SECURE` (default: `0`; set `1` in production HTTPS)
- `FREUDD_SUBJECTS_JSON_PATH` (default: `freudd_portal/subjects.json`)
- `FREUDD_READING_MASTER_KEY_PATH` (default: `shows/personlighedspsykologi-en/docs/reading-file-key.md`)
- `FREUDD_READING_MASTER_KEY_FALLBACK_PATH` (default: `shows/personlighedspsykologi-en/docs/reading-file-key.md`)
- `FREUDD_SUBJECT_FEED_RSS_PATH` (default: `shows/personlighedspsykologi-en/feeds/rss.xml`)
- `FREUDD_SUBJECT_SPOTIFY_MAP_PATH` (default: `shows/personlighedspsykologi-en/spotify_map.json`)
- `FREUDD_SUBJECT_CONTENT_MANIFEST_PATH` (default: `shows/personlighedspsykologi-en/content_manifest.json`)
- `FREUDD_READING_FILES_ROOT` (default: `/var/www/readings/personlighedspsykologi`)
- `FREUDD_READING_FILES_ROOT` must be traversable/readable by the portal service user (`www-data`) or tekst open/download routes will fail at runtime.
- `FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH` (default: `shows/personlighedspsykologi-en/reading_download_exclusions.json`)
- `FREUDD_GAMIFICATION_DAILY_GOAL` (default: `20`)
- `FREUDD_GAMIFICATION_XP_PER_ANSWER` (default: `5`)
- `FREUDD_GAMIFICATION_XP_PER_COMPLETION` (default: `50`)
- `FREUDD_GAMIFICATION_XP_PER_LEVEL` (default: `500`)
- `FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS` (default: `30`)
- `FREUDD_QUIZ_RETRY_COOLDOWN_RESET_SECONDS` (default: `3600`)
- `FREUDD_CREDENTIALS_MASTER_KEY` (required for credential encrypt/decrypt)
- `FREUDD_CREDENTIALS_KEY_VERSION` (default: `1`)
- `FREUDD_EXT_SYNC_TIMEOUT_SECONDS` (default: `20`)
- `FREUDD_DESIGN_SYSTEM_DEFAULT` (default: `paper-studio`)
- `FREUDD_DESIGN_SYSTEM_COOKIE_NAME` (default: `freudd_design_system`)
- `FREUDD_SUBJECT_DETAIL_SHOW_READING_QUIZZES` (legacy toggle; tekst difficulty indicators are now always shown in subject detail)

## Google OAuth setup
Create a Google OAuth client (Web application) and whitelist callback URLs:
- `https://freudd.dk/accounts/google/login/callback/`
- `https://www.freudd.dk/accounts/google/login/callback/`
- `http://127.0.0.1:8000/accounts/google/login/callback/` (local dev)
- `http://localhost:8000/accounts/google/login/callback/` (local dev)

Then set:
- `FREUDD_AUTH_GOOGLE_ENABLED=1`
- `FREUDD_GOOGLE_CLIENT_ID=<client id>`
- `FREUDD_GOOGLE_CLIENT_SECRET=<client secret>`

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
- Caddy routes to portal: `/accounts/*`, `/api/*`, `/progress*`, `/q/*`, `/subjects/*`

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

If `/opt/podcasts` does not exist on the current host, run these deploy commands on the production droplet where `freudd-portal.service` is installed.

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
