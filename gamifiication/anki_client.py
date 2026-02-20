from __future__ import annotations

from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - import guard for lean test environments
    requests = None  # type: ignore[assignment]


class AnkiConnectError(RuntimeError):
    """Raised for AnkiConnect transport or protocol errors."""


class AnkiClient:
    def __init__(self, endpoint: str, *, timeout_seconds: int = 20):
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        if requests is None:
            raise AnkiConnectError(
                "The 'requests' package is required for AnkiConnect calls. Install project dependencies."
            )

        payload: dict[str, Any] = {"action": action, "version": 6}
        if params:
            payload["params"] = params

        try:
            response = requests.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:  # pragma: no cover - network failures are environment dependent
            raise AnkiConnectError(f"Failed to reach AnkiConnect at {self.endpoint}: {exc}") from exc
        except ValueError as exc:
            raise AnkiConnectError("AnkiConnect returned non-JSON data.") from exc

        if "error" not in data or "result" not in data:
            raise AnkiConnectError("AnkiConnect response is missing required fields.")
        if data["error"] is not None:
            raise AnkiConnectError(str(data["error"]))
        return data["result"]

    def get_num_cards_reviewed_today(self) -> int:
        result = self.invoke("getNumCardsReviewedToday")
        if not isinstance(result, int):
            raise AnkiConnectError("AnkiConnect returned a non-integer review count.")
        return result

    def add_notes(self, notes: list[dict[str, Any]]) -> list[int | None]:
        result = self.invoke("addNotes", {"notes": notes})
        if not isinstance(result, list):
            raise AnkiConnectError("AnkiConnect addNotes returned an invalid payload.")

        normalized: list[int | None] = []
        for note_id in result:
            if note_id is None:
                normalized.append(None)
                continue
            if isinstance(note_id, int):
                normalized.append(note_id)
                continue
            raise AnkiConnectError("AnkiConnect addNotes returned a non-integer note id.")
        return normalized

    def find_cards(self, query: str) -> list[int]:
        result = self.invoke("findCards", {"query": query})
        if not isinstance(result, list):
            raise AnkiConnectError("AnkiConnect findCards returned an invalid payload.")
        card_ids: list[int] = []
        for card_id in result:
            if not isinstance(card_id, int):
                raise AnkiConnectError("AnkiConnect findCards returned a non-integer card id.")
            card_ids.append(card_id)
        return card_ids
