"""Utilities for quiz files, mapping metadata, and progress calculations."""

from __future__ import annotations

import html
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone as dt_timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import QuizProgress
from .subject_services import load_subject_catalog, resolve_subject_paths

logger = logging.getLogger(__name__)

QUIZ_ID_RE = re.compile(r"^[0-9a-f]{8}$")
APP_DATA_RE = re.compile(r"<app-root[^>]*data-app-data=\"(?P<data>.*?)\"", re.IGNORECASE | re.DOTALL)
QUIZ_PATH_RE = re.compile(r"(?P<id>[0-9a-f]{8})\.html$", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
INLINE_PAREN_MATH_RE = re.compile(r"\\\((.+?)\\\)")
INLINE_DOLLAR_MATH_RE = re.compile(r"\$([^$\n]+)\$")
TEX_COMMAND_RE = re.compile(r"\\(?P<command>[A-Za-z]+)(?:\{(?P<braced>[^{}]*)\})?")

TEX_GREEK_COMMANDS = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "vartheta": "ϑ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "omicron": "ο",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "varsigma": "ς",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "varphi": "ϕ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
}
TEX_ACCENT_MARKS = {
    "acute": "\u0301",
    "grave": "\u0300",
    "ddot": "\u0308",
    "tilde": "\u0303",
    "bar": "\u0304",
    "breve": "\u0306",
    "check": "\u030c",
    "hat": "\u0302",
    "dot": "\u0307",
    "mathring": "\u030a",
}
TEX_GREEK_ACCENTED_BASES = {
    ("acute", "o"): "ό",
    ("acute", "O"): "Ό",
}


class StatePayloadError(ValueError):
    """Raised when a state payload does not match expected shape."""


@dataclass(frozen=True)
class QuizLabel:
    episode_title: str
    difficulty: str
    subject_slug: str | None


@dataclass(frozen=True)
class ProgressComputation:
    answers_count: int
    question_count: int
    status: str


@dataclass(frozen=True)
class CooldownStatus:
    is_blocked: bool
    retry_after_seconds: int
    available_at: str | None
    streak_count: int
    next_cooldown_seconds: int


@dataclass(frozen=True)
class QuizOutcome:
    question_count: int
    answered_count: int
    correct_answers: int
    wrong_answers: int
    skipped_answers: int


_METADATA_CACHE: dict[str, Any] = {"mtime": None, "signature": None, "data": {}}
MAX_SPEED_BONUS_SECONDS_PER_QUESTION = 10


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _quiz_subject_slug(quiz_id: str) -> str:
    label = load_quiz_label_mapping().get(str(quiz_id or "").strip().lower())
    candidate = str(label.subject_slug or "").strip().lower() if label else ""
    if not SUBJECT_SLUG_RE.match(candidate):
        return ""
    return candidate


def _all_known_quiz_roots() -> list[Path]:
    roots: list[Path] = [Path(settings.QUIZ_FILES_ROOT)]
    catalog = load_subject_catalog()
    for subject in catalog.active_subjects:
        roots.append(resolve_subject_paths(subject.slug).quiz_files_root)
    return _dedupe_paths(roots)


def _candidate_quiz_roots(quiz_id: str) -> list[Path]:
    quiz_id_normalized = str(quiz_id or "").strip().lower()
    roots: list[Path] = []
    subject_slug = _quiz_subject_slug(quiz_id_normalized)
    default_root = Path(settings.QUIZ_FILES_ROOT)
    if subject_slug:
        subject_root = resolve_subject_paths(subject_slug).quiz_files_root
        roots.append(subject_root)
        # Backward-compatible fallback for deployments that use a shared quiz root.
        roots.append(default_root / subject_slug)
    roots.extend(_all_known_quiz_roots())
    return _dedupe_paths(roots)


def _candidate_quiz_file_paths(quiz_id: str, *, suffix: str) -> list[Path]:
    quiz_id_normalized = str(quiz_id or "").strip().lower()
    return [
        root / f"{quiz_id_normalized}.{suffix}"
        for root in _candidate_quiz_roots(quiz_id_normalized)
    ]


def _first_existing_quiz_file(quiz_id: str, *, suffix: str) -> Path | None:
    for path in _candidate_quiz_file_paths(quiz_id, suffix=suffix):
        if _path_is_file(path):
            return path
    return None


def quiz_html_file_path(quiz_id: str) -> Path:
    existing = _first_existing_quiz_file(quiz_id, suffix="html")
    if existing is not None:
        return existing
    candidates = _candidate_quiz_file_paths(quiz_id, suffix="html")
    return candidates[0] if candidates else Path(settings.QUIZ_FILES_ROOT) / f"{quiz_id}.html"


def quiz_json_file_path(quiz_id: str) -> Path:
    existing = _first_existing_quiz_file(quiz_id, suffix="json")
    if existing is not None:
        return existing
    candidates = _candidate_quiz_file_paths(quiz_id, suffix="json")
    return candidates[0] if candidates else Path(settings.QUIZ_FILES_ROOT) / f"{quiz_id}.json"


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
    return (
        _first_existing_quiz_file(quiz_id, suffix="json") is not None
        or _first_existing_quiz_file(quiz_id, suffix="html") is not None
    )


def read_quiz_bytes(quiz_id: str) -> bytes:
    html_path = _first_existing_quiz_file(quiz_id, suffix="html") or quiz_html_file_path(quiz_id)
    return html_path.read_bytes()


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


def _normalize_tex_command(match: re.Match[str]) -> str:
    command = match.group("command")
    braced = match.group("braced")
    if command in TEX_GREEK_COMMANDS and braced is None:
        return TEX_GREEK_COMMANDS[command]
    if command in TEX_ACCENT_MARKS and braced is not None:
        base = normalize_quiz_copy(braced)
        if (command, base) in TEX_GREEK_ACCENTED_BASES:
            return TEX_GREEK_ACCENTED_BASES[(command, base)]
        if len(base) == 1:
            return unicodedata.normalize("NFC", f"{base}{TEX_ACCENT_MARKS[command]}")
    return match.group(0)


def normalize_quiz_copy(raw_value: Any) -> str:
    text = str(raw_value or "")
    text = UNICODE_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), text)
    text = INLINE_PAREN_MATH_RE.sub(r"\1", text)
    text = INLINE_DOLLAR_MATH_RE.sub(r"\1", text)
    text = TEX_COMMAND_RE.sub(_normalize_tex_command, text)
    text = text.replace("\\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_answer_option(option: Any) -> Any:
    if not isinstance(option, dict):
        return option
    normalized = dict(option)
    for key in ("text", "rationale"):
        if key in normalized:
            normalized[key] = normalize_quiz_copy(normalized[key])
    return normalized


def _normalize_question_entry(question: Any) -> Any:
    if not isinstance(question, dict):
        return question
    normalized = dict(question)
    for key in ("question", "hint"):
        if key in normalized:
            normalized[key] = normalize_quiz_copy(normalized[key])
    options = normalized.get("answerOptions")
    if isinstance(options, list):
        normalized["answerOptions"] = [_normalize_answer_option(option) for option in options]
    return normalized


def normalize_quiz_questions(questions: list[Any]) -> list[Any]:
    return [_normalize_question_entry(question) for question in questions]


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
                return {"title": title, "questions": normalize_quiz_questions(questions)}

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
    return {"title": "Quiz", "questions": normalize_quiz_questions(questions)}


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

    timed_out_raw = raw_payload.get("timedOutQuestionIndices", [])
    if timed_out_raw is None:
        timed_out_raw = []
    if not isinstance(timed_out_raw, list):
        raise StatePayloadError("timedOutQuestionIndices skal være en liste.")
    timed_out_indices: list[int] = []
    for item in timed_out_raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise StatePayloadError("timedOutQuestionIndices-elementer skal være heltal.")
        timed_out_indices.append(item)

    deadlines_raw = raw_payload.get("questionDeadlineEpochMs", {})
    if deadlines_raw is None:
        deadlines_raw = {}
    if not isinstance(deadlines_raw, dict):
        raise StatePayloadError("questionDeadlineEpochMs skal være et objekt.")
    deadlines: dict[str, int] = {}
    for raw_key, raw_value in deadlines_raw.items():
        key_str = str(raw_key).strip()
        if len(key_str) > 64:
            raise StatePayloadError("questionDeadlineEpochMs indeholder en for lang nøgle.")
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise StatePayloadError("questionDeadlineEpochMs-værdier skal være heltal.")
        if raw_value < 0:
            raise StatePayloadError("questionDeadlineEpochMs-værdier skal være nul eller positive.")
        deadlines[key_str] = raw_value

    return {
        "userAnswers": user_answers,
        "currentQuestionIndex": current_question_index,
        "hiddenQuestionIndices": hidden_indices,
        "currentView": current_view,
        "timedOutQuestionIndices": timed_out_indices,
        "questionDeadlineEpochMs": deadlines,
    }


def _coerce_answered_index_map(raw_user_answers: Any) -> dict[str, int]:
    if not isinstance(raw_user_answers, dict):
        return {}
    answered: dict[str, int] = {}
    for key, value in raw_user_answers.items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        answered[str(key)] = value
    return answered


def _coerce_timed_out_index_set(raw_timed_out: Any) -> set[int]:
    if not isinstance(raw_timed_out, list):
        return set()
    return {
        int(index)
        for index in raw_timed_out
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0
    }


def lock_answered_questions_in_state(
    *,
    previous_state_payload: dict[str, Any] | None,
    state_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(previous_state_payload, dict):
        return state_payload

    previous_answers = _coerce_answered_index_map(previous_state_payload.get("userAnswers"))
    previous_timed_out = _coerce_timed_out_index_set(previous_state_payload.get("timedOutQuestionIndices"))
    if not previous_answers and not previous_timed_out:
        return state_payload

    merged = dict(state_payload)
    incoming_answers = dict(state_payload.get("userAnswers") or {})
    incoming_timed_out = _coerce_timed_out_index_set(state_payload.get("timedOutQuestionIndices"))

    for key, selected in previous_answers.items():
        incoming_answers[key] = selected

    for index in previous_timed_out:
        incoming_timed_out.add(index)
        key = str(index)
        if key not in incoming_answers:
            incoming_answers[key] = None

    merged["userAnswers"] = incoming_answers
    merged["timedOutQuestionIndices"] = sorted(incoming_timed_out)
    return merged


def compute_progress(state_payload: dict[str, Any], question_count: int) -> ProgressComputation:
    user_answers = state_payload.get("userAnswers", {})
    answered_keys = {str(key) for key, value in user_answers.items() if value is not None}
    timed_out_indices = state_payload.get("timedOutQuestionIndices", [])
    timed_out_keys = {
        str(index)
        for index in timed_out_indices
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0
    }
    answers_count = len(answered_keys.union(timed_out_keys))
    current_view = str(state_payload.get("currentView", "question"))

    status = QuizProgress.Status.IN_PROGRESS
    if current_view == "summary" and question_count > 0 and answers_count == question_count:
        status = QuizProgress.Status.COMPLETED

    return ProgressComputation(
        answers_count=answers_count,
        question_count=question_count,
        status=status,
    )


def _question_time_limit_seconds() -> int:
    value = int(getattr(settings, "FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS", 30))
    return max(5, value)


def _retry_reset_seconds() -> int:
    value = int(getattr(settings, "FREUDD_QUIZ_RETRY_COOLDOWN_RESET_SECONDS", 3600))
    return max(60, value)


def question_time_limit_seconds() -> int:
    return _question_time_limit_seconds()


def current_leaderboard_semester_key(*, now: datetime | None = None) -> str:
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, dt_timezone.utc)
    current = current.astimezone(dt_timezone.utc)
    half = "H1" if current.month <= 6 else "H2"
    return f"{current.year}-{half}"


def cooldown_seconds_for_streak(streak_count: int) -> int:
    streak = max(1, int(streak_count))
    if streak <= 2:
        return 60
    if streak <= 5:
        return 300
    return 600


def maybe_reset_retry_streak(progress: QuizProgress, *, now: datetime | None = None) -> bool:
    current = now or timezone.now()
    last_completed = progress.last_attempt_completed_at
    if last_completed is None:
        return False
    elapsed_seconds = (current - last_completed).total_seconds()
    if elapsed_seconds < _retry_reset_seconds():
        return False

    changed = False
    if int(progress.retry_streak_count or 0) != 0:
        progress.retry_streak_count = 0
        changed = True
    if progress.retry_cooldown_until_at is not None:
        progress.retry_cooldown_until_at = None
        changed = True
    return changed


def build_cooldown_status(progress: QuizProgress, *, now: datetime | None = None) -> CooldownStatus:
    current = now or timezone.now()
    streak_count = max(0, int(progress.retry_streak_count or 0))
    cooldown_until = progress.retry_cooldown_until_at
    is_blocked = bool(cooldown_until and cooldown_until > current)
    retry_after = 0
    if is_blocked and cooldown_until:
        retry_after = max(1, int((cooldown_until - current).total_seconds()))

    return CooldownStatus(
        is_blocked=is_blocked,
        retry_after_seconds=retry_after,
        available_at=cooldown_until.isoformat() if cooldown_until else None,
        streak_count=streak_count,
        next_cooldown_seconds=cooldown_seconds_for_streak(streak_count + 1),
    )


def apply_completion_cooldown(progress: QuizProgress, *, now: datetime | None = None) -> CooldownStatus:
    current = now or timezone.now()
    streak_count = max(0, int(progress.retry_streak_count or 0)) + 1
    cooldown_seconds = cooldown_seconds_for_streak(streak_count)
    progress.retry_streak_count = streak_count
    progress.last_attempt_completed_at = current
    progress.retry_cooldown_until_at = current + timedelta(seconds=cooldown_seconds)
    return build_cooldown_status(progress, now=current)


def compute_attempt_duration_ms(progress: QuizProgress, *, now: datetime | None = None) -> int:
    current = now or timezone.now()
    started_at = progress.attempt_started_at or progress.first_seen_at or current
    duration_ms = int((current - started_at).total_seconds() * 1000)
    return max(1_000, duration_ms)


def compute_quiz_outcome(*, state_payload: dict[str, Any], quiz_payload: dict[str, Any] | None) -> QuizOutcome:
    questions = _extract_question_entries(quiz_payload)
    question_count = len(questions)
    raw_answers = state_payload.get("userAnswers", {})
    user_answers = raw_answers if isinstance(raw_answers, dict) else {}
    timed_out = {
        int(index)
        for index in state_payload.get("timedOutQuestionIndices", [])
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0
    }

    correct_answers = 0
    wrong_answers = 0
    skipped_answers = 0
    answered_count = 0

    for index in range(question_count):
        if index in timed_out:
            answered_count += 1
            wrong_answers += 1
            continue

        selected = user_answers.get(str(index))
        if selected is None:
            skipped_answers += 1
            continue
        if isinstance(selected, bool) or not isinstance(selected, int):
            skipped_answers += 1
            continue

        question = questions[index] if index < len(questions) else None
        options = question.get("answerOptions") if isinstance(question, dict) else None
        if not isinstance(options, list) or selected < 0 or selected >= len(options):
            skipped_answers += 1
            continue

        answered_count += 1
        option = options[selected]
        if isinstance(option, dict) and option.get("isCorrect") is True:
            correct_answers += 1
        else:
            wrong_answers += 1

    return QuizOutcome(
        question_count=question_count,
        answered_count=answered_count,
        correct_answers=correct_answers,
        wrong_answers=wrong_answers,
        skipped_answers=skipped_answers,
    )


def compute_leaderboard_score(
    *,
    correct_answers: int,
    question_count: int,
    duration_ms: int,
    question_time_limit_seconds: int | None = None,
) -> int:
    correct = max(0, int(correct_answers))
    total = max(0, int(question_count))
    duration = max(1_000, int(duration_ms))
    limit_seconds = max(5, int(question_time_limit_seconds or _question_time_limit_seconds()))
    speed_bonus_window_seconds = min(limit_seconds, MAX_SPEED_BONUS_SECONDS_PER_QUESTION)
    expected_ms = max(1, total) * speed_bonus_window_seconds * 1_000
    speed_factor = max(0.0, min(1.0, expected_ms / duration))
    speed_bonus = round(correct * 20 * speed_factor)
    return max(0, int(correct * 100 + speed_bonus))


def update_leaderboard_best(
    *,
    progress: QuizProgress,
    semester_key: str,
    reached_at: datetime,
    score_points: int,
    correct_answers: int,
    question_count: int,
    duration_ms: int,
) -> None:
    target_semester = str(semester_key or "").strip()
    if progress.leaderboard_semester_key != target_semester:
        progress.leaderboard_semester_key = target_semester
        progress.leaderboard_best_score = 0
        progress.leaderboard_best_correct_answers = 0
        progress.leaderboard_best_question_count = 0
        progress.leaderboard_best_duration_ms = 0
        progress.leaderboard_best_reached_at = None

    best_score = int(progress.leaderboard_best_score or 0)
    best_correct = int(progress.leaderboard_best_correct_answers or 0)
    best_duration = int(progress.leaderboard_best_duration_ms or 0)

    has_no_entry = progress.leaderboard_best_reached_at is None
    is_better = False
    if has_no_entry:
        is_better = True
    elif score_points > best_score:
        is_better = True
    elif score_points == best_score and correct_answers > best_correct:
        is_better = True
    elif score_points == best_score and correct_answers == best_correct:
        if best_duration <= 0 or duration_ms < best_duration:
            is_better = True

    if not is_better:
        return

    progress.leaderboard_best_score = max(0, int(score_points))
    progress.leaderboard_best_correct_answers = max(0, int(correct_answers))
    progress.leaderboard_best_question_count = max(0, int(question_count))
    progress.leaderboard_best_duration_ms = max(0, int(duration_ms))
    progress.leaderboard_best_reached_at = reached_at


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


def _normalize_subject_slug(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    slug = value.strip().lower()
    if not slug:
        return None
    if not SUBJECT_SLUG_RE.match(slug):
        return None
    return slug


def _quiz_links_candidate_paths() -> list[Path]:
    paths: list[Path] = [Path(settings.QUIZ_LINKS_JSON_PATH)]
    catalog = load_subject_catalog()
    for subject in catalog.active_subjects:
        paths.append(resolve_subject_paths(subject.slug).quiz_links_path)
    return _dedupe_paths(paths)


def _quiz_links_signature(paths: list[Path]) -> tuple[tuple[str, int | None], ...]:
    signature: list[tuple[str, int | None]] = []
    for path in paths:
        mtime: int | None = None
        try:
            if path.exists():
                mtime = path.stat().st_mtime_ns
        except OSError:
            logger.warning("Unable to read stat for quiz_links path: %s", path, exc_info=True)
        signature.append((str(path), mtime))
    return tuple(signature)


def _set_quiz_label_if_not_conflicting(
    labels: dict[str, QuizLabel],
    *,
    quiz_id: str,
    candidate: QuizLabel,
    source_path: Path,
) -> None:
    existing = labels.get(quiz_id)
    if existing is None:
        labels[quiz_id] = candidate
        return
    if existing == candidate:
        return
    if (
        existing.episode_title == candidate.episode_title
        and existing.difficulty == candidate.difficulty
        and existing.subject_slug is None
        and candidate.subject_slug is not None
    ):
        labels[quiz_id] = candidate
        return
    logger.warning(
        "Conflicting quiz label mapping for %s in %s; keeping first mapping.",
        quiz_id,
        source_path,
    )


def load_quiz_label_mapping() -> dict[str, QuizLabel]:
    paths = _quiz_links_candidate_paths()
    signature = _quiz_links_signature(paths)
    if _METADATA_CACHE.get("signature") == signature:
        return _METADATA_CACHE.get("data", {})

    labels: dict[str, QuizLabel] = {}
    latest_mtime: int | None = None
    for path in paths:
        if not path.exists():
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Unable to parse quiz links file: %s", path, exc_info=True)
            continue

        try:
            path_mtime = path.stat().st_mtime_ns
        except OSError:
            path_mtime = None
        if path_mtime is not None:
            latest_mtime = path_mtime if latest_mtime is None else max(latest_mtime, path_mtime)

        by_name = payload.get("by_name") if isinstance(payload, dict) else None
        if not isinstance(by_name, dict):
            continue

        for episode_title, entry in by_name.items():
            if not isinstance(entry, dict):
                continue
            subject_slug = _normalize_subject_slug(entry.get("subject_slug"))
            if entry.get("subject_slug") is not None and subject_slug is None:
                logger.warning("Invalid subject_slug in quiz links for entry: %s", episode_title)

            primary_id = _quiz_id_from_relative_path(entry.get("relative_path"))
            if primary_id:
                _set_quiz_label_if_not_conflicting(
                    labels,
                    quiz_id=primary_id,
                    candidate=QuizLabel(
                        episode_title=str(episode_title),
                        difficulty=_normalize_difficulty(entry.get("difficulty")),
                        subject_slug=subject_slug,
                    ),
                    source_path=path,
                )

            links = entry.get("links")
            if isinstance(links, list):
                fallback_subject_slug: str | None = None
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_subject_slug = _normalize_subject_slug(link.get("subject_slug"))
                    if link_subject_slug and fallback_subject_slug is None:
                        fallback_subject_slug = link_subject_slug
                    quiz_id = _quiz_id_from_relative_path(link.get("relative_path"))
                    if quiz_id:
                        _set_quiz_label_if_not_conflicting(
                            labels,
                            quiz_id=quiz_id,
                            candidate=QuizLabel(
                                episode_title=str(episode_title),
                                difficulty=_normalize_difficulty(link.get("difficulty")),
                                subject_slug=subject_slug or link_subject_slug,
                            ),
                            source_path=path,
                        )
                if subject_slug is None and fallback_subject_slug is not None and primary_id and primary_id in labels:
                    labels[primary_id] = QuizLabel(
                        episode_title=labels[primary_id].episode_title,
                        difficulty=labels[primary_id].difficulty,
                        subject_slug=fallback_subject_slug,
                    )
                if subject_slug is None and fallback_subject_slug is None:
                    logger.warning("Missing subject_slug in quiz links for entry: %s", episode_title)
            elif subject_slug is None:
                logger.warning("Missing subject_slug in quiz links for entry: %s", episode_title)

    _METADATA_CACHE["mtime"] = latest_mtime
    _METADATA_CACHE["signature"] = signature
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
