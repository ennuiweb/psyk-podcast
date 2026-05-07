# Podcast Flow Artifacts

Dette dokument beskriver artefakt-typer, canonical ownership og afledningskæden i
Personlighedspsykologi-flowet. Driftstrin og fejlsøgning er flyttet til
`podcast-flow-operations.md`.

## Kort Flow

1. Autoritative inputfiler ligger i OneDrive for rå læsetekster/slides og i repoet for `reading-file-key.md`, show-config og manuelle summary-filer.
2. Den canonical repo-ejede `reading-file-key.md` eksporteres til OneDrive-mirror-targets for ikke-repo workflows.
3. NotebookLM genererer lokale outputs, som efterfølgende uploades eller spejles til Drive/droplet.
4. `generate-feed.yml` bygger `rss.xml` og `episode_inventory.json` fra Drive.
5. Downstream sidecars afledes derefter: `spotify_map.json` og `content_manifest.json`.

## Canonical Ownership

Disse artefakter er de eneste, der bør redigeres direkte som canonical inputs:

| Artefakt | Rolle |
|---|---|
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings/` | Autoritative læsetekster organiseret efter `W##L#`. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Grundbog/Kapitler/` | Grundbogskapitler og kildemateriale til læsninger/lydbog. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Forelæsningsrækken/0_Pensum og forelæsningsplan/` | Forelæsningsplan og pensumgrundlag. |
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Seminarhold/Slides/` | Lokale slide-kilder. |
| `shows/personlighedspsykologi-en/docs/reading-file-key.md` | Canonical læsenøgle: lecture -> reading title -> præcist filnavn. Alle repo-, queue- og CI-flows skal læse denne path. |
| `shows/personlighedspsykologi-en/config.github.json` | Canonical show-config. |
| `shows/personlighedspsykologi-en/auto_spec.json` | Forelæsningsstruktur og auto-matching for episoder. |
| `shows/personlighedspsykologi-en/episode_metadata.json` | Manuelle episode-overrides. |
| `shows/personlighedspsykologi-en/prompt_versions.json` | Canonical prompt-label registry: human `setup_version` defaults plus current prompt-version strings for podcast, printout og source-intelligence builders. |
| `shows/personlighedspsykologi-en/artifact_ownership.json` | Maskinlaesbar ownership-kontrakt for canonical inputs, mirrors, derived artifacts og registries. |
| `shows/personlighedspsykologi-en/regeneration_registry.json` | Canonical A/B rollout-registry for public baseline (`A`) vs. regenerated candidate (`B`) per logisk episode. |
| `shows/personlighedspsykologi-en/reading_summaries.json` | Manuel cache med summary/key points for reading-, slide-, brief- og lydbogsepisoder. |
| `shows/personlighedspsykologi-en/weekly_overview_summaries.json` | Manuel cache for `ALLE KILDER`/lecture-level episoder. |
| `shows/personlighedspsykologi-en/reading_download_exclusions.json` | Udelukkelser for tekst-/downloadadgang. |
| `shows/personlighedspsykologi-en/slides_catalog.json` | Manuel mapping af slides til forelæsning, kategori og lokal sti. |
| `shows/personlighedspsykologi-en/docs/overblik.md` | Canonical important-text doc for feed/metadata. |
| `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json` | Prompt-, sprog-, længde-, brief-, slide- og quiz-konfiguration for NotebookLM-generation. |
| `freudd_portal/subjects.json` | Freudd subject registry med stier til RSS, inventory, manifest, quiz links, Spotify map og slides catalog. |

## Repo Mirrors And Exports

Repo-mirrors og eksport-targets er afledte kopier. De må ikke redigeres som source of truth.

| Artefakt | Rolle |
|---|---|
| `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/.ai/reading-file-key.md` | Eksporteret OneDrive-mirror af den canonical repo-læsenøgle til lokale ikke-repo workflows. |
| `shows/personlighedspsykologi-en/config.local.json` | Lokal kompatibilitetskopi af canonical config. Skal forblive identisk med `config.github.json`. |
| `scripts/sync_personlighedspsykologi_reading_file_key.py` | Auditerer mirror-drift og eksporterer canonical repo-læsenøgle til OneDrive/andre mirror-targets. `--mode import` findes kun til eksplicit recovery. |

Vigtig detalje: GitHub Actions læser repo-filer, ikke OneDrive-stier direkte. For
reading-key er den aktive path `shows/personlighedspsykologi-en/docs/reading-file-key.md`.

## Generated Tracked Outputs

Disse filer er afledte outputs, som må regenereres:

| Artefakt | Rolle |
|---|---|
| `shows/personlighedspsykologi-en/feeds/rss.xml` | Public RSS-feed. Spotify og podcast apps læser denne. |
| `shows/personlighedspsykologi-en/episode_inventory.json` | Strukturret inventory fra feed build. Freudd bruger denne før RSS fallback. |
| `shows/personlighedspsykologi-en/regeneration_registry.json` | Syncet statusoversigt over hvilke episoder der stadig er `A`, hvilke der har en `B`, og hvilken variant der aktuelt er aktiv. |
| `shows/personlighedspsykologi-en/quiz_links.json` | Repo mapping fra audio/episode names til quiz URLs og difficulty metadata. |
| `shows/personlighedspsykologi-en/spotify_map.json` | Repo sidecar mapping fra episode key/RSS-title til Spotify episode URL. |
| `shows/personlighedspsykologi-en/content_manifest.json` | Freudd content manifest med lectures, readings, podcast assets, quizzes, slides og Spotify links. |
| `shows/personlighedspsykologi-en/source_catalog.json` | Deterministisk file-level inventory-katalog for raw readings/slides: hashes, page counts, page-baserede token-estimater, type-signaler og prompt-sidecar-daekning. Det ekstraherer ikke source-tekst lokalt; source-forstaaelse bygges i Gemini artifacts med de faktiske filer attached. Bygges lokalt fra source tree, ikke i GitHub Actions. |

## Runtime And Ephemeral State

Disse artefakter er nødvendige i drift, men skal ikke behandles som vedligeholdte
førsteklasses kilder:

| Artefakt | Rolle |
|---|---|
| `notebooklm-podcast-auto/personlighedspsykologi/output/W##L#/` | Lokale outputmapper for MP3, quiz, infographics og request logs. Git-ignored. Kan være en macOS Alias-fil lokalt; generation/download scripts resolver aliaset til mål-mappen. |
| `*.request.json`, `*.request.error.json` | NotebookLM job-state. Ryddes som standard af `download_week.py` efter successful download eller når target-output allerede findes. |
| `shows/personlighedspsykologi-en/config.runtime.json` | CI runtime config efter secret injection. Git-ignored og slettes af workflow. |
| `$RUNNER_TEMP/...` | Midlertidige CI-filer og SSH key material. |
| `~/.notebooklm/storage_state.json` og `notebooklm-podcast-auto/profiles.json` | Lokal auth-state til NotebookLM. |

## Derivation Chain

De vigtigste afledninger går i denne retning:

1. `config.github.json` + `reading-file-key.md` + summaries + NotebookLM/local output artifacts
2. `feeds/rss.xml` + `episode_inventory.json`
3. `spotify_map.json`
4. `content_manifest.json`

`spotify_map.json` styrer ikke Spotify. Spotify læser RSS. Map-filen bruges af
repoet/Freudd som opslag fra intern episode-identitet til Spotify URL.

## Output Contracts

| Kontrakt | Betydning |
|---|---|
| RSS item title | Lyttervendt titel. Styres af feed config og `gdrive_podcast_feed.py`. |
| RSS item GUID | Stabil podcast-client identitet. Tail/Grundbog synthetic entries kan bruge suffix som `#tail-grundbog-*`. |
| RSS enclosure URL | Public R2/object-storage URL til audio. |
| `episode_inventory.json` episode key | Intern stabil episode-identitet for Freudd og Spotify map. |
| `quiz_links.json` by-name entries | Mapping fra episode/audio navn til quiz assets. |
| `content_manifest.json` reading/lecture keys | Freudd navigation, progress og subject pages. |
| `spotify_map.json` by-episode-key | Mapping til Spotify episode URL, hvis Spotify har ingested episoden. |

## Guardrails

- Redigér canonical config i `config.github.json`, ikke i `config.local.json`.
- Redigér kun den canonical repo-læsenøgle i `shows/personlighedspsykologi-en/docs/reading-file-key.md`.
- Behandl OneDrive `.ai/reading-file-key.md` som eksporteret mirror, ikke som vedligeholdt input.
- Kør `python3 scripts/check_personlighedspsykologi_artifact_invariants.py`, når du ændrer config-, mirror- eller docs-strukturen.
- Hvis en lokal output path er en macOS Alias-fil, skal den ikke committes eller
  slettes som del af repo-oprydning. Brug `PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT`
  eller `--output-root` hvis scripts skal pege på en anden fysisk mappe.
