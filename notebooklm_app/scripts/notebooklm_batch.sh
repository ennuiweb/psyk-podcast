#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${NOTEBOOKLM_ENV:-notebooklm_app/nlm.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

SOURCES_DIR=${SOURCES_DIR:-notebooklm_app/sources}
OUTPUT_DIR=${OUTPUT_DIR:-notebooklm_app/outputs}
NOTEBOOK_TITLE_PREFIX=${NOTEBOOK_TITLE_PREFIX:-NotebookLM Batch}
EPISODE_FOCUS=${EPISODE_FOCUS:-}
LANGUAGE_CODE=${LANGUAGE_CODE:-en-US}
POLL_INTERVAL=${POLL_INTERVAL:-30}
POLL_TIMEOUT=${POLL_TIMEOUT:-900}
MAX_CONCURRENCY=${MAX_CONCURRENCY:-2}
UPLOAD_MIME_OVERRIDE=${UPLOAD_MIME_OVERRIDE:-}
OUTPUT_AUDIO_FORMAT=${OUTPUT_AUDIO_FORMAT:-mp3}
MP3_BITRATE=${MP3_BITRATE:-128k}
KEEP_WAV=${KEEP_WAV:-0}
AUDIO_CREATE_MAX_RETRIES=${AUDIO_CREATE_MAX_RETRIES:-4}
AUDIO_CREATE_RETRY_DELAY=${AUDIO_CREATE_RETRY_DELAY:-5}
AUDIO_CREATE_RETRY_BACKOFF=${AUDIO_CREATE_RETRY_BACKOFF:-2}
LAST_AUDIO_PATH=""
GCLOUD_PROJECT_NUMBER=${GCLOUD_PROJECT_NUMBER:-}
GCLOUD_PROJECT_ID=${GCLOUD_PROJECT_ID:-}
GCLOUD_LOCATION=${GCLOUD_LOCATION:-}
GCLOUD_ENDPOINT_LOCATION=${GCLOUD_ENDPOINT_LOCATION:-$GCLOUD_LOCATION}
GCLOUD_DISCOVERY_API_VERSION=${GCLOUD_DISCOVERY_API_VERSION:-v1alpha}
GCLOUD_ACCESS_TOKEN_CMD=${GCLOUD_ACCESS_TOKEN_CMD:-gcloud auth print-access-token}
PYTHON_BIN=${PYTHON_BIN:-python3}

log() {
  local prefix=""
  if [[ -n ${JOB_PREFIX:-} ]]; then
    prefix="[$JOB_PREFIX] "
  fi
  printf '[%s] %s%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$prefix" "$*"
}

ensure_python() {
  if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
    return
  fi
  log "python3 (or python) is required for JSON payload handling. Install it and rerun."
  exit 1
}

ensure_gcloud_prereqs() {
  if ! command -v gcloud >/dev/null 2>&1; then
    log "gcloud CLI is required for all NotebookLM Enterprise API calls. Install it via https://cloud.google.com/sdk and rerun."
    exit 1
  fi
  if [[ -z $GCLOUD_PROJECT_NUMBER ]]; then
    log "Set GCLOUD_PROJECT_NUMBER in $ENV_FILE (or the environment) before running the batch script."
    exit 1
  fi
  if [[ -z $GCLOUD_LOCATION ]]; then
    log "Set GCLOUD_LOCATION in $ENV_FILE (or the environment) before running the batch script."
    exit 1
  fi
  if [[ -z $GCLOUD_ENDPOINT_LOCATION ]]; then
    GCLOUD_ENDPOINT_LOCATION="$GCLOUD_LOCATION"
  fi
  if [[ $GCLOUD_ENDPOINT_LOCATION != *- ]]; then
    GCLOUD_ENDPOINT_LOCATION="${GCLOUD_ENDPOINT_LOCATION}-"
  fi
}

api_base() {
  printf 'https://%sdiscoveryengine.googleapis.com/%s' "$GCLOUD_ENDPOINT_LOCATION" "$GCLOUD_DISCOVERY_API_VERSION"
}

upload_api_base() {
  printf 'https://%sdiscoveryengine.googleapis.com/upload/%s' "$GCLOUD_ENDPOINT_LOCATION" "$GCLOUD_DISCOVERY_API_VERSION"
}

get_gcloud_access_token() {
  local tmp_err
  tmp_err=$(mktemp "${TMPDIR:-/tmp}/gcloud_token_err.XXXXXX")
  local token
  if ! token=$($GCLOUD_ACCESS_TOKEN_CMD 2>"$tmp_err"); then
    local err_msg="$(cat "$tmp_err" 2>/dev/null)"
    rm -f "$tmp_err"
    log "Failed to obtain gcloud access token${err_msg:+: $err_msg}"
    return 1
  fi
  rm -f "$tmp_err"
  token=$(printf '%s' "$token" | tr -d '\r\n')
  if [[ -z $token ]]; then
    log "gcloud returned an empty access token"
    return 1
  fi
  printf '%s' "$token"
}

json_api_request() {
  local method=$1
  local url=$2
  local payload=${3:-}
  local send_payload=${4:-0}
  local log_context=${5:-"API request"}
  local token
  if ! token=$(get_gcloud_access_token); then
    return 1
  fi
  local tmp_response tmp_err
  tmp_response=$(mktemp "${TMPDIR:-/tmp}/discovery_api_resp.XXXXXX")
  tmp_err=$(mktemp "${TMPDIR:-/tmp}/discovery_api_err.XXXXXX")
  local -a curl_cmd
  curl_cmd=(curl -sS -X "$method" -H "Authorization:Bearer ${token}" -H "Content-Type: application/json" -o "$tmp_response" -w '%{http_code}' "$url")
  if (( send_payload )); then
    curl_cmd+=(-d "$payload")
  fi
  local http_status
  http_status=$("${curl_cmd[@]}" 2>"$tmp_err")
  local curl_exit=$?
  local curl_stderr=""
  if [[ -s $tmp_err ]]; then
    curl_stderr=$(cat "$tmp_err")
  fi
  rm -f "$tmp_err"
      http_status=$(printf '%s' "$http_status" | tr -d '\r\n')
  local response_body=""
  if [[ -s $tmp_response ]]; then
    response_body=$(cat "$tmp_response")
  fi
  rm -f "$tmp_response"
  if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( http_status >= 200 && http_status < 300 )); then
    printf '%s' "$response_body"
    return 0
  fi
  if (( curl_exit != 0 )) && [[ -z $http_status || $http_status == 000 ]]; then
    log "${log_context} failed: curl exited $curl_exit${curl_stderr:+ - $curl_stderr}"
  else
    log "${log_context} failed: HTTP ${http_status:-unknown}${curl_stderr:+ - $curl_stderr}${response_body:+ - $response_body}"
  fi
  return 1
}

download_with_optional_auth() {
  local url=$1
  local destination=$2
  local tmp_file
  tmp_file=$(mktemp "${TMPDIR:-/tmp}/audio_download.XXXXXX")
  local http_status
  http_status=$(curl -sS -L -o "$tmp_file" -w '%{http_code}' "$url")
  local curl_exit=$?
  http_status=$(printf '%s' "$http_status" | tr -d '\r\n')
  if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( http_status >= 200 && http_status < 300 )); then
    mv "$tmp_file" "$destination"
    return 0
  fi
  local token
  if ! token=$(get_gcloud_access_token); then
    rm -f "$tmp_file"
    return 1
  fi
  http_status=$(curl -sS -L -H "Authorization:Bearer ${token}" -o "$tmp_file" -w '%{http_code}' "$url")
  curl_exit=$?
  http_status=$(printf '%s' "$http_status" | tr -d '\r\n')
  if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( http_status >= 200 && http_status < 300 )); then
    mv "$tmp_file" "$destination"
    return 0
  fi
  rm -f "$tmp_file"
  log "Audio download failed: HTTP ${http_status:-unknown} (url: $url)"
  return 1
}

detect_mime_type() {
  local path=$1
  if [[ -n $UPLOAD_MIME_OVERRIDE ]]; then
    printf '%s' "$UPLOAD_MIME_OVERRIDE"
    return
  fi
  if command -v file >/dev/null 2>&1; then
    local detected
    detected=$(file -b --mime-type "$path" 2>/dev/null | tr -d '\r\n') || true
    if [[ -n $detected ]]; then
      printf '%s' "$detected"
      return
    fi
  fi
  printf 'application/octet-stream'
}

ensure_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1; then
    return
  fi
  log "ffmpeg is required to convert WAV to MP3. Install it (e.g., 'brew install ffmpeg') or set OUTPUT_AUDIO_FORMAT=wav."
  exit 1
}

trim_last_non_empty_line() {
  awk 'NF{last=$0} END{print last}'
}

create_notebook() {
  local title=$1
  local payload
  if ! payload=$("$PYTHON_BIN" - "$title" <<'PY'
import json
import sys

title = sys.argv[1]
print(json.dumps({"title": title}))
PY
  ); then
    log "Failed to build notebook creation payload"
    return 1
  fi
  local url
  url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks"
  local response
  if ! response=$(json_api_request POST "$url" "$payload" 1 "create notebook"); then
    return 1
  fi
  local notebook_id
  if ! notebook_id=$(printf '%s' "$response" | "$PYTHON_BIN" - <<'PY'
import json
import sys

data = json.load(sys.stdin)
notebook_id = data.get("notebookId") or ""
if notebook_id:
    print(notebook_id.strip())
PY
  ); then
    log "Failed to parse notebook id from API response"
    return 1
  fi
  notebook_id=$(printf '%s' "$notebook_id" | tr -d '\r\n[:space:]')
  if [[ -z $notebook_id ]]; then
    log "Notebook creation response did not include notebookId"
    return 1
  fi
  printf '%s' "$notebook_id"
}

upload_source() {
  local notebook_id=$1
  local path=$2
  local mime_type
  mime_type=$(detect_mime_type "$path")
  local display_name
  display_name=$(basename "$path")
  local token
  if ! token=$(get_gcloud_access_token); then
    return 1
  fi
  local url
  url="$(upload_api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/sources:uploadFile"
  local tmp_response tmp_err
  tmp_response=$(mktemp "${TMPDIR:-/tmp}/source_upload_resp.XXXXXX")
  tmp_err=$(mktemp "${TMPDIR:-/tmp}/source_upload_err.XXXXXX")
  local http_status
  http_status=$(curl -sS -X POST --data-binary @"$path" \
    -H "Authorization:Bearer ${token}" \
    -H "X-Goog-Upload-File-Name: ${display_name}" \
    -H "X-Goog-Upload-Protocol: raw" \
    -H "Content-Type: ${mime_type}" \
    -o "$tmp_response" \
    -w '%{http_code}' \
    "$url" 2>"$tmp_err")
  local curl_exit=$?
  local curl_stderr=""
  if [[ -s $tmp_err ]]; then
    curl_stderr=$(cat "$tmp_err")
  fi
  rm -f "$tmp_err"
  http_status=$(printf '%s' "$http_status" | tr -d '\r\n')
  local response_body=""
  if [[ -s $tmp_response ]]; then
    response_body=$(cat "$tmp_response")
  fi
  rm -f "$tmp_response"
  if ! (( curl_exit == 0 )) || [[ ! $http_status =~ ^[0-9]+$ ]] || (( http_status < 200 || http_status >= 300 )); then
    log "Source upload failed (HTTP ${http_status:-unknown})${curl_stderr:+ - $curl_stderr}${response_body:+ - $response_body}"
    return 1
  fi
  local source_id
  if ! source_id=$(printf '%s' "$response_body" | "$PYTHON_BIN" - <<'PY'
import json
import sys

data = json.load(sys.stdin)
sid = ""
source_id = data.get("sourceId")
if isinstance(source_id, dict):
    sid = source_id.get("id", "")
elif isinstance(source_id, str):
    sid = source_id
if not sid:
    sources = data.get("sources") or []
    if isinstance(sources, list) and sources:
        entry = sources[0]
        inner = entry.get("sourceId") if isinstance(entry, dict) else None
        if isinstance(inner, dict):
            sid = inner.get("id", "")
if sid:
    print(sid.strip())
PY
  ); then
    log "Failed to parse source id from upload response"
    return 1
  fi
  source_id=$(printf '%s' "$source_id" | tr -d '\r\n[:space:]')
  if [[ -z $source_id ]]; then
    log "Upload response did not include a source id"
    return 1
  fi
  printf '%s' "$source_id"
}

request_audio_overview() {
  local notebook_id=$1
  local instructions=$2
  shift 2
  local source_args=("$@")
  local attempt=1
  local max_attempts=$AUDIO_CREATE_MAX_RETRIES
  local delay=$AUDIO_CREATE_RETRY_DELAY
  local backoff=$AUDIO_CREATE_RETRY_BACKOFF

  if (( ${#source_args[@]} == 0 )); then
    log "No source ids provided for audio overview request"
    return 1
  fi

  if (( max_attempts < 1 )); then
    max_attempts=1
  fi
  if (( delay < 1 )); then
    delay=1
  fi
  if (( backoff < 1 )); then
    backoff=1
  fi

  local tmp_payload_err
  tmp_payload_err=$(mktemp "${TMPDIR:-/tmp}/audio_payload_err.XXXXXX")
  local payload=""
  if ! payload=$(AUDIO_FOCUS="$instructions" AUDIO_LANGUAGE="$LANGUAGE_CODE" "$PYTHON_BIN" - "${source_args[@]}" 2>"$tmp_payload_err" <<'PY'
import json
import os
import sys

focus = os.environ.get("AUDIO_FOCUS", "")
language = os.environ.get("AUDIO_LANGUAGE", "")
source_ids = sys.argv[1:]
if not source_ids:
    raise SystemExit("at least one source id is required")

payload = {
    "sourceIds": [{"id": sid} for sid in source_ids],
}
if focus:
    payload["episodeFocus"] = focus
if language:
    payload["languageCode"] = language

print(json.dumps(payload, separators=(",", ":")))
PY
); then
    local err_msg="$(cat "$tmp_payload_err" 2>/dev/null)"
    rm -f "$tmp_payload_err"
    log "Failed to build audio overview payload${err_msg:+: $err_msg}"
    return 1
  fi
  rm -f "$tmp_payload_err"

  local api_url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/audioOverviews"

  local wait=$delay
  while (( attempt <= max_attempts )); do
    local output=""
    local access_token
    if ! access_token=$(get_gcloud_access_token); then
      output="Failed to obtain gcloud access token"
    else
      local tmp_response tmp_err
      tmp_response=$(mktemp "${TMPDIR:-/tmp}/audio_overview_response.XXXXXX")
      tmp_err=$(mktemp "${TMPDIR:-/tmp}/audio_overview_err.XXXXXX")
      local http_status
      http_status=$(curl -sS -X POST \
        -H "Authorization:Bearer ${access_token}" \
        -H "Content-Type: application/json" \
        -o "$tmp_response" \
        -w '%{http_code}' \
        "$api_url" \
        -d "$payload" 2>"$tmp_err")
      local curl_exit=$?
      local curl_stderr=""
      if [[ -s $tmp_err ]]; then
        curl_stderr=$(cat "$tmp_err")
      fi
      rm -f "$tmp_err"
      http_status=$(printf '%s' "$http_status" | tr -d '\r\n')
      local response_body=""
      if [[ -s $tmp_response ]]; then
        response_body=$(cat "$tmp_response")
      fi
      rm -f "$tmp_response"
      if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( $http_status >= 200 && $http_status < 300 )); then
        return 0
      fi
      if (( curl_exit != 0 )) && [[ -z $http_status || $http_status == 000 ]]; then
        output="curl exited $curl_exit: ${curl_stderr:-$response_body}"
      else
        output="HTTP ${http_status:-unknown}: ${response_body:-$curl_stderr}"
      fi
    fi
    log "Audio overview API request failed (attempt ${attempt}/${max_attempts})"
    log "$output"
    if (( attempt >= max_attempts )) || ! should_retry_audio_create "$output"; then
      return 1
    fi
    log "Retrying audio overview request in ${wait}s"
    sleep "$wait"
    ((attempt++))
    wait=$((wait * backoff))
  done
  return 1
}

should_retry_audio_create() {
  local message=$1
  if grep -qiE 'unavailable|temporar|timeout|try again|deadline|rate limit|429|bad gateway|502|503|internal error' <<<"$message"; then
    return 0
  fi
  return 1
}

build_instructions() {
  local base=$1
  local focus
  if [[ -n $EPISODE_FOCUS ]]; then
    focus=$EPISODE_FOCUS
  else
    focus="Summarize '${base}' for listeners."
  fi
  printf '%s (Language: %s)' "$focus" "$LANGUAGE_CODE"
}

cleanup_audio() {
  local notebook_id=$1
  local url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/audioOverviews/default"
  json_api_request DELETE "$url" "" 0 "delete audio overview" >/dev/null 2>&1 || true
}

cleanup_source() {
  local notebook_id=$1
  local source_id=$2
  if [[ -z $source_id ]]; then
    return
  fi
  local url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/sources/${source_id}"
  json_api_request DELETE "$url" "" 0 "delete source" >/dev/null 2>&1 || true
}

cleanup_notebook() {
  local notebook_id=$1
  local url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}"
  json_api_request DELETE "$url" "" 0 "delete notebook" >/dev/null 2>&1 || true
}

download_audio_with_api() {
  local notebook_id=$1
  local base=$2
  local start=$(date +%s)
  local timeout=${POLL_TIMEOUT:-0}
  local interval=${POLL_INTERVAL:-30}
  local status_url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/audioOverviews/default"
  while true; do
    local status_file
    status_file=$(mktemp "${TMPDIR:-/tmp}/audio_overview_status.XXXXXX.json")
    if ! json_api_request GET "$status_url" "" 0 "fetch audio overview status" >"$status_file"; then
      rm -f "$status_file"
      return 1
    fi
    local tmp_audio
    tmp_audio=$(mktemp "${TMPDIR:-/tmp}/audio_overview_file.XXXXXX")
    local python_output
    if ! python_output=$("$PYTHON_BIN" - "$status_file" "$tmp_audio" <<'PY'
import base64
import json
import re
import sys

status_path = sys.argv[1]
output_path = sys.argv[2]
with open(status_path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

state = ""
url = ""
mime = ""
error = ""
encoded = ""

def consider_string(key_path, value):
    global state, url, mime, error, encoded
    kl = key_path.lower()
    if not state and ("state" in kl or "status" in kl):
        state = value
    if not mime and "mime" in kl:
        mime = value
    if not url and ("url" in kl or "uri" in kl) and ("audio" in kl or "download" in kl or "signed" in kl):
        url = value
    if not encoded and "content" in kl and len(value) > 512 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", value):
        encoded = value
    if not error and "error" in kl:
        error = value

def walk(obj, path=""):
    if isinstance(obj, dict):
        err = obj.get("error")
        if isinstance(err, dict) and not error:
            msg = err.get("message") or err.get("code") or ""
            if msg:
                nonlocal_error[0] = msg
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(value, str):
                consider_string(child_path, value)
            elif isinstance(value, (dict, list)):
                walk(value, child_path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            walk(item, f"{path}[{idx}]")

nonlocal_error = [""]
walk(data)
if nonlocal_error[0] and not error:
    error = nonlocal_error[0]

wrote = False
if encoded:
    try:
        decoded = base64.b64decode(encoded)
    except Exception:
        encoded = ""
    else:
        with open(output_path, "wb") as fh:
            fh.write(decoded)
        wrote = True

print(state or "")
print(url or "")
print(mime or "")
print(error or "")
print("true" if wrote else "false")
PY
    ); then
      rm -f "$status_file" "$tmp_audio"
      log "Failed to parse audio overview status"
      return 1
    fi
    rm -f "$status_file"
    local state download_url mime_type err_msg wrote
    IFS=$'\n' read -r state download_url mime_type err_msg wrote <<<"$python_output"
    if [[ -n $err_msg ]]; then
      rm -f "$tmp_audio"
      log "Audio overview status error: $err_msg"
      return 1
    fi
    local extension="wav"
    if [[ -n $mime_type ]]; then
      case ${mime_type,,} in
        audio/mpeg|audio/mp3) extension="mp3" ;;
        audio/flac) extension="flac" ;;
        audio/wav|audio/x-wav|audio/wave) extension="wav" ;;
      esac
    fi
    local output_path="$OUTPUT_DIR/${base}.${extension}"
    if [[ $wrote == "true" ]]; then
      mkdir -p "$(dirname "$output_path")"
      mv "$tmp_audio" "$output_path"
      LAST_AUDIO_PATH="$output_path"
      log "Saved $output_path (embedded audio payload)"
      return 0
    fi
    rm -f "$tmp_audio"
    if [[ -n $download_url ]]; then
      mkdir -p "$(dirname "$output_path")"
      if download_with_optional_auth "$download_url" "$output_path"; then
        LAST_AUDIO_PATH="$output_path"
        log "Saved $output_path (download URL)"
        return 0
      fi
      log "Downloading audio overview from API-provided URL failed"
      return 1
    fi
    local now=$(date +%s)
    if (( timeout > 0 && now - start > timeout )); then
      log "Timed out waiting for audio overview after $((now - start))s${state:+ (last state: $state)}"
      return 1
    fi
    if [[ -n $state ]]; then
      log "Audio overview still processing (state: $state)"
    else
      log "Audio overview still processing"
    fi
    rm -f "$tmp_audio"
    sleep "$interval"
  done
}

post_process_audio() {
  local source_path=$1
  local format=$(printf '%s' "$OUTPUT_AUDIO_FORMAT" | tr '[:upper:]' '[:lower:]')
  if [[ $format != "mp3" ]]; then
    return 0
  fi
  ensure_ffmpeg
  local target_path="${source_path%.wav}.mp3"
  if ! ffmpeg -y -loglevel error -i "$source_path" -codec:a libmp3lame -b:a "$MP3_BITRATE" "$target_path"; then
    log "ffmpeg conversion failed for $source_path"
    return 1
  fi
  log "Converted to $target_path (ffmpeg, bitrate $MP3_BITRATE)"
  if [[ ${KEEP_WAV:-0} -eq 0 ]]; then
    rm -f "$source_path"
    log "Deleted intermediate WAV $source_path"
  fi
  return 0
}

process_file() {
  local path=$1
  local worker_id=${2:-0}
  local base=$(basename "$path")
  JOB_PREFIX="${base}|worker-${worker_id}"
  log "Processing $base"

  local notebook_id=""
  local source_id=""
  cleanup_on_exit() {
    if [[ -n $source_id && -n $notebook_id ]]; then
      cleanup_source "$notebook_id" "$source_id"
      source_id=""
    fi
    if [[ -n $notebook_id ]]; then
      cleanup_audio "$notebook_id"
      cleanup_notebook "$notebook_id"
      notebook_id=""
    fi
  }
  trap cleanup_on_exit RETURN

  local notebook_title="${NOTEBOOK_TITLE_PREFIX} ${base}"
  if ! notebook_id=$(create_notebook "$notebook_title"); then
    log "Notebook creation failed"
    return 1
  fi
  log "Created notebook $notebook_id"

  if ! source_id=$(upload_source "$notebook_id" "$path"); then
    log "Source upload failed"
    return 1
  fi
  log "Uploaded source id $source_id"

  sleep 2  # give NotebookLM a moment to index the upload

  local instructions
  instructions=$(build_instructions "$base")
  if ! request_audio_overview "$notebook_id" "$instructions" "$source_id"; then
    log "Audio overview request failed"
    return 1
  fi
  log "Requested audio overview"

  if ! download_audio_with_nlm "$notebook_id" "$base"; then
    return 1
  fi
  if [[ -n $LAST_AUDIO_PATH ]]; then
    if ! post_process_audio "$LAST_AUDIO_PATH"; then
      return 1
    fi
    LAST_AUDIO_PATH=""
  fi

  return 0
}

ensure_nlm
require_nlm_auth
mkdir -p "$OUTPUT_DIR"
shopt -s nullglob
files=("$SOURCES_DIR"/*)
if [[ ${#files[@]} -eq 0 ]]; then
  log "No files in $SOURCES_DIR"
  exit 0
fi

if (( MAX_CONCURRENCY < 1 )); then
  MAX_CONCURRENCY=1
fi

active_pids=()
active_files=()
job_results=()
worker_id=0

wait_for_pid() {
  local pid=$1
  local file=$2
  if wait "$pid"; then
    job_results+=("$file:0")
  else
    job_results+=("$file:$?")
  fi
}

wait_first() {
  local pid=${active_pids[0]}
  local file=${active_files[0]}
  wait_for_pid "$pid" "$file"
  active_pids=("${active_pids[@]:1}")
  active_files=("${active_files[@]:1}")
}

for file in "${files[@]}"; do
  ((worker_id++))
  (
    if ! process_file "$file" "$worker_id"; then
      exit 1
    fi
  ) &
  pid=$!
  active_pids+=("$pid")
  active_files+=("$file")
  if (( ${#active_pids[@]} >= MAX_CONCURRENCY )); then
    wait_first
  fi
  sleep $(( (RANDOM % 3) + 1 ))
done

while (( ${#active_pids[@]} )); do
  wait_first
done

success=0
failed=0
for result in "${job_results[@]}"; do
  file=${result%%:*}
  status=${result##*:}
  if [[ $status -eq 0 ]]; then
    ((success++))
  else
    ((failed++))
    log "Failed: $file (exit $status)"
  fi
done

log "Completed processing: ${success} succeeded, ${failed} failed."
if (( failed > 0 )); then
  exit 1
fi
