"""Utilities for quiz files, mapping metadata, and progress calculations."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import QuizProgress

logger = logging.getLogger(__name__)

QUIZ_ID_RE = re.compile(r"^[0-9a-f]{8}$")
APP_DATA_RE = re.compile(r"<app-root[^>]*data-app-data=\"(?P<data>.*?)\"", re.IGNORECASE | re.DOTALL)
QUIZ_PATH_RE = re.compile(r"(?P<id>[0-9a-f]{8})\.html$", re.IGNORECASE)


class StatePayloadError(ValueError):
    """Raised when a state payload does not match expected shape."""


@dataclass(frozen=True)
class QuizLabel:
    episode_title: str
    difficulty: str


@dataclass(frozen=True)
class ProgressComputation:
    answers_count: int
    question_count: int
    status: str


_METADATA_CACHE: dict[str, Any] = {"mtime": None, "data": {}}


def quiz_html_file_path(quiz_id: str) -> Path:
    return Path(settings.QUIZ_FILES_ROOT) / f"{quiz_id}.html"


def quiz_json_file_path(quiz_id: str) -> Path:
    return Path(settings.QUIZ_FILES_ROOT) / f"{quiz_id}.json"


def quiz_file_path(quiz_id: str) -> Path:
    """Backward-compatible alias used by legacy raw HTML route."""
    return quiz_html_file_path(quiz_id)


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        logger.warning("Unable to stat quiz file: %s", path, exc_info=True)
        return False


def quiz_exists(quiz_id: str) -> bool:
    return _path_is_file(quiz_json_file_path(quiz_id)) or _path_is_file(quiz_html_file_path(quiz_id))


def read_quiz_bytes(quiz_id: str) -> bytes:
    return quiz_html_file_path(quiz_id).read_bytes()


def _extract_question_entries(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list):
            return questions
        quiz_entries = payload.get("quiz")
        if isinstance(quiz_entries, list):
            return quiz_entries
    if isinstance(payload, list):
        return payload
    return []


def parse_question_count_from_quiz_bytes(quiz_bytes: bytes) -> int:
    text = quiz_bytes.decode("utf-8", errors="replace")
    match = APP_DATA_RE.search(text)
    if not match:
        return 0
    payload = html.unescape(match.group("data"))
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Failed to decode data-app-data payload", exc_info=True)
        return 0
    return len(_extract_question_entries(decoded))


def parse_question_count_from_quiz_json(payload: Any) -> int:
    return len(_extract_question_entries(payload))


def load_quiz_content(quiz_id: str) -> dict[str, Any] | None:
    json_path = quiz_json_file_path(quiz_id)
    if _path_is_file(json_path):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Unable to parse quiz JSON file: %s", json_path, exc_info=True)
        else:
            questions = _extract_question_entries(payload)
            if questions:
                title = "Quiz"
                if isinstance(payload, dict):
                    raw_title = payload.get("title")
                    if isinstance(raw_title, str) and raw_title.strip():
                        title = raw_title.strip()
                return {"title": title, "questions": questions}

    html_path = quiz_html_file_path(quiz_id)
    if not _path_is_file(html_path):
        return None
    try:
        html_bytes = html_path.read_bytes()
    except OSError:
        logger.warning("Unable to read quiz HTML file: %s", html_path, exc_info=True)
        return None

    text = html_bytes.decode("utf-8", errors="replace")
    match = APP_DATA_RE.search(text)
    if not match:
        return None

    raw_payload = html.unescape(match.group("data"))
    try:
        decoded_payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Failed to decode data-app-data payload for quiz: %s", quiz_id, exc_info=True)
        return None

    questions = _extract_question_entries(decoded_payload)
    if not questions:
        return None
    return {"title": "Quiz", "questions": questions}


def quiz_question_count(quiz_id: str) -> int:
    json_path = quiz_json_file_path(quiz_id)
    if _path_is_file(json_path):
        try:
            json_payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Unable to parse quiz JSON for question count: %s", json_path, exc_info=True)
        else:
            return parse_question_count_from_quiz_json(json_payload)

    html_path = quiz_html_file_path(quiz_id)
    if not _path_is_file(html_path):
        return 0
    try:
        return parse_question_count_from_quiz_bytes(html_path.read_bytes())
    except OSError:
        logger.warning("Unable to read quiz file for question count: %s", html_path, exc_info=True)
        return 0


def normalize_state_payload(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise StatePayloadError("State-payload skal være et JSON-objekt.")

    required_keys = ("userAnswers", "currentQuestionIndex", "hiddenQuestionIndices", "currentView")
    missing = [key for key in required_keys if key not in raw_payload]
    if missing:
        missing_str = ", ".join(missing)
        raise StatePayloadError(f"State-payload mangler obligatoriske nøgler: {missing_str}.")

    raw_user_answers = raw_payload.get("userAnswers", {})
    if not isinstance(raw_user_answers, dict):
        raise StatePayloadError("userAnswers skal være et objekt.")

    user_answers: dict[str, Any] = {}
    for key, value in raw_user_answers.items():
        key_str = str(key)
        if len(key_str) > 64:
            raise StatePayloadError("userAnswers indeholder en for lang nøgle.")
        user_answers[key_str] = value

    current_question_index = raw_payload.get("currentQuestionIndex", 0)
    if isinstance(current_question_index, bool) or not isinstance(current_question_index, int):
        raise StatePayloadError("currentQuestionIndex skal være et heltal.")

    hidden_indices_raw = raw_payload.get("hiddenQuestionIndices", [])
    if not isinstance(hidden_indices_raw, list):
        raise StatePayloadError("hiddenQuestionIndices skal være en liste.")

    hidden_indices: list[int] = []
    for item in hidden_indices_raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise StatePayloadError("hiddenQuestionIndices-elementer skal være heltal.")
        hidden_indices.append(item)

    current_view = raw_payload.get("currentView", "question")
    if not isinstance(current_view, str):
        raise StatePayloadError("currentView skal være en streng.")
    current_view = current_view.strip() or "question"
    if len(current_view) > 32:
        raise StatePayloadError("currentView er for lang.")

    return {
        "userAnswers": user_answers,
        "currentQuestionIndex": current_question_index,
        "hiddenQuestionIndices": hidden_indices,
        "currentView": current_view,
    }


def compute_progress(state_payload: dict[str, Any], question_count: int) -> ProgressComputation:
    user_answers = state_payload.get("userAnswers", {})
    answers_count = sum(1 for _, value in user_answers.items() if value is not None)
    current_view = str(state_payload.get("currentView", "question"))

    status = QuizProgress.Status.IN_PROGRESS
    if current_view == "summary" and question_count > 0 and answers_count == question_count:
        status = QuizProgress.Status.COMPLETED

    return ProgressComputation(
        answers_count=answers_count,
        question_count=question_count,
        status=status,
    )


def _quiz_id_from_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = QUIZ_PATH_RE.search(value.strip())
    if not match:
        return None
    return match.group("id").lower()


def _normalize_difficulty(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "medium"
    return value.strip().lower()


def load_quiz_label_mapping() -> dict[str, QuizLabel]:
    path = Path(settings.QUIZ_LINKS_JSON_PATH)
    if not path.exists():
        return {}

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Unable to read stat for quiz_links path: %s", path, exc_info=True)
        return {}

    if _METADATA_CACHE.get("mtime") == mtime:
        return _METADATA_CACHE.get("data", {})

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unable to parse quiz links file: %s", path, exc_info=True)
        return {}

    labels: dict[str, QuizLabel] = {}
    by_name = payload.get("by_name") if isinstance(payload, dict) else None
    if isinstance(by_name, dict):
        for episode_title, entry in by_name.items():
            if not isinstance(entry, dict):
                continue

            primary_id = _quiz_id_from_relative_path(entry.get("relative_path"))
            if primary_id:
                labels[primary_id] = QuizLabel(
                    episode_title=str(episode_title),
                    difficulty=_normalize_difficulty(entry.get("difficulty")),
                )

            links = entry.get("links")
            if isinstance(links, list):
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    quiz_id = _quiz_id_from_relative_path(link.get("relative_path"))
                    if quiz_id:
                        labels[quiz_id] = QuizLabel(
                            episode_title=str(episode_title),
                            difficulty=_normalize_difficulty(link.get("difficulty")),
                        )

    _METADATA_CACHE["mtime"] = mtime
    _METADATA_CACHE["data"] = labels
    return labels


def upsert_progress_from_state(
    *,
    progress: QuizProgress,
    state_payload: dict[str, Any],
    computation: ProgressComputation,
) -> QuizProgress:
    progress.state_json = state_payload
    progress.answers_count = computation.answers_count
    progress.question_count = computation.question_count
    progress.last_view = str(state_payload.get("currentView", "question"))
    progress.status = computation.status

    if computation.status == QuizProgress.Status.COMPLETED and progress.completed_at is None:
        progress.completed_at = timezone.now()

    progress.save()
    return progress
