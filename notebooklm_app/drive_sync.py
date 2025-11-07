"""Google Drive helpers for NotebookLM output."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Dict, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def _build_drive_service(service_account_file: Path):
    creds = service_account.Credentials.from_service_account_file(
        str(service_account_file),
        scopes=[DRIVE_SCOPE],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_audio_asset(
    *,
    service_account_file: Path,
    folder_id: str,
    local_path: Path,
    title: Optional[str] = None,
    mime_type: Optional[str] = None,
    share_public: bool = True,
) -> Dict[str, str]:
    service = _build_drive_service(service_account_file)
    target_mime = mime_type or _guess_mime(local_path)
    file_metadata = {
        "name": title or local_path.name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(str(local_path), mimetype=target_mime, resumable=False)
    logger.info("Uploading %s to Drive folder %s", local_path, folder_id)
    created = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id,name,webViewLink,webContentLink")
        .execute()
    )
    if share_public:
        service.permissions().create(
            fileId=created["id"],
            body={"role": "reader", "type": "anyone"},
            fields="id",
        ).execute()
    return created


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "audio/mpeg"

