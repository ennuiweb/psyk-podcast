from __future__ import annotations

import os
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - import guard for lean test environments
    requests = None  # type: ignore[assignment]


class HabiticaError(RuntimeError):
    """Raised for Habitica API errors."""


class HabiticaClient:
    def __init__(
        self,
        *,
        api_base: str,
        user_id: str,
        api_token: str,
        timeout_seconds: int = 20,
    ):
        self.api_base = api_base.rstrip("/")
        self.user_id = user_id
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(
        cls,
        *,
        api_base: str,
        user_id_env: str,
        api_token_env: str,
        timeout_seconds: int = 20,
    ) -> "HabiticaClient":
        user_id = os.getenv(user_id_env, "").strip()
        api_token = os.getenv(api_token_env, "").strip()
        if not user_id:
            raise HabiticaError(f"Missing Habitica credentials: env var {user_id_env} is empty.")
        if not api_token:
            raise HabiticaError(f"Missing Habitica credentials: env var {api_token_env} is empty.")
        return cls(
            api_base=api_base,
            user_id=user_id,
            api_token=api_token,
            timeout_seconds=timeout_seconds,
        )

    def score_task(self, task_id: str, direction: str) -> dict[str, Any]:
        if requests is None:
            raise HabiticaError(
                "The 'requests' package is required for Habitica API calls. Install project dependencies."
            )

        normalized_direction = direction.lower().strip()
        if normalized_direction not in {"up", "down"}:
            raise HabiticaError("Task score direction must be 'up' or 'down'.")

        url = f"{self.api_base}/tasks/{task_id}/score/{normalized_direction}"
        headers = {
            "x-api-user": self.user_id,
            "x-api-key": self.api_token,
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:  # pragma: no cover - network failures are environment dependent
            raise HabiticaError(f"Habitica request failed: {exc}") from exc
        except ValueError as exc:
            raise HabiticaError("Habitica returned non-JSON data.") from exc

        if not isinstance(payload, dict):
            raise HabiticaError("Habitica response payload is not an object.")

        if payload.get("success") is False:
            message = "Unknown Habitica API error"
            if isinstance(payload.get("message"), str) and payload["message"].strip():
                message = payload["message"].strip()
            raise HabiticaError(message)

        return payload
