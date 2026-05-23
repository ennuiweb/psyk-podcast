#!/usr/bin/env bash
set -euo pipefail

repo_root="${NOTEBOOKLM_QUEUE_REPO_ROOT:-/opt/podcasts}"
python_bin="${NOTEBOOKLM_QUEUE_PYTHON_BIN:-$repo_root/.venv/bin/python}"
cli_script="${NOTEBOOKLM_QUEUE_CLI_SCRIPT:-$repo_root/scripts/notebooklm_queue.py}"
storage_root="${NOTEBOOKLM_QUEUE_STORAGE_ROOT:-/var/lib/podcasts/notebooklm-queue}"
min_age_seconds="${NOTEBOOKLM_PROFILE_REFRESH_MIN_AGE_SECONDS:-900}"
actor="${NOTEBOOKLM_PROFILE_REFRESH_ACTOR:-systemd-profile-refresh}"

export NOTEBOOKLM_PROFILES_FILE="${NOTEBOOKLM_PROFILES_FILE:-/etc/podcasts/notebooklm-queue/profiles.host.json}"
export NOTEBOOKLM_PROFILE_STATE_FILE="${NOTEBOOKLM_PROFILE_STATE_FILE:-/root/.notebooklm/profile_state.json}"
unset NOTEBOOKLM_AUTH_JSON

cmd=(
  "$python_bin"
  "$cli_script"
  --storage-root "$storage_root"
  refresh-profiles
  --min-refresh-age-seconds "$min_age_seconds"
  --actor "$actor"
)

if [[ -n "${NOTEBOOKLM_PROFILE_PRIORITY:-}" ]]; then
  cmd+=(--profile-priority "$NOTEBOOKLM_PROFILE_PRIORITY")
fi

if [[ "${NOTEBOOKLM_PROFILE_REFRESH_FORCE:-0}" == "1" ]]; then
  cmd+=(--force)
fi

if [[ "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_ON_RECOVERY:-0}" == "1" ]]; then
  cmd+=(--reclaim-on-recovery)
  cmd+=(--reclaim-target-free-slots "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_TARGET_FREE_SLOTS:-25}")
  cmd+=(--reclaim-max-deletions "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_MAX_DELETIONS:-25}")
  if [[ "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_APPLY:-0}" == "1" ]]; then
    cmd+=(--reclaim-apply)
  fi
elif [[ "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_ON_AUTH_RECOVERY:-0}" == "1" ]]; then
  cmd+=(--reclaim-on-auth-recovery)
  cmd+=(--reclaim-target-free-slots "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_TARGET_FREE_SLOTS:-25}")
  cmd+=(--reclaim-max-deletions "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_MAX_DELETIONS:-25}")
  if [[ "${NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_APPLY:-0}" == "1" ]]; then
    cmd+=(--reclaim-apply)
  fi
fi

exec "${cmd[@]}"
