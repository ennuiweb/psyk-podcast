"""Shared constants for Spotify transcript tooling."""

from __future__ import annotations

APP_NAME = "spotify-transcripts"
MANIFEST_VERSION = 1
NORMALIZED_TRANSCRIPT_VERSION = 1
DEFAULT_TIMEOUT_MS = 30_000
SPOTIFY_WEB_URL = "https://open.spotify.com/"
TRANSCRIPT_URL_MARKERS = (
    "transcript-read-along",
    "episode-transcripts.spotifycdn.com",
)

STATUS_DOWNLOADED = "downloaded"
STATUS_MISSING_MAPPING = "missing_mapping"
STATUS_NO_TRANSCRIPT = "no_transcript_available"
STATUS_AUTH_REQUIRED = "auth_required"
STATUS_PLAYBACK_REQUIRED = "playback_required"
STATUS_MARKET_RESTRICTED = "market_restricted"
STATUS_SCHEMA_CHANGED = "schema_changed"
STATUS_NETWORK_ERROR = "network_error"
STATUS_UNKNOWN_FAILURE = "unknown_failure"

TERMINAL_STATUSES = {
    STATUS_DOWNLOADED,
    STATUS_MISSING_MAPPING,
    STATUS_NO_TRANSCRIPT,
    STATUS_AUTH_REQUIRED,
    STATUS_PLAYBACK_REQUIRED,
    STATUS_MARKET_RESTRICTED,
    STATUS_SCHEMA_CHANGED,
    STATUS_NETWORK_ERROR,
    STATUS_UNKNOWN_FAILURE,
}
