# Traffic Analytics (Plausible)

The portal can track traffic with a global Plausible script include.

## Behavior
- The script is injected from `templates/base.html` for all pages.
- Injection is disabled by default.
- Injection is enabled only when `FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN` is non-empty.

## Runtime configuration
- `FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN`
  - Example: `freudd.dk`
  - Required to enable script injection.
- `FREUDD_ANALYTICS_PLAUSIBLE_SRC`
  - Default: `https://plausible.io/js/script.js`
  - Optional override for self-hosted Plausible.

## Production setup
Add these lines to `/etc/freudd-portal.env` on the droplet:

```bash
FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN=freudd.dk
FREUDD_ANALYTICS_PLAUSIBLE_SRC=https://plausible.io/js/script.js
```

Then restart the portal:

```bash
sudo systemctl restart freudd-portal
```

## Verify
Open page source on `https://freudd.dk/accounts/login` and confirm:
- `<script defer data-domain="freudd.dk" ...>` is present in `<head>`.
