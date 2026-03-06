#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
apps_script_push_mode="${APPS_SCRIPT_PUSH_MODE:-best-effort}"
clasp_project_override="${APPS_SCRIPT_CLASP_JSON:-}"

warn() {
  echo "apps-script push: warning: $1" >&2
}

fail() {
  echo "apps-script push: $1" >&2
  exit 1
}

add_candidate() {
  local candidate="$1"
  if [[ -z "${candidate}" ]]; then
    return 0
  fi
  for existing in "${clasp_project_candidates[@]:-}"; do
    if [[ "${existing}" == "${candidate}" ]]; then
      return 0
    fi
  done
  clasp_project_candidates+=("${candidate}")
}

mode_exit_for_failure() {
  local message="$1"
  if [[ "${apps_script_push_mode}" == "required" ]]; then
    fail "${message}"
  fi
  warn "${message} (continuing; APPS_SCRIPT_PUSH_MODE=${apps_script_push_mode})"
  exit 0
}

case "${apps_script_push_mode}" in
  best-effort|required|off)
    ;;
  *)
    fail "invalid APPS_SCRIPT_PUSH_MODE='${apps_script_push_mode}' (expected: best-effort|required|off)"
    ;;
esac

if [[ "${apps_script_push_mode}" == "off" ]]; then
  exit 0
fi

clasp_project_candidates=()
if [[ -n "${clasp_project_override}" ]]; then
  if [[ "${clasp_project_override}" == /* ]]; then
    add_candidate "${clasp_project_override}"
  else
    add_candidate "${PWD}/${clasp_project_override}"
  fi
fi
add_candidate "${script_dir}/.clasp.json"

git_common_dir="$(git -C "${script_dir}" rev-parse --git-common-dir 2>/dev/null || true)"
if [[ -n "${git_common_dir}" ]]; then
  if [[ "${git_common_dir}" == /* ]]; then
    resolved_git_common_dir="${git_common_dir}"
  else
    resolved_git_common_dir="$(cd "${script_dir}/${git_common_dir}" && pwd)"
  fi
  shared_repo_root="$(cd "${resolved_git_common_dir}/.." && pwd)"
  add_candidate "${shared_repo_root}/apps-script/.clasp.json"
fi

clasp_project_path=""
for candidate in "${clasp_project_candidates[@]}"; do
  if [[ -f "${candidate}" ]]; then
    clasp_project_path="${candidate}"
    break
  fi
done

if [[ -z "${clasp_project_path}" ]]; then
  mode_exit_for_failure \
"missing Apps Script project config (.clasp.json). Tried: ${clasp_project_candidates[*]}. Copy apps-script/.clasp.json.example to apps-script/.clasp.json and set scriptId."
fi

if command -v clasp >/dev/null 2>&1; then
  clasp_cmd=(clasp)
elif command -v npx >/dev/null 2>&1; then
  clasp_cmd=(npx --yes @google/clasp)
else
  mode_exit_for_failure "missing 'clasp' and 'npx'. Install Node.js or add clasp to PATH."
fi

cd "${script_dir}"

if [[ "${1:-}" == "--watch" ]]; then
  clasp_push_cmd=("${clasp_cmd[@]}" -P "${clasp_project_path}" push --watch)
else
  clasp_push_cmd=("${clasp_cmd[@]}" -P "${clasp_project_path}" push)
fi

if ! "${clasp_push_cmd[@]}"; then
  mode_exit_for_failure "clasp push failed for project config: ${clasp_project_path}"
fi
