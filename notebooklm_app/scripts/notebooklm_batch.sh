#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${NOTEBOOKLM_ENV:-notebooklm_app/nlm.env}"
ENV_FILE_LOADED=0
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  ENV_FILE_LOADED=1
fi

SOURCES_DIR=${SOURCES_DIR:-notebooklm_app/sources}
OUTPUT_DIR=${OUTPUT_DIR:-notebooklm_app/outputs}
NOTEBOOK_TITLE_PREFIX=${NOTEBOOK_TITLE_PREFIX:-NotebookLM Batch}
EPISODE_FOCUS=${EPISODE_FOCUS:-}
LANGUAGE_CODE=${LANGUAGE_CODE:-en-US}
MAX_CONCURRENCY=${MAX_CONCURRENCY:-2}
AUTO_CLEANUP=${AUTO_CLEANUP:-0}
UPLOAD_MIME_OVERRIDE=${UPLOAD_MIME_OVERRIDE:-}
AUDIO_CREATE_MAX_RETRIES=${AUDIO_CREATE_MAX_RETRIES:-4}
AUDIO_CREATE_RETRY_DELAY=${AUDIO_CREATE_RETRY_DELAY:-5}
AUDIO_CREATE_RETRY_BACKOFF=${AUDIO_CREATE_RETRY_BACKOFF:-2}
NOTEBOOK_CREATE_MAX_RETRIES=${NOTEBOOK_CREATE_MAX_RETRIES:-4}
NOTEBOOK_CREATE_RETRY_DELAY=${NOTEBOOK_CREATE_RETRY_DELAY:-5}
NOTEBOOK_CREATE_RETRY_BACKOFF=${NOTEBOOK_CREATE_RETRY_BACKOFF:-2}
SOURCE_UPLOAD_MAX_RETRIES=${SOURCE_UPLOAD_MAX_RETRIES:-4}
SOURCE_UPLOAD_RETRY_DELAY=${SOURCE_UPLOAD_RETRY_DELAY:-5}
SOURCE_UPLOAD_RETRY_BACKOFF=${SOURCE_UPLOAD_RETRY_BACKOFF:-2}
NOTEBOOK_URL_LOG=${NOTEBOOK_URL_LOG:-notebooklm_app/outputs/notebook_urls.log}
GCLOUD_PROJECT_NUMBER=${GCLOUD_PROJECT_NUMBER:-}
GCLOUD_PROJECT_ID=${GCLOUD_PROJECT_ID:-}
GCLOUD_LOCATION=${GCLOUD_LOCATION:-}
GCLOUD_ENDPOINT_LOCATION=${GCLOUD_ENDPOINT_LOCATION:-$GCLOUD_LOCATION}
GCLOUD_DISCOVERY_API_VERSION=${GCLOUD_DISCOVERY_API_VERSION:-v1alpha}
GCLOUD_ACCESS_TOKEN_CMD=${GCLOUD_ACCESS_TOKEN_CMD:-gcloud auth print-access-token}
GCLOUD_AUTHUSER=${GCLOUD_AUTHUSER:-}
PYTHON_BIN=${PYTHON_BIN:-python3}
API_RESPONSE_STATUS=""
API_RESPONSE_BODY=""
API_RESPONSE_ERROR=""

log() {
  local prefix=""
  if [[ -n ${JOB_PREFIX:-} ]]; then
    prefix="[$JOB_PREFIX] "
  fi
  printf '[%s] %s%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$prefix" "$*" >&2
}

if (( ENV_FILE_LOADED )); then
  log "Loaded NotebookLM env config from $ENV_FILE"
else
  log "NotebookLM env file $ENV_FILE not found; relying on caller-provided environment"
fi

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
  local emit_body=${6:-1}
  API_RESPONSE_STATUS=""
  API_RESPONSE_BODY=""
  API_RESPONSE_ERROR=""
  local token
  if ! token=$(get_gcloud_access_token); then
    API_RESPONSE_ERROR="failed-to-fetch-token"
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
  http_status=$(printf '%s' "$http_status" | tr -d '
')
  local response_body=""
  if [[ -s $tmp_response ]]; then
    response_body=$(cat "$tmp_response")
  fi
  rm -f "$tmp_response"
  API_RESPONSE_STATUS="$http_status"
  API_RESPONSE_BODY="$response_body"
  API_RESPONSE_ERROR="${curl_stderr:-$response_body}"
  if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( $http_status >= 200 && $http_status < 300 )); then
    API_RESPONSE_ERROR="$curl_stderr"
    if (( emit_body )); then
      printf '%s' "$response_body"
    fi
    return 0
  fi
  if (( curl_exit != 0 )) && [[ -z $http_status || $http_status == 000 ]]; then
    log "${log_context} failed (${method} ${url}): curl exited $curl_exit${curl_stderr:+ - $curl_stderr}"
  else
    local snippet
    if [[ -n $response_body ]]; then
      snippet=$(printf '%s' "$response_body" | head -c 400 | tr '
' ' ')
    else
      snippet=$curl_stderr
    fi
    log "${log_context} failed (${method} ${url}): HTTP ${http_status:-unknown}${snippet:+ - $snippet}"
  fi
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

body_starts_with_json() {
  local body=$1
  local first_char
  first_char=$(printf '%s' "$body" | sed -e 's/^[[:space:]]*//' | head -c1)
  if [[ $first_char == "{" || $first_char == "[" ]]; then
    return 0
  fi
  return 1
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
  local attempt=1
  local max_attempts=$NOTEBOOK_CREATE_MAX_RETRIES
  local delay=$NOTEBOOK_CREATE_RETRY_DELAY
  local backoff=$NOTEBOOK_CREATE_RETRY_BACKOFF
  if (( max_attempts < 1 )); then
    max_attempts=1
  fi
  if (( delay < 1 )); then
    delay=1
  fi
  if (( backoff < 1 )); then
    backoff=1
  fi
  local wait=$delay
  while (( attempt <= max_attempts )); do
    if (( attempt == 1 )); then
      log "create_notebook request -> ${url} (project=${GCLOUD_PROJECT_NUMBER}, location=${GCLOUD_LOCATION})"
    fi
    local response=""
    local snippet=""
    if json_api_request POST "$url" "$payload" 1 "create notebook" 0; then
      response="$API_RESPONSE_BODY"
      snippet=$(printf '%s' "$response" | head -c 400 | tr '\n' ' ')
      if [[ -n $response ]] && body_starts_with_json "$response"; then
        local tmp_parse_err
        tmp_parse_err=$(mktemp "${TMPDIR:-/tmp}/notebook_parse_err.XXXXXX")
        local notebook_id
        if notebook_id=$("$PYTHON_BIN" -c '
import json
import sys

data = json.load(sys.stdin)
notebook_id = data.get("notebookId") or ""
if not notebook_id:
    name = data.get("name") or ""
    if name and "/" in name:
        notebook_id = name.rsplit("/", 1)[-1]
if notebook_id:
    print(notebook_id.strip())
' 2>"$tmp_parse_err" <<<"$response"); then
          rm -f "$tmp_parse_err"
          notebook_id=$(printf '%s' "$notebook_id" | tr -d '\r\n[:space:]')
          if [[ -n $notebook_id ]]; then
            printf '%s' "$notebook_id"
            return 0
          fi
          log "Notebook creation response missing notebookId${snippet:+ - $snippet}"
        else
          local parse_err=$(cat "$tmp_parse_err" 2>/dev/null)
          rm -f "$tmp_parse_err"
          log "Failed to parse notebook id from API response${snippet:+ - $snippet}${parse_err:+ - $parse_err}"
        fi
      else
        log "Notebook creation response was not JSON${snippet:+ - $snippet}"
      fi
    else
      response="$API_RESPONSE_BODY"
      snippet=$(printf '%s' "$response" | head -c 400 | tr '\n' ' ')
    fi
    local status=${API_RESPONSE_STATUS:-unknown}
    local message=${API_RESPONSE_ERROR:-}
    local message_snippet=$(printf '%s' "$message" | head -c 400 | tr '\n' ' ')
    log "create notebook failed (attempt ${attempt}/${max_attempts}): HTTP ${status} ${message_snippet}${snippet:+ | body: $snippet}"
    if (( attempt >= max_attempts )) || ! should_retry_api_error "$status" "$message"; then
      return 1
    fi
    log "Retrying notebook creation in ${wait}s"
    sleep "$wait"
    wait=$((wait * backoff))
    ((attempt++))
  done
  return 1
}


build_notebook_url() {
  local notebook_id=$1
  local ui_location=${GCLOUD_LOCATION:-global}
  local project_ref=${GCLOUD_PROJECT_NUMBER:-$GCLOUD_PROJECT_ID}
  if [[ -z $project_ref ]]; then
    log "Set GCLOUD_PROJECT_NUMBER (or GCLOUD_PROJECT_ID) to build notebook URLs"
    return 1
  fi
  local url
  url=$(printf 'https://notebooklm.cloud.google.com/%s/notebook/%s?project=%s' "$ui_location" "$notebook_id" "$project_ref")
  local authuser=""
  if [[ -n $GCLOUD_AUTHUSER ]]; then
    authuser=$GCLOUD_AUTHUSER
  elif [[ -n ${ENTERPRISE_PROJECT_URL:-} && ${ENTERPRISE_PROJECT_URL} == *authuser=* ]]; then
    authuser=${ENTERPRISE_PROJECT_URL#*authuser=}
    authuser=${authuser%%&*}
  fi
  if [[ -n $authuser ]]; then
    url="${url}&authuser=${authuser}"
  fi
  printf '%s' "$url"
}

record_notebook_url() {
  local notebook_id=$1
  local base_name=$2
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  local notebook_url
  if ! notebook_url=$(build_notebook_url "$notebook_id"); then
    return 1
  fi
  local entry="[$timestamp] ${base_name} -> ${notebook_url}"
  local log_path=$NOTEBOOK_URL_LOG
  mkdir -p "$(dirname "$log_path")"
  if ! "$PYTHON_BIN" - "$log_path" "$entry" <<'PY'
import fcntl
import os
import sys

path = sys.argv[1]
line = sys.argv[2] + "\n"
directory = os.path.dirname(path) or "."
os.makedirs(directory, exist_ok=True)
with open(path, "a", encoding="utf-8") as fh:
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    fh.write(line)
PY
  then
    log "Failed to append notebook URL to $log_path"
    return 1
  fi
  log "Notebook ready for review: $notebook_url"
  return 0
}

upload_source() {
  local notebook_id=$1
  local path=$2
  local mime_type
  mime_type=$(detect_mime_type "$path")
  local display_name
  display_name=$(basename "$path")
  local url
  url="$(upload_api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/sources:uploadFile"
  local attempt=1
  local max_attempts=$SOURCE_UPLOAD_MAX_RETRIES
  local delay=$SOURCE_UPLOAD_RETRY_DELAY
  local backoff=$SOURCE_UPLOAD_RETRY_BACKOFF
  if (( max_attempts < 1 )); then
    max_attempts=1
  fi
  if (( delay < 1 )); then
    delay=1
  fi
  if (( backoff < 1 )); then
    backoff=1
  fi
  local wait=$delay
  while (( attempt <= max_attempts )); do
    local token
    if ! token=$(get_gcloud_access_token); then
      log "Source upload failed (attempt ${attempt}/${max_attempts}): could not obtain gcloud token"
      API_RESPONSE_STATUS=""
      API_RESPONSE_BODY=""
      API_RESPONSE_ERROR="failed-to-fetch-token"
      if (( attempt >= max_attempts )); then
        return 1
      fi
      sleep "$wait"
      wait=$((wait * backoff))
      ((attempt++))
      continue
    fi
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
    API_RESPONSE_STATUS="$http_status"
    API_RESPONSE_BODY="$response_body"
    API_RESPONSE_ERROR="${curl_stderr:-$response_body}"
    if (( curl_exit == 0 )) && [[ $http_status =~ ^[0-9]+$ ]] && (( $http_status >= 200 && $http_status < 300 )); then
      if [[ -z $response_body ]] || ! body_starts_with_json "$response_body"; then
        local snippet
        snippet=$(printf '%s' "$response_body" | head -c 400 | tr '\n' ' ')
        log "Source upload returned non-JSON payload${snippet:+ - $snippet}"
        if (( attempt >= max_attempts )); then
          return 1
        fi
        log "Retrying source upload in ${wait}s"
        sleep "$wait"
        wait=$((wait * backoff))
        ((attempt++))
        continue
      fi
      API_RESPONSE_ERROR="$curl_stderr"
      local source_id
      local tmp_source_parse_err
      tmp_source_parse_err=$(mktemp "${TMPDIR:-/tmp}/source_parse_err.XXXXXX")
      if ! source_id=$("$PYTHON_BIN" -c '
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
' 2>"$tmp_source_parse_err" <<<"$response_body"); then
        local parse_err=$(cat "$tmp_source_parse_err" 2>/dev/null)
        rm -f "$tmp_source_parse_err"
        log "Failed to parse source id from upload response${parse_err:+ - $parse_err}"
        return 1
      fi
      rm -f "$tmp_source_parse_err"
      source_id=$(printf '%s' "$source_id" | tr -d '\r\n[:space:]')
      if [[ -z $source_id ]]; then
        log "Upload response did not include a source id"
        return 1
      fi
      printf '%s' "$source_id"
      return 0
    fi
    local message=${API_RESPONSE_ERROR:-}
    local message_snippet=$(printf '%s' "$message" | head -c 400 | tr '\n' ' ')
    local body_snippet=$(printf '%s' "$response_body" | head -c 400 | tr '\n' ' ')
    log "Source upload failed (attempt ${attempt}/${max_attempts}): HTTP ${http_status:-unknown} ${message_snippet}${body_snippet:+ | body: $body_snippet}"
    if (( attempt >= max_attempts )) || ! should_retry_api_error "$http_status" "$message"; then
      return 1
    fi
    log "Retrying source upload in ${wait}s"
    sleep "$wait"
    wait=$((wait * backoff))
    ((attempt++))
  done
  return 1
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

generation_options = {
    "sourceIds": [{"id": sid} for sid in source_ids],
}
if focus:
    generation_options["episodeFocus"] = focus
if language:
    generation_options["languageCode"] = language

print(json.dumps({"generationOptions": generation_options}, separators=(",", ":")))
PY
  ); then
    local err_msg=$(cat "$tmp_payload_err" 2>/dev/null)
    rm -f "$tmp_payload_err"
    log "Failed to build audio overview payload${err_msg:+: $err_msg}"
    return 1
  fi
  rm -f "$tmp_payload_err"

  local api_url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/audioOverviews"
  local wait=$delay
  while (( attempt <= max_attempts )); do
    if json_api_request POST "$api_url" "$payload" 1 "request audio overview" 0; then
      return 0
    fi
    local status=${API_RESPONSE_STATUS:-unknown}
    local message=${API_RESPONSE_ERROR:-}
    local message_snippet=$(printf '%s' "$message" | head -c 400 | tr '\n' ' ')
    local body_snippet=$(printf '%s' "${API_RESPONSE_BODY:-}" | head -c 400 | tr '\n' ' ')
    log "Audio overview API request failed (attempt ${attempt}/${max_attempts}): HTTP ${status} ${message_snippet}${body_snippet:+ | body: $body_snippet}"
    if (( attempt >= max_attempts )) || ! should_retry_api_error "$status" "$message"; then
      return 1
    fi
    log "Retrying audio overview request in ${wait}s"
    sleep "$wait"
    wait=$((wait * backoff))
    ((attempt++))
  done
  return 1
}


should_retry_api_error() {
  local status=${1:-}
  local message=${2:-}
  if [[ -z $status ]]; then
    status=0
  fi
  if [[ $status =~ ^(401|403|408|425|429|500|502|503|504)$ ]]; then
    return 0
  fi
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
  json_api_request DELETE "$url" "" 0 "delete audio overview" 0 >/dev/null 2>&1 || true
}

cleanup_source() {
  local notebook_id=$1
  local source_id=$2
  if [[ -z $source_id ]]; then
    return
  fi
  local url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}/sources/${source_id}"
  json_api_request DELETE "$url" "" 0 "delete source" 0 >/dev/null 2>&1 || true
}

cleanup_notebook() {
  local notebook_id=$1
  local url="$(api_base)/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${notebook_id}"
  json_api_request DELETE "$url" "" 0 "delete notebook" 0 >/dev/null 2>&1 || true
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
    if [[ ${AUTO_CLEANUP:-0} -ne 1 ]]; then
      return
    fi
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
    local status=${API_RESPONSE_STATUS:-unknown}
    local message=${API_RESPONSE_ERROR:-}
    local snippet=$(printf '%s' "$message" | head -c 400 | tr '\n' ' ')
    log "Notebook creation failed (HTTP ${status}): ${snippet}"
    return 1
  fi
  log "Created notebook $notebook_id"

  if ! source_id=$(upload_source "$notebook_id" "$path"); then
    local status=${API_RESPONSE_STATUS:-unknown}
    local message=${API_RESPONSE_ERROR:-}
    local snippet=$(printf '%s' "$message" | head -c 400 | tr '\n' ' ')
    log "Source upload failed (HTTP ${status}): ${snippet}"
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

  if ! record_notebook_url "$notebook_id" "$base"; then
    log "Failed to log notebook URL"
    return 1
  fi

  return 0
}

ensure_python
ensure_gcloud_prereqs
log "Using NotebookLM API base: $(api_base) (project=${GCLOUD_PROJECT_NUMBER}, location=${GCLOUD_LOCATION}, endpoint_host=${GCLOUD_ENDPOINT_LOCATION})"
log "Using upload API base: $(upload_api_base)"
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
