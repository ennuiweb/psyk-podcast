#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v clasp >/dev/null 2>&1; then
  clasp_cmd=(clasp)
elif command -v npx >/dev/null 2>&1; then
  clasp_cmd=(npx --yes @google/clasp)
else
  echo "Missing 'clasp' and 'npx'. Install Node.js or add clasp to PATH." >&2
  exit 1
fi

if [[ ! -f "${script_dir}/.clasp.json" ]]; then
  cat <<'EOF' >&2
Missing apps-script/.clasp.json.
1) Copy apps-script/.clasp.json.example to apps-script/.clasp.json
2) Replace scriptId with your Apps Script project ID
EOF
  exit 1
fi

cd "${script_dir}"

if [[ "${1:-}" == "--watch" ]]; then
  "${clasp_cmd[@]}" push --watch
else
  "${clasp_cmd[@]}" push
fi
