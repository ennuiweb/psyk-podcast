# Extension sync operations (server-driven)

This runbook documents two production-safe schedulers for `manage.py sync_extensions`:
- `systemd timer` (recommended)
- `cron` (fallback)

All commands assume:
- repo path: `/opt/podcasts`
- venv: `/opt/podcasts/.venv`
- Django project: `/opt/podcasts/freudd_portal`
- service user: `www-data`

Repository deploy artifacts:
- `freudd_portal/deploy/systemd/freudd-extension-sync.service`
- `freudd_portal/deploy/systemd/freudd-extension-sync.timer`
- `freudd_portal/deploy/cron/freudd-extension-sync.cron`

## Prerequisites

1. Ensure env file includes:
   - `FREUDD_CREDENTIALS_MASTER_KEY`
   - `FREUDD_CREDENTIALS_KEY_VERSION`
   - `FREUDD_EXT_SYNC_TIMEOUT_SECONDS`
2. Ensure at least one user has:
   - `extension_access` enabled for `habitica`
   - `extension_credentials` stored for `habitica`
3. Sanity check manually:

```bash
cd /opt/podcasts
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica --dry-run
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica
```

---

## Option A: systemd timer (recommended)

### 1) Create service unit

`/etc/systemd/system/freudd-extension-sync.service`

```ini
[Unit]
Description=Run freudd extension sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=www-data
Group=www-data
WorkingDirectory=/opt/podcasts
EnvironmentFile=/etc/freudd-portal.env
ExecStart=/opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica
```

### 2) Create timer unit

`/etc/systemd/system/freudd-extension-sync.timer`

```ini
[Unit]
Description=Daily freudd extension sync

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=300
Unit=freudd-extension-sync.service

[Install]
WantedBy=timers.target
```

### 3) Enable timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now freudd-extension-sync.timer
sudo systemctl list-timers | rg freudd-extension-sync
```

### 4) Observe runs

```bash
sudo systemctl status freudd-extension-sync.timer
sudo systemctl status freudd-extension-sync.service
sudo journalctl -u freudd-extension-sync.service -n 200 --no-pager
```

---

## Option B: cron (fallback)

Install as root crontab:

```cron
0 2 * * * cd /opt/podcasts && /usr/bin/flock -n /tmp/freudd-extension-sync.lock /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica >> /var/log/freudd-extension-sync.log 2>&1
```

Notes:
- `flock` prevents overlapping runs.
- log rotation should be configured for `/var/log/freudd-extension-sync.log`.

---

## Failure playbook

1. Re-run in dry-run mode:

```bash
cd /opt/podcasts
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica --dry-run
```

2. Check credential metadata for impacted user:

```bash
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py extension_credentials --user <username> --extension habitica --show-meta
```

3. Rotate/rewrite credential if decrypt/auth fails:

```bash
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py extension_credentials --user <username> --extension habitica --set --habitica-user-id <id> --habitica-api-token <token> --habitica-task-id <task_id>
```

4. Replay specific date:

```bash
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py sync_extensions --extension habitica --user <username> --date YYYY-MM-DD
```

---

## Key rotation procedure

1. Update `FREUDD_CREDENTIALS_MASTER_KEY` and optionally increment `FREUDD_CREDENTIALS_KEY_VERSION` in `/etc/freudd-portal.env`.
2. Restart app service:

```bash
sudo systemctl restart freudd-portal
```

3. Re-encrypt each credential:

```bash
cd /opt/podcasts
sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py extension_credentials --user <username> --extension habitica --rotate-key-version
```
