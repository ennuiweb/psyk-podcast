# freudd

Django portal for authentication, quiz state, and quiz-driven gamification on top of static NotebookLM quiz exports.

## Current decisions
- Auth: Hybrid login (`brugernavn/adgangskode` + optional Google OAuth), med open signup (`/accounts/signup`) bevaret.
- Signup policy: `email` er obligatorisk; `brugernavn` er valgfrit og autogenereres unikt ved tomt felt.
- Google OAuth er feature-flagged via `FREUDD_AUTH_GOOGLE_ENABLED`; når aktiv eksponeres allauth Google-login + konto-linking flows.
- Existing password users linker Google eksplicit via `Forbind Google` (`/accounts/3rdparty/`) efter login.
- UI language: Danish only (`da`) for now; English is intentionally disabled.
- Multi-language readiness: internal IDs/status codes remain language-neutral (`quiz_id`, `completed`) so additional UI languages can be added later without data migration.
- Runtime naming: service/env/config namespace is `freudd` (`freudd-portal.service`, `/etc/freudd-portal.env`, `FREUDD_PORTAL_*`).
- Rollout compatibility: old `QUIZ_PORTAL_*` env names are still accepted temporarily.
- Locale stack is active (`LocaleMiddleware` + `LOCALE_PATHS`) but currently constrained to Danish in `LANGUAGES`.
- Quiz access: `/q/<id>.html` is public and renders a JSON-driven quiz UI (NotebookLM-like flow).
- Raw quiz HTML: served publicly via `/q/raw/<id>.html`.
- Quiz data source: portal reads `<id>.json` when available and falls back to parsing `<id>.html`.
- Anonymous quiz state is kept locally in browser storage; logged-in users persist state in DB via state API.
- Anonymous users are prompted to log in when they reach quiz summary/completion.
- Quiz flow enforces a per-question timer (`FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS`, default `30s`); timeout auto-marks the question wrong and advances.
- Quiz flow locks each question on first submission (`first answer counts`) so answers cannot be changed later in the same attempt.
- Quiz wrapper renders answer options in a deterministic per-question display order to reduce positional-answer bias; selected answers still persist as raw option indices for stable scoring/state compatibility.
- Quiz question header shows live potential score while unanswered (`Tid: <sek>s · <point>/120 point`) and updates continuously as time passes.
- Quiz question/hint/option copy normalizes inline math delimiters (`$...$`, `\\(...\\)`) for cleaner learner-facing text.
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
- Gamification core is quiz-driven and always available for authenticated users (`/settings`, `/api/gamification/me`).
- `/settings` focuses on subject access, quiz history, and public scoreboard alias/visibility settings.
- `/leaderboard/<subject_slug>` is the dedicated `scoreboard` page with subject tabs, podium cards, and Top 50 table.
- Desktop topbar centers `scoreboard` in its own highlighted pill with a trophy icon; utility actions (`Indstillinger`, `Log ud`) stay right-aligned.
- Desktop topbar enrolled-subject chips are scaled down by 25% (`height/padding/font-size`) to keep visual balance with the `freudd` wordmark.
- Quizhistorik on `/settings` is card-based and includes live search, difficulty/status filters, sort modes, and auto-updating summary metrics (`quiz count`, `rigtige svar`, `træfsikkerhed`, `perfekte quizzer`).
- Quizhistorik visibility on `/settings` is feature-flagged by `FREUDD_PROGRESS_QUIZ_HISTORY_ENABLED` (default: `1`).
- Quizhistorik chips are text-oriented (`Tekstquiz`, `Alle tekster`) and intentionally avoid audio/podcast tags like `Lyd`/`Deep dive`.
- Personal tekster/podcast tracking data remains private and is handled on subject pages (`mark/unmark`), while quiz completion stays sourced from `QuizProgress`.
- Public scoreboard is opt-in and alias-based; public view shows `alias + rank + score point + quiz count`.
- scoreboard score per quiz is based on correctness plus speed bonus (`score = correct*100 + speed_bonus`), with correctness weighted highest.
- Speed bonus reaches max when average correct-answer pace is `<= 10s` per question (capped by configured per-question timeout if lower).
- scoreboard tie-break is `correct_answers`, then earliest `reached_at`, then alias alphabetic.
- scoreboard semesters reset every half year in UTC: `H1 = [Jan 1, Jul 1)`, `H2 = [Jul 1, Jan 1 next year)`.
- Learning path on subject pages (`/subjects/<subject_slug>`) is lecture-first with nested completion-first tekststatus (`completed|no_quiz`; otherwise no explicit in-progress label) and quiz/podcast navigation.
- Subject detail UI is mobile-first and uses a left lecture rail + single active lecture card (no multi-panel accordion).
- Subject detail header shows a desktop-only trophy CTA (`scoreboard for <fag>`) linking to the current subject leaderboard; header actions are hidden on compact layouts (`<=1180px`).
- Subject detail removes KPI strip and global `Udvid alle`/`Luk alle`; lecture switching is via rail links (`?lecture=<lecture_key>`).
- Subject detail remembers each user's last opened lecture per subject and uses it as default when `?lecture=` is omitted.
- Subject detail spacing uses a local responsive scale (`section/block/tight`) to keep vertical rhythm consistent across rail, card header, and section blocks.
- Subject detail supports desktop rail collapse/expand (`Skjul tidslinje` / `Vis tidslinje`); compact layouts (`<=1180px`) keep the rail visible.
- Subject detail uses compact mobile density on small screens (`<=760px`) to reduce nested card padding/gaps for narrow devices.
- Subject detail hides the card-to-rail pointer notch on responsive layouts (`<=1180px`) to keep alignment clean with compact rail widths.
- Active lecture card renders sections in this order: `Tekster`, optional `Podcasts` (only when podcast rows exist), `Quiz for alle kilder`.
- Quiz assets are surfaced only in `Quiz for alle kilder`, podcast assets only in `Podcasts`, and tekststatus/progress only in `Tekster`.
- If no podcasts are available for the active lecture, the `Podcasts` section is hidden.
- Tekstkort and `Quizzer` sections render quiz rows in mockup format (`<sværhedsgrad> quiz` + `<rigtige>/<total> rigtige • <point>/150 point`) when question counts are available.
- Tekstkort include a `Send til ChatGPT` quick action that opens a new ChatGPT chat with a prefilled prompt that always includes the absolute PDF URL plus reading title/context.
- Lecture rail rows render extra-compact marker dots on mobile (without index numbers) plus lecture copy (week label + cleaned lecture title).
- Module headers in subject detail are rendered as a combined headline (`Uge x, forelæsning x: <titel>`), with cleaned lecture title metadata.
- Quiz labels are rendered from cleaned `episode_title` metadata (`modul` + `titel`) instead of raw file/tag strings.
- Quiz wrapper header uses a structured identity block (module label + title) and includes in-flow progress feedback per question step.
- Quiz summary includes a direct `Gå til scoreboard` CTA and shows rank movement (`fra #x til #y`) when a logged-in public participant improves placement on completion.
- Global shell and quiz wrapper enforce horizontal overflow guardrails so sticky header + fixed mobile tabbar stay anchored on narrow devices.
- Mobile `Mine fag` popup is rendered as a viewport-centered layer (via body portal) to stay centered on both axes across browsers.
- `quiz_links.json` entries must include `subject_slug` so unit progression can be computed per subject (auto-populated by quiz-link sync scripts).
- Optional extensions (`habitica`, `anki`) are disabled by default and must be enabled per account via management command.
- Extension sync is server-driven (`manage.py sync_extensions`) and runs only for enabled users with stored per-user credentials.
- Credentials are encrypted at rest with Fernet via `FREUDD_CREDENTIALS_MASTER_KEY`.
- Habitica server sync is active; Anki remains gated but server sync is deferred.
- Theme governance: `paper-studio` is the only active portal design system.
- Default design system is `paper-studio` (`FREUDD_DESIGN_SYSTEM_DEFAULT`) and is locked for end users.
- Multi-theme support is future-facing only; runtime is currently single-theme (`paper-studio`).
- Headings/titles in the portal UI are rendered in lower-case for consistent visual tone.
- Quiz wrapper reading titles preserve source capitalization (no forced lowercasing).
- `scoreboard` hero heading intentionally keeps title case to match the approved cup design.
- Shared primitives in `templates/base.html` enforce radius/spacing/depth rules portal-wide, while page templates apply local layout detail.
- Design system source of truth: `freudd_portal/docs/design-guidelines.md` (anchored to `docs/non-technical-overview.md`).
- Design guidance includes former expressive V2 rules directly in `freudd_portal/docs/design-guidelines.md`.

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
- `GET /settings` (`GET /progress` redirects permanently with query string preserved)
- `GET /leaderboard/<subject_slug>`
- `POST /leaderboard/profile`
- `GET /subjects/<subject_slug>`
- `GET /subjects/<subject_slug>/tekster/open/<reading_key>` (public tekst-fil adgang; blocked if excluded in config)
- `GET /subjects/<subject_slug>/tekster/open/<reading_key>/text` (public tekstudtræk til ChatGPT; blocked if excluded in config)
- `POST /subjects/<subject_slug>/enroll`
- `POST /subjects/<subject_slug>/unenroll`
- `POST /subjects/<subject_slug>/tracking/tekst`
- `POST /subjects/<subject_slug>/tracking/podcast`

Enrollment UX rule: `Mine fag` on `GET /settings` is read-only (open + status), while enroll/unenroll actions live in the bottom `Tilmeld og afmeld fag` module; subject detail remains read-only for enrollment state.

Leaderboard alias UX rule: if a user already has an alias, it is shown locked by default and can only be changed via explicit `Ændr alias` mode (`allow_alias_change=1` on submit). This applies to both `GET /settings` and `GET /leaderboard/<subject_slug>`.

`quiz_id` format is strict 8-char hex (`^[0-9a-f]{8}$`).

## Data model
- `QuizProgress` (existing): per-user quiz completion/score state.
- `SubjectEnrollment`: per-user subject enrollment keyed by `(user, subject_slug)`.
- `UserGamificationProfile`: per-user XP/streak/level aggregates.
- `UserUnitProgress`: per-user learning path unit status (`active`, `completed`).
- `DailyGamificationStat`: per-user daily answer/completion deltas + goal state.
- `UserLectureProgress`: per-user lecture status (`active|completed`) and quiz totals.
- `UserReadingProgress`: per-user tekststatus (`completed|no_quiz`; otherwise implicit not completed) and quiz totals.
- `UserExtensionAccess`: per-user enablement and last sync status for optional extensions.
- `UserExtensionCredential`: per-user encrypted extension credentials (`habitica` now, `anki` deferred).
- `ExtensionSyncLedger`: per-user/per-extension/per-day idempotent sync log (`ok|error|skipped`).
- `UserInterfacePreference`: reserved for future multi-theme support; current runtime remains locked to `paper-studio`.
- `UserReadingMark`: per-user private tekst tracking marks (`mark/unmark`) on subject detail.
- `UserPodcastMark`: per-user private podcast tracking marks (`mark/unmark`) on subject detail.
- `UserLeaderboardProfile`: per-user public alias and visibility settings for scoreboard leaderboard (case-insensitive unique alias).
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

Optional per-subject `paths` overrides let a subject use its own reading key, RSS, manifest, quiz links, and reading-file root instead of the global defaults:

```json
{
  "slug": "bioneuro",
  "title": "Bioneuro",
  "description": "Bio / Neuropsychology F26",
  "active": true,
  "paths": {
    "reading_master_path": "shows/bioneuro/docs/freudd-reading-file-key.md",
    "quiz_links_path": "shows/bioneuro/quiz_links.json",
    "feed_rss_path": "shows/bioneuro/feeds/rss.xml",
    "spotify_map_path": "shows/bioneuro/spotify_map.json",
    "content_manifest_path": "shows/bioneuro/content_manifest.json",
    "reading_files_root": "/var/www/readings/bioneuro",
    "reading_download_exclusions_path": "shows/bioneuro/reading_download_exclusions.json"
  }
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
- Used by `GET /subjects/<subject_slug>/tekster/open/<reading_key>` and subject detail link rendering.
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
- `FREUDD_PROGRESS_QUIZ_HISTORY_ENABLED` (default: `1`; set `0` to hide Quizhistorik on `/settings`)
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
- Caddy routes to portal: `/accounts/*`, `/api/*`, `/settings*`, `/progress*` (legacy redirect), `/q/*`, `/subjects/*`

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
