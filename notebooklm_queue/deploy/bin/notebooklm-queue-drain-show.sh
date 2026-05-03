#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <show-slug>" >&2
  exit 64
fi

show_slug="$1"
repo_root="${NOTEBOOKLM_QUEUE_REPO_ROOT:-/opt/podcasts}"
python_bin="${NOTEBOOKLM_QUEUE_PYTHON_BIN:-$repo_root/.venv/bin/python}"
cli_script="${NOTEBOOKLM_QUEUE_CLI_SCRIPT:-$repo_root/scripts/notebooklm_queue.py}"
max_stage_runs="${NOTEBOOKLM_QUEUE_MAX_STAGE_RUNS:-50}"
timeout_seconds="${NOTEBOOKLM_QUEUE_DOWNSTREAM_TIMEOUT_SECONDS:-900}"
poll_interval_seconds="${NOTEBOOKLM_QUEUE_DOWNSTREAM_POLL_SECONDS:-10}"
remote_name="${NOTEBOOKLM_QUEUE_REMOTE:-origin}"
branch_name="${NOTEBOOKLM_QUEUE_BRANCH:-main}"

cmd=(
  "$python_bin"
  "$cli_script"
  drain-show
  --repo-root "$repo_root"
  --show-slug "$show_slug"
  --max-stage-runs "$max_stage_runs"
  --timeout-seconds "$timeout_seconds"
  --poll-interval-seconds "$poll_interval_seconds"
  --remote "$remote_name"
  --branch "$branch_name"
)

if [[ -n "${NOTEBOOKLM_QUEUE_SHOW_CONFIG:-}" ]]; then
  cmd+=(--show-config "$NOTEBOOKLM_QUEUE_SHOW_CONFIG")
fi

if [[ -n "${NOTEBOOKLM_QUEUE_CONTENT_TYPES:-}" ]]; then
  IFS=',' read -r -a content_types <<<"${NOTEBOOKLM_QUEUE_CONTENT_TYPES}"
  for content_type in "${content_types[@]}"; do
    trimmed="$(printf '%s' "$content_type" | xargs)"
    if [[ -n "$trimmed" ]]; then
      cmd+=(--content-type "$trimmed")
    fi
  done
fi

exec "${cmd[@]}"
