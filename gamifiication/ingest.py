from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - import guard for lean test environments
    requests = None  # type: ignore[assignment]


class IngestError(RuntimeError):
    """Raised when ingestion or card extraction fails."""


CARD_PROMPT_TEMPLATE = (
    "Extract {count} key concepts from the text below as flashcards. "
    "Respond with JSON only. Format exactly: "
    "[{\"front\": \"concept\", \"back\": \"definition\"}]."
)


def read_source_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise IngestError(f"Input file does not exist: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ModuleNotFoundError as exc:
            raise IngestError(
                "PDF ingestion requires pypdf. Install it or provide a plain-text source file."
            ) from exc

        pages: list[str] = []
        reader = PdfReader(str(path))
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        text = "\n\n".join(pages).strip()
        if not text:
            raise IngestError("No extractable text found in PDF input.")
        return text

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise IngestError("Input text file is empty.")
    return text


def parse_cards_payload(payload_text: str) -> list[dict[str, str]]:
    candidate = payload_text.strip()
    if not candidate:
        raise IngestError("LLM response did not include any content.")

    if not candidate.startswith("["):
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise IngestError("LLM output was not valid JSON card data.") from exc

    if not isinstance(parsed, list) or not parsed:
        raise IngestError("LLM output must be a non-empty JSON array.")

    normalized_cards: list[dict[str, str]] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise IngestError(f"Card {index} is not a JSON object.")
        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        if not front or not back:
            raise IngestError(f"Card {index} must include non-empty 'front' and 'back'.")
        normalized_cards.append({"front": front, "back": back})

    return normalized_cards


def _extract_response_text(payload: dict[str, Any]) -> str:
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = payload.get("output")
    if not isinstance(output, list):
        raise IngestError("OpenAI response did not include output text.")

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"output_text", "text"}:
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    if chunks:
        return "\n".join(chunks)
    raise IngestError("OpenAI response did not include text content.")


def extract_cards_with_openai(
    *,
    text: str,
    api_key: str,
    model: str,
    max_cards: int,
    timeout_seconds: int = 60,
) -> list[dict[str, str]]:
    if requests is None:
        raise IngestError(
            "The 'requests' package is required for OpenAI extraction. Install project dependencies."
        )

    prompt = CARD_PROMPT_TEMPLATE.format(count=max_cards)
    body = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You generate concise flashcards and always return strict JSON.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{prompt}\n\nText:\n{text}",
                    }
                ],
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=body,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:  # pragma: no cover - network failures are environment dependent
        raise IngestError(f"OpenAI request failed: {exc}") from exc
    except ValueError as exc:
        raise IngestError("OpenAI response was not JSON.") from exc

    if not isinstance(payload, dict):
        raise IngestError("OpenAI response payload is invalid.")

    output_text = _extract_response_text(payload)
    cards = parse_cards_payload(output_text)
    return cards[:max_cards]


def extract_cards_with_mock(text: str, *, max_cards: int) -> list[dict[str, str]]:
    sentences = [
        item.strip()
        for item in re.split(r"[\n\.]+", text)
        if item and item.strip()
    ]
    cards: list[dict[str, str]] = []
    for index, sentence in enumerate(sentences[:max_cards], start=1):
        cards.append(
            {
                "front": f"Concept {index}: {sentence[:80]}",
                "back": f"Definition placeholder generated from source text segment {index}.",
            }
        )
    if not cards:
        raise IngestError("Mock extraction could not derive any cards from input text.")
    return cards


def build_anki_notes(
    *,
    cards: list[dict[str, str]],
    deck_name: str,
    note_model: str,
    front_field: str,
    back_field: str,
    tags: list[str],
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for card in cards:
        note = {
            "deckName": deck_name,
            "modelName": note_model,
            "fields": {
                front_field: card["front"],
                back_field: card["back"],
            },
            "tags": tags,
            "options": {"allowDuplicate": False},
        }
        notes.append(note)
    return notes
