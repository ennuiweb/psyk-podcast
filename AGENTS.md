## Core Policies

- `freudd_portal` changes: deploy to `freudd-portal` as the final step.
- Podcast repo changes: commit + push, then run `gh workflow run generate-feed.yml --ref main`.
- `freudd_portal` model/schema changes: always run `makemigrations` + `migrate`.

## Mandatory Git Worktree Protocol (No Exceptions)

- One task = one worktree + one branch from `origin/main`.
- Naming: worktree path `.ai/worktrees/<task-name>`, branch `worktree-<task-name>`.
- Create task workspace with:

```bash
TASK="<kebab-task-name>"
git fetch origin
git worktree add ".ai/worktrees/$TASK" -b "worktree-$TASK" origin/main
```

- Only edit inside the assigned worktree.
- Only commit/push `worktree-$TASK`.
- Required first output:
- `Worktree: .ai/worktrees/<task-name>`
- `Branch: worktree-<task-name>`
- `Scope: <explicit in-scope work only>`
- `Constraint: Do not modify files outside this directory.`
- Parallel agents must use unique `TASK` names and non-overlapping scope; integrate only via merge to `main`.

### Done Gate (mandatory cleanup)

- A task is not finished until merged to `main` and cleanup is complete:

```bash
git worktree remove ".ai/worktrees/$TASK"
git branch -d "worktree-$TASK"
git push origin --delete "worktree-$TASK" || true
git worktree prune
```

- If any cleanup step fails, report it and continue until cleanup succeeds.

## Freudd Remote Deploy Runbook (verified 2026-02-25)

- Deploy must run over SSH from local machine (local has no `systemctl` and no `/opt/podcasts`).
- SSH target: `digitalocean-ennui-droplet-01` (`root@64.226.79.109`, key `~/.ssh/digitalocean_ed25519`).
- Production repo: `/opt/podcasts`; service: `freudd-portal.service`.
- Precondition: changes already committed and pushed to `origin/main`.

Standard deploy (non-destructive):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git checkout main; git pull --ff-only origin main; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal; systemctl status freudd-portal --no-pager -n 25'`

Fallback if `git pull --ff-only` fails due to dirty server worktree (only with explicit approval):
- `ssh digitalocean-ennui-droplet-01 'set -euo pipefail; cd /opt/podcasts; git fetch origin main; git reset --hard origin/main; git clean -fd; /opt/podcasts/.venv/bin/pip install -r /opt/podcasts/requirements.txt; sudo -u www-data /opt/podcasts/.venv/bin/python /opt/podcasts/freudd_portal/manage.py migrate; systemctl restart freudd-portal; systemctl is-active freudd-portal'`

Post-deploy smoke check:
- `ssh digitalocean-ennui-droplet-01 'echo \"gunicorn_login $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/accounts/login)\"; echo \"gunicorn_progress $(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8001/progress)\"; echo \"public_login $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/accounts/login)\"; echo \"public_progress $(curl -s -o /dev/null -w \"%{http_code}\" http://64.226.79.109/progress)\"'`
- Expected: `login=200`, `progress=302` (anonymous redirect to login).
