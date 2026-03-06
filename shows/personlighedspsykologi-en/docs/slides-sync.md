# Personlighedspsykologi Slides Sync

Slides sync uses three OneDrive source roots and auto-derives slide underkategori from source path:

- `Forelæsningsrækken` -> `lecture` (`slides fra forelæsning`)
- `Seminarhold/Slides` -> `seminar` (`slides fra seminarhold`)
- `Øvelseshold` -> `exercise` (`slides fra øvelseshold`)

Script:

```bash
python3 scripts/sync_personlighedspsykologi_slides_to_droplet.py
```

What it does:

1. Maps slide files to `W##L#` using `reading-file-key.md` lecture numbers/dates plus filename hints.
2. Writes catalog to `shows/personlighedspsykologi-en/slides_catalog.json`.
3. Syncs mapped files to droplet path `/var/www/slides/personlighedspsykologi`.

Useful options:

```bash
# Preview mapping only
python3 scripts/sync_personlighedspsykologi_slides_to_droplet.py --dry-run --no-upload

# Continue with partial mapping
python3 scripts/sync_personlighedspsykologi_slides_to_droplet.py --allow-unresolved
```
