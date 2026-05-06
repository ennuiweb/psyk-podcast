"""Shared constants for the NotebookLM queue subsystem."""

from __future__ import annotations

import os
from pathlib import Path

QUEUE_VERSION = 1

DEFAULT_STORAGE_ROOT = Path(
    os.environ.get("NOTEBOOKLM_QUEUE_STORAGE_ROOT") or "/var/lib/podcasts/notebooklm-queue"
)

STATE_DISCOVERED = "discovered"
STATE_BLOCKED_MANUAL_PREREQ = "blocked_manual_prereq"
STATE_BLOCKED_CONFIG_ERROR = "blocked_config_error"
STATE_QUEUED = "queued"
STATE_GENERATING = "generating"
STATE_WAITING_FOR_ARTIFACT = "waiting_for_artifact"
STATE_GENERATED = "generated"
STATE_DOWNLOADING = "downloading"
STATE_DOWNLOADED = "downloaded"
STATE_VALIDATING_GENERATED_ARTIFACTS = "validating_generated_artifacts"
STATE_AWAITING_PUBLISH = "awaiting_publish"
STATE_UPLOADING_OBJECTS = "uploading_objects"
STATE_OBJECTS_UPLOADED = "objects_uploaded"
STATE_REBUILDING_METADATA = "rebuilding_metadata"
STATE_VALIDATING_PUBLISH_BUNDLE = "validating_publish_bundle"
STATE_COMMITTING_REPO_ARTIFACTS = "committing_repo_artifacts"
STATE_REPO_PUSHED = "repo_pushed"
STATE_SYNCING_DOWNSTREAM = "syncing_downstream"
STATE_COMPLETED = "completed"
STATE_RETRY_SCHEDULED = "retry_scheduled"
STATE_FAILED_RETRYABLE = "failed_retryable"
STATE_FAILED_TERMINAL = "failed_terminal"
STATE_DEAD_LETTER = "dead_letter"
STATE_CANCELLED = "cancelled"
STATE_AWAITING_REVIEW = "awaiting_review"
STATE_APPROVED_FOR_PUBLISH = "approved_for_publish"
STATE_REJECTED_MANUAL_REVIEW = "rejected_manual_review"

TERMINAL_STATES = {
    STATE_COMPLETED,
    STATE_FAILED_TERMINAL,
    STATE_DEAD_LETTER,
    STATE_CANCELLED,
    STATE_REJECTED_MANUAL_REVIEW,
}

BLOCKED_STATES = {
    STATE_BLOCKED_MANUAL_PREREQ,
    STATE_BLOCKED_CONFIG_ERROR,
    STATE_AWAITING_REVIEW,
}

READY_STATES = {
    STATE_QUEUED,
    STATE_RETRY_SCHEDULED,
    STATE_APPROVED_FOR_PUBLISH,
}
