"""Authentication utilities for NotebookLM API access."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account


DEFAULT_SCOPES: Sequence[str] = (
    "https://www.googleapis.com/auth/cloud-platform",
)


def build_session(service_account_file: Path, scopes: Sequence[str] | None = None) -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(
        str(service_account_file),
        scopes=scopes or DEFAULT_SCOPES,
    )
    return AuthorizedSession(creds)

