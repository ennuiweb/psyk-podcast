# Bioneuro (NotebookLM Generation)

Dette fag er en let wrapper omkring den eksisterende ugegenerator, med `bioneuro`-defaults.

## Kilde-rod (default)
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Readings`

## Filer
- `prompt_config.json` - prompt/language/artifact defaults.
- `scripts/generate_week.py` - wrapper til den fælles ugegenerator med `bioneuro`-stier som default.
- `scripts/download_week.py` - wrapper til download af artifacts fra request-logs med `bioneuro` output-root som default.

## Brug

Dry-run for én uge:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

Generér audio:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --content-types audio
```

Download artifacts for flere uger:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/download_week.py --weeks 1,2,3,4,5,6,8,9,10,11,12
```

Bemærk:
- Du kan stadig overskrive defaults med egne argumenter (`--sources-root`, `--prompt-config`, `--output-root`).
- Wrappers bruger de fælles scripts i `personlighedspsykologi/scripts`, så de arver samme forbedringer:
  - `Alle kilder` bliver automatisk sprunget over for uge/lektions-mapper med kun én kildefil.
  - `generate_week.py` skip-logic håndterer konflikt mellem `.request.json` og `.request.error.json` ved at stole på nyeste log.
  - `download_week.py` rydder request-logs op som default (`.request.json`, `.request.error.json`, `.request.done.json`), inkl. orphan `.request.done.json` i valgte uge-mapper.
  - Brug `--no-cleanup-requests` (eller `--no-archive-requests`) for at beholde logs.

## Troubleshooting (2026-03-02)

Hvis en PDF fejler med `Source <id> failed to process`, men andre PDF'er virker:

1. Omskriv PDF'en før upload (Ghostscript):

```bash
gs -q -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook \
  -sOutputFile="/tmp/<name>_normalized.pdf" "<original>.pdf"
```

2. Ved flakey ingestion: forsøg upload igen (samme fil kan fejle og lykkes på efterfølgende forsøg).
3. Hvis `generate_podcast.py` køres med `--wait`, skal script-versionen inkludere fixet hvor wait/download kører i en ny client-kontekst.
