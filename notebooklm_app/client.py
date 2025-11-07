"""NotebookLM API client."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

from google.auth.transport.requests import AuthorizedSession

from .auth import build_session
from .config import ResolvedShowConfig
from .http import HttpError, request_json

logger = logging.getLogger(__name__)


class NotebookLMError(RuntimeError):
    """Base error raised for NotebookLM client failures."""


READY_STATUSES = {
    "AUDIO_OVERVIEW_STATUS_READY",
}
FAILED_STATUSES = {
    "AUDIO_OVERVIEW_STATUS_FAILED",
    "AUDIO_OVERVIEW_STATUS_ERROR",
}

@dataclass(slots=True)
class NotebookLMClient:
    config: ResolvedShowConfig
    session: AuthorizedSession = field(init=False)

    def __post_init__(self) -> None:
        self.session = build_session(self.config.service_account_file)

    # URLs -----------------------------------------------------------------
    def _overview_collection_url(self) -> str:
        return f"{self.config.endpoint}/v1alpha/{self.config.notebooks_base}/{self.config.notebook_id}/audioOverviews"

    def _overview_resource_url(self, overview_id: str = "default") -> str:
        return f"{self._overview_collection_url()}/{overview_id}"

    # Operations -----------------------------------------------------------
    def create_audio_overview(
        self,
        *,
        source_ids: Optional[Iterable[str]] = None,
        episode_focus: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if source_ids:
            payload["sourceIds"] = [{"id": sid} for sid in source_ids]
        if episode_focus:
            payload["episodeFocus"] = episode_focus
        payload["languageCode"] = language_code or self.config.language_code
        url = self._overview_collection_url()
        logger.info("Creating audio overview for %s", self.config.name)
        return self._request("POST", url, json=payload)

    def get_audio_overview(self, overview_id: str = "default") -> Dict[str, Any]:
        url = self._overview_resource_url(overview_id)
        return self._request("GET", url)

    def delete_audio_overview(self, overview_id: str = "default") -> Dict[str, Any]:
        url = self._overview_resource_url(overview_id)
        return self._request("DELETE", url, expected_status={200, 204})

    def wait_for_ready(
        self,
        *,
        overview_id: str = "default",
        poll_interval: int = 30,
        timeout: int = 900,
    ) -> Dict[str, Any]:
        start = time.monotonic()
        while True:
            payload = self.get_audio_overview(overview_id)
            status = (
                payload.get("audioOverview", {})
                .get("status")
                or payload.get("status")
            )
            name = payload.get("audioOverview", {}).get("audioOverviewId") or overview_id
            logger.info("Audio overview %s status: %s", name, status)
            if status in READY_STATUSES:
                return payload
            if status in FAILED_STATUSES or (isinstance(status, str) and "FAILED" in status):
                raise NotebookLMError(f"Audio overview failed with status '{status}': {payload}")
            if time.monotonic() - start > timeout:
                raise NotebookLMError(f"Timed out waiting for audio overview '{name}' to be ready.")
            time.sleep(poll_interval)

    @staticmethod
    def extract_audio_uri(payload: Mapping[str, Any]) -> Optional[str]:
        overview = payload.get("audioOverview")
        if isinstance(overview, Mapping):
            return overview.get("audioUri") or overview.get("downloadUri")
        return None

    def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            return request_json(self.session, method, url, **kwargs)
        except HttpError as exc:
            raise NotebookLMError(str(exc)) from exc
