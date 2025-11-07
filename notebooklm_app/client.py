"""NotebookLM Podcast API client."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Sequence

from google.auth.transport.requests import AuthorizedSession

from .auth import build_session
from .config import ContextConfig, ResolvedProfileConfig, render_context_payload
from .http import HttpError, request_json

logger = logging.getLogger(__name__)


class NotebookLMError(RuntimeError):
    """Base error raised for NotebookLM client failures."""


@dataclass(slots=True)
class NotebookLMClient:
    config: ResolvedProfileConfig
    session: AuthorizedSession = field(init=False)

    def __post_init__(self) -> None:
        self.session = build_session(self.config.service_account_file)

    # URLs -----------------------------------------------------------------
    def _podcast_collection_url(self) -> str:
        return f"{self.config.endpoint}/v1/{self.config.podcast_collection}"

    def _operation_url(self, operation_name: str) -> str:
        return f"{self.config.endpoint}/v1/{operation_name}"

    def _operation_download_url(self, operation_name: str) -> str:
        return f"{self._operation_url(operation_name)}:download?alt=media"

    # API calls ------------------------------------------------------------
    def create_podcast(
        self,
        *,
        focus: str | None,
        length: str,
        language_code: str,
        title: str | None,
        description: str | None,
        contexts: Sequence[ContextConfig],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "podcastConfig": {
                "focus": focus or "",
                "length": length,
                "languageCode": language_code,
            },
            "contexts": [render_context_payload(ctx) for ctx in contexts],
        }
        if title:
            payload["title"] = title
        if description:
            payload["description"] = description
        url = self._podcast_collection_url()
        logger.info("Creating podcast for profile %s", self.config.name)
        return self._request("POST", url, json=payload)

    def get_operation(self, operation_name: str) -> Dict[str, Any]:
        return self._request("GET", self._operation_url(operation_name))

    def wait_for_operation(
        self,
        operation_name: str,
        *,
        poll_interval: int = 30,
        timeout: int = 900,
    ) -> Dict[str, Any]:
        start = time.monotonic()
        while True:
            op = self.get_operation(operation_name)
            if op.get("done"):
                if "error" in op:
                    raise NotebookLMError(f"Podcast generation failed: {op['error']}")
                return op
            if time.monotonic() - start > timeout:
                raise NotebookLMError(f"Timed out waiting for operation '{operation_name}'.")
            logger.info("Operation %s still running; waiting %ss", operation_name, poll_interval)
            time.sleep(poll_interval)

    def download_operation_media(self, operation_name: str, destination: Path, chunk_size: int = 1024 * 1024) -> None:
        url = self._operation_download_url(operation_name)
        response = self.session.get(url, stream=True)
        if response.status_code != 200:
            raise NotebookLMError(f"Failed to download podcast ({response.status_code}): {response.text}")
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    handle.write(chunk)

    def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            return request_json(self.session, method, url, **kwargs)
        except HttpError as exc:
            raise NotebookLMError(str(exc)) from exc

