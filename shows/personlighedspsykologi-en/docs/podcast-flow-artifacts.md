# Podcast Flow Artifacts

Dette dokument oplister artefakterne i det fulde Personlighedspsykologi-podcastflow: fra OneDrive-kilder og NotebookLM-generation til RSS, Spotify, Freudd og GitHub Actions.

Formålet er at gøre det klart, hvad der er source-of-truth, hvad der er repo-cache, hvad der er genereret output, og hvad der kun er eksternt eller midlertidigt runtime-state.

## Kort Flow

1. Pensum, slides og Grundbog-materiale ligger i OneDrive-fagmappen.
2. `reading-file-key.md`, `slides_catalog.json`, configs og manuelle summaries definerer struktur, titler, mappings og beskrivelser.
3. NotebookLM genererer podcasts, korte podcasts, lydbøger, quizzer og eventuelle infographics.
4. Lokale outputs uploades eller spejles til Drive/droplet efter type.
5. `generate-feed.yml` scanner Drive, transkoder ved behov, synker quiz-links, bygger RSS og episode inventory, synker Spotify map og bygger Freudd manifest.
6. Spotify læser RSS-feedet og opretter/opdaterer egne episode objects.
7. Freudd læser `content_manifest.json`, `quiz_links.json`, `spotify_map.json` og relaterede repo-filer.

## Source Of Truth

Disse artefakter bør behandles som primære kilder. Andre filer kan være spejle eller genereret ud fra dem.

| Artefakt | Rolle |
|---|---|
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Readings/` | Autoritative læsetekster organiseret efter `W##L#`. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Grundbog/Kapitler/` | Grundbogskapitler og kildemateriale til læsninger/lydbog. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Forelæsningsrækken/0_Pensum og forelæsningsplan/` | Forelæsningsplan og pensumgrundlag. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Seminarhold/Slides/` | Lokale slide-kilder. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/.ai/reading-file-key.md` | Master for læsenøgle: lecture -> reading title -> præcist filnavn. |
| `shows/personlighedspsykologi-en/slides_catalog.json` | Manuel mapping af slides til forelæsning, kategori og lokal sti. |
| `shows/personlighedspsykologi-en/config.github.json` | CI/feed source-of-truth for GitHub Actions. |
| `shows/personlighedspsykologi-en/config.local.json` | Lokal feed-build config. |
| `shows/personlighedspsykologi-en/auto_spec.json` | Forelæsningsstruktur og auto-matching for episoder. |
| `shows/personlighedspsykologi-en/episode_metadata.json` | Manuelle episode-overrides. |
| `shows/personlighedspsykologi-en/reading_summaries.json` | Manuel cache med summary/key points for reading-, slide-, brief- og lydbogsepisoder. |
| `shows/personlighedspsykologi-en/weekly_overview_summaries.json` | Manuel cache for `ALLE KILDER`/lecture-level episoder. |
| `shows/personlighedspsykologi-en/reading_download_exclusions.json` | Udelukkelser for tekst-/downloadadgang. |
| `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` | Prompt-, sprog-, længde-, brief-, slide- og quiz-konfiguration for NotebookLM-generation. |
| `freudd_portal/subjects.json` | Freudd subject registry med stier til RSS, inventory, manifest, quiz links, Spotify map og slides catalog. |

## Repo Spejle

Disse filer er repo-kopier eller afledte routing-filer, som bruges fordi CI/Freudd ikke læser direkte fra OneDrive.

| Artefakt | Rolle |
|---|---|
| `shows/personlighedspsykologi-en/docs/reading-file-key.md` | Primært repo-spejl af OneDrive `reading-file-key.md`; bruges af feed config og manifest/Freudd. |
| `notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md` | Sekundært repo-spejl til NotebookLM-docs. |
| `shows/personlighedspsykologi-en/docs/overblik.md` | Important-text doc for feed/metadata. |
| `notebooklm-podcast-auto/personlighedspsykologi/docs/overblik.md` | NotebookLM-side spejl/notat af overblik. |
| `scripts/sync_personlighedspsykologi_reading_file_key.py` | Synker OneDrive-læsenøglen til repo-spejlene og normaliserer Grundbog-linjer. |

Vigtig detalje: GitHub Actions læser `shows/personlighedspsykologi-en/docs/reading-file-key.md`, ikke OneDrive-stien direkte.

## Templates Og Scaffolding

| Artefakt | Rolle |
|---|---|
| `shows/personlighedspsykologi-en/config.template.json` | Template for show config. |
| `shows/personlighedspsykologi-en/auto_spec.template.json` | Template for auto spec. |
| `shows/personlighedspsykologi-en/episode_metadata.template.json` | Template for episode metadata. |
| `shows/personlighedspsykologi-en/reading_summaries.template.json` | Template for reading summaries. |
| `shows/personlighedspsykologi-en/weekly_overview_summaries.template.json` | Template for weekly overview summaries. |
| `shows/personlighedspsykologi-en/docs/manual_summary_key.tsv` | Hjælpefil til manuel summary-dækning. |
| `shows/personlighedspsykologi-en/docs/summary_backlog_*.tsv` | Backlog over summary gaps, OCR/readability/unmapped issues. |
| `shows/personlighedspsykologi-en/docs/reading-name-sources-report-2026-03-05.md` | Historisk rapport om reading names og sources. |
| `shows/personlighedspsykologi-en/docs/slides-sync.md` | Manuel runbook for slide mapping og upload. |
| `freudd_portal/docs/slides-mapping-policy.md` | Global Freudd-policy for slide mapping. |

## NotebookLM Artefakter

NotebookLM-flowet er delvist lokalt, delvist eksternt og delvist git-ignored.

| Artefakt | Rolle |
|---|---|
| `notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py` | Planlægger og starter NotebookLM-generation for uge/forelæsning. |
| `notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py` | Downloader færdige NotebookLM artifacts ud fra request logs. |
| `notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py` | Scaffolder og validerer summary-caches ud fra lokale outputs og kilder. |
| `notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py` | Hjælper med canonicalisering/migration af OneDrive sources. |
| `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/` | Lokale outputmapper for MP3, quiz, infographics og request logs. Git-ignored. |
| `notebooklm-podcast-auto/personlighedspsykologi/output/<profile>/W##L#/` | Profilopdelte lokale outputs, når `--output-profile-subdir` bruges. |
| `*.mp3`, `*.wav`, `*.html`, `*.json`, `*.png` under `output/` | Lokale NotebookLM-downloads. Audio er normalt git-ignored. |
| `*.request.json` | Non-blocking job-state med `notebook_id`, `artifact_id`, `output_path`, auth/profile metadata. |
| `*.request.error.json` | Fejl-state fra NotebookLM-generation. |
| Eksterne NotebookLM notebooks | Remote notebooks med uploadede kilder. Eksisterer uden for repoet. |
| Eksterne NotebookLM artifacts | Remote artifacts, som downloades via `artifact_id`. Eksisterer uden for repoet. |
| `notebooklm-podcast-auto/profiles.json` | Lokal profile registry til NotebookLM auth. Git-ignored. |
| `~/.notebooklm/storage_state.json` | Lokal standard auth-state til NotebookLM CLI. |

## Drive Artefakter

| Artefakt | Rolle |
|---|---|
| Drive show-folder fra `drive_folder_id` | Publicerede audio- og quiz-filer, som feed workflow scanner. |
| Drive audio-filer | Enclosure-kilder for RSS. |
| Drive quiz JSON exports | Source-of-truth for quiz sync. |
| Drive-transkodede MP3-filer | Derivater af WAV/M4A/MP4, skabt af workflow før feed build. |
| Google Drive file IDs | Bruges i public download-URLs og stabile GUIDs. |
| `shows/personlighedspsykologi-en/service-account.json` | Lokal/CI service account credential. Git-ignored og runtime-only. |
| `shows/personlighedspsykologi-en/config.runtime.json` | CI runtime config efter secret injection. Git-ignored og slettes af workflow. |

## Feed Og Podcast Artefakter

| Artefakt | Rolle |
|---|---|
| `podcast-tools/gdrive_podcast_feed.py` | Hovedgenerator for RSS, episode titles, order, descriptions og inventory. |
| `podcast-tools/transcode_drive_media.py` | Scanner/transkoder Drive-medier til MP3 ved behov. |
| `shows/personlighedspsykologi-en/feeds/rss.xml` | Public RSS-feed. Spotify og podcast apps læser denne. |
| `shows/personlighedspsykologi-en/episode_inventory.json` | Strukturret inventory fra feed build. Freudd bruger denne før RSS fallback. |
| `shows/personlighedspsykologi-en/assets/cover-new.png` | Cover art i RSS og clients. |
| `shows/personlighedspsykologi-en/feeds/README.md` | Feed-folder note. |

Titelorden og navigation styres primært af `gdrive_podcast_feed.py` + `config.*.json`, ikke af Spotify. Spotify kan vise gamle titler i en periode på grund af ingestion/cache-lag.

## Quiz Artefakter

| Artefakt | Rolle |
|---|---|
| `podcast-tools/sync_drive_quiz_links.py` | Downloader quiz JSON fra Drive, uploader til droplet og opdaterer `quiz_links.json`. |
| `scripts/sync_quiz_links.py` | Lokal quiz sync helper. |
| `shows/personlighedspsykologi-en/quiz_links.json` | Repo mapping fra audio/episode names til quiz URLs og difficulty metadata. |
| `/var/www/quizzes/personlighedspsykologi/*.json` | Remote quiz JSON på droplet. |
| `/var/www/quizzes/personlighedspsykologi/*.html` | Remote quiz HTML på droplet. |
| `https://freudd.dk/q/<id>.html` | Public quiz URLs i RSS og Freudd. |
| `$RUNNER_TEMP/drive-quizzes/personlighedspsykologi/` | CI-temp download-root for quiz JSON. |

## Slides Artefakter

| Artefakt | Rolle |
|---|---|
| `shows/personlighedspsykologi-en/slides_catalog.json` | Manuel slide catalog med lecture key, category og local path. |
| Lokale slide-filer under OneDrive-fagmappen | Kilder til slide podcasts og Freudd slide-visning. |
| `scripts/sync_personlighedspsykologi_slides_to_droplet.py` | Synker mapped slides til droplet. |
| `/var/www/slides/personlighedspsykologi/` | Remote slide storage på droplet. |
| `scripts/audit_personlighedspsykologi_slide_briefs.py` | CI/lokal audit af lecture-slide brief coverage i feedet. |

Slide mapping er manuel. Automatisk mapping bør ikke bruges som source-of-truth.

## Spotify Artefakter

| Artefakt | Rolle |
|---|---|
| Spotify show `https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv` | Ekstern Spotify show-side for Personlighedspsykologi. |
| Spotify episode objects | Spotifys egne kopier/objects baseret på RSS ingestion. |
| `scripts/sync_spotify_map.py` | Matcher `episode_inventory.json` mod Spotify Web API og opdaterer map. |
| `shows/personlighedspsykologi-en/spotify_map.json` | Repo sidecar mapping fra episode key/RSS-title til Spotify episode URL. |
| `.github/workflows/sync-spotify-map.yml` | Periodisk/manuel sync af Spotify map. |

`spotify_map.json` styrer ikke Spotify. Spotify læser RSS. Map-filen bruges af repoet/Freudd som opslag fra intern episode-identitet til Spotify URL.

## Freudd Artefakter

| Artefakt | Rolle |
|---|---|
| `freudd_portal/manage.py rebuild_content_manifest --subject personlighedspsykologi` | Bygger subject manifest fra repo artefakter. |
| `shows/personlighedspsykologi-en/content_manifest.json` | Freudd content manifest med lectures, readings, podcast assets, quizzes, slides og Spotify links. |
| `freudd_portal/quizzes/content_services.py` | Loader og bygger content manifest. |
| `freudd_portal/quizzes/subject_services.py` | Resolver subject paths og settings. |
| `freudd_portal/quizzes/views.py` | Viser subject pages, readings, podcasts, quizzes og progress UI. |
| `freudd_portal/quizzes/models.py` og migrations | Persistent bruger/progress/gamification/extension state. |
| `freudd_portal/db.sqlite3` | Lokal dev DB. Git-ignored for normal drift, men findes lokalt. |
| Production DB på droplet | Faktisk Freudd bruger- og progress-state. |
| `/opt/podcasts` | Production checkout på droplet. |
| `freudd-portal.service` | Production systemd service. |
| `freudd_portal/deploy/systemd/*` og `freudd_portal/deploy/cron/*` | Deploy/extension-sync service artefakter. |

## GitHub Actions Og Automation

| Artefakt | Rolle |
|---|---|
| `.github/workflows/generate-feed.yml` | Hovedworkflow: credentials, transcode, quiz sync, feed build, slide audit, Spotify map, manifest rebuild, commit. |
| `.github/workflows/sync-spotify-map.yml` | Periodisk Spotify map + manifest rebuild. |
| `.github/workflows/deploy-freudd-portal.yml` | Deploy af Freudd ved portal/manifest/map/quiz changes. |
| `.github/workflows/monitor-production-drift.yml` | Drift-monitorering. |
| `apps-script/drive_change_trigger.gs` | Apps Script trigger for Drive changes. |
| `apps-script/appsscript.json` | Apps Script manifest. |
| `apps-script/push_drive_trigger.sh` | Lokal deploy helper til Apps Script. |
| `githooks/pre-push` | Lokal pre-push hook. |
| GitHub Actions bot commits | Genererede commits for RSS/inventory/quiz/Spotify/manifest updates. |
| Workflow logs | Driftsspor for hvad workflowet byggede og uploadede. |

## Secrets Og Runtime-State

| Artefakt | Rolle |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` / show-specifikke service account secrets | CI adgang til Drive. |
| `DIGITALOCEAN_SSH_KEY` | CI adgang til droplet for quiz sync og deploy. |
| `SPOTIFY_CLIENT_ID` og `SPOTIFY_CLIENT_SECRET` | Spotify Web API lookup for `spotify_map.json`. |
| `$RUNNER_TEMP/droplet_key` | Midlertidig SSH key file i CI. |
| `$RUNNER_TEMP/drive-quizzes/...` | Midlertidig quiz download cache i CI. |
| `shows/**/service-account.json` | Lokal/CI credential file. Git-ignored. |
| `*.runtime.json` | Runtime config. Git-ignored. |

## Output Contracts

| Kontrakt | Betydning |
|---|---|
| RSS item title | Lyttervendt titel. Styres af feed config og `gdrive_podcast_feed.py`. |
| RSS item GUID | Stabil podcast-client identitet. Tail/Grundbog synthetic entries kan bruge suffix som `#tail-grundbog-*`. |
| RSS enclosure URL | Public Drive download URL til audio. |
| `episode_inventory.json` episode key | Intern stabil episode-identitet for Freudd og Spotify map. |
| `quiz_links.json` by-name entries | Mapping fra episode/audio navn til quiz assets. |
| `content_manifest.json` reading/lecture keys | Freudd navigation, progress og subject pages. |
| `spotify_map.json` by-episode-key | Mapping til Spotify episode URL, hvis Spotify har ingested episoden. |

## Ved Titel- Eller Order-Ændringer

Når navigationstitler eller rækkefølge ændres, er disse artefakter typisk relevante:

1. `podcast-tools/gdrive_podcast_feed.py`
2. `shows/personlighedspsykologi-en/config.github.json`
3. `shows/personlighedspsykologi-en/config.local.json`
4. `shows/personlighedspsykologi-en/README.md`
5. `shows/personlighedspsykologi-en/feeds/rss.xml`
6. `shows/personlighedspsykologi-en/episode_inventory.json`
7. `shows/personlighedspsykologi-en/spotify_map.json`
8. `shows/personlighedspsykologi-en/content_manifest.json`
9. Spotify ingestion/cache
10. Freudd deploy/cache/manifest load

Hvis kun documentation eller labels i source docs ændres, påvirker det ikke nødvendigvis RSS. Hvis RSS-titlen ændres, skal feed workflow køres, og Spotify kan stadig være forsinket.

## Ved Nye Eller Manglende Episoder

Tjek normalt i denne rækkefølge:

1. Findes kilden i OneDrive `Readings/` eller slides-mappen?
2. Findes korrekt mapping i `reading-file-key.md` eller `slides_catalog.json`?
3. Er NotebookLM-output genereret og downloadet lokalt?
4. Er audio/quiz uploadet eller spejlet til Drive/droplet?
5. Finder `generate-feed.yml` filen i Drive?
6. Er `feeds/rss.xml` og `episode_inventory.json` opdateret?
7. Er `quiz_links.json`, `spotify_map.json` og `content_manifest.json` opdateret?
8. Er Freudd deployet, og har Spotify nået at ingest'e RSS?

