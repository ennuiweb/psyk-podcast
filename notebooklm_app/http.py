"""HTTP helpers with lightweight retry/backoff."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, Optional

from requests import Response, Session

logger = logging.getLogger(__name__)


class HttpError(RuntimeError):
    """Raised when the API response is not successful."""

    def __init__(self, response: Response):
        self.response = response
        message = f"{response.status_code} {response.reason} for URL {response.url}"
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        super().__init__(f"{message}: {payload}")


def _should_retry(resp: Response) -> bool:
    if resp.status_code in (500, 502, 503, 504, 429):
        return True
    return False


def request_json(
    session: Session,
    method: str,
    url: str,
    *,
    expected_status: Iterable[int] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
    backoff: float = 1.5,
    **kwargs: Any,
) -> Dict[str, Any]:
    expected = set(expected_status or {200})
    for attempt in range(1, retries + 1):
        response = session.request(method=method, url=url, timeout=timeout, **kwargs)
        if response.status_code in expected:
            if response.content:
                return response.json()
            return {}
        if not _should_retry(response) or attempt == retries:
            raise HttpError(response)
        wait = backoff ** attempt
        logger.warning("Retrying %s %s after %s (attempt %s/%s)", method, url, response.status_code, attempt, retries)
        time.sleep(wait)
    raise RuntimeError("HTTP request exited retry loop unexpectedly.")
