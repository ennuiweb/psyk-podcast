#!/usr/bin/env bash
set -euo pipefail

NLM_BIN="${NLM_BIN:-nlm}"
TMP_FILE=$(mktemp)
trap 'rm -f "$TMP_FILE"' EXIT

cat >"$TMP_FILE"
python3 - "$TMP_FILE" <<'PY'
import sys, re, urllib.parse
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
def decode_at(match):
    return match.group(1) + urllib.parse.unquote(match.group(2))
text = re.sub(r'(at=)([^&\s\'"]+)', decode_at, text)
path.write_text(text)
PY

perl -0pe "s/-H 'Cookie: /-H 'cookie: /" "$TMP_FILE" | "$NLM_BIN" auth
