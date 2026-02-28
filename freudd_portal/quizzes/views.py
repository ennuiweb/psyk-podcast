"""Views for auth, quiz wrapper/raw access, subject dashboards, and state/progress APIs."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import SignupForm
from .gamification_services import (
    get_gamification_snapshot,
    get_subject_learning_path_snapshot,
    record_quiz_progress_delta,
)
from .leaderboard_services import (
    active_half_year_season,
    build_subject_leaderboard_snapshot,
    get_profile_payload,
    update_leaderboard_profile,
)
from .models import (
    QuizProgress,
    SubjectEnrollment,
    UserPodcastMark,
    UserReadingMark,
    UserSubjectLastLecture,
)
from .rate_limit import evaluate_rate_limit
from .services import (
    QUIZ_ID_RE,
    StatePayloadError,
    apply_completion_cooldown,
    build_cooldown_status,
    compute_attempt_duration_ms,
    compute_leaderboard_score,
    compute_progress,
    compute_quiz_outcome,
    current_leaderboard_season_key,
    load_quiz_content,
    load_quiz_label_mapping,
    maybe_reset_retry_streak,
    normalize_state_payload,
    question_time_limit_seconds,
    quiz_exists,
    quiz_file_path,
    quiz_question_count,
    update_leaderboard_best,
    upsert_progress_from_state,
)
from .subject_services import SubjectCatalog, load_subject_catalog
from .tracking_services import (
    annotate_subject_lectures_with_marks,
    personal_tracking_summary_for_user,
    set_podcast_mark,
    set_reading_mark,
    subject_tracking_index,
)
logger = logging.getLogger(__name__)
MAX_STATE_BYTES = 5_000_000
DIFFICULTY_LABELS_DA = {
    "easy": "Let",
    "medium": "Mellem",
    "hard": "Svær",
    "unknown": "Ukendt",
}
DIFFICULTY_SORT_ORDER = {
    "easy": 0,
    "medium": 1,
    "hard": 2,
    "unknown": 3,
}
LECTURE_KEY_DISPLAY_RE = re.compile(r"^W(?P<week>\d{1,2})L(?P<lecture>\d+)$", re.IGNORECASE)
LECTURE_META_SUFFIX_RE = re.compile(
    r"\s*\((?:forelæsning|forelaesning)\s+\d+\s*,\s*\d{4}-\d{2}-\d{2}\)\s*$",
    re.IGNORECASE,
)
QUIZ_CFG_BLOCK_RE = re.compile(r"\{(?P<body>[^{}]+)\}")
QUIZ_CFG_PAIR_RE = re.compile(r"(?P<key>[a-z0-9._:+-]+)=(?P<value>[^{}\s]+)", re.IGNORECASE)
QUIZ_FILE_SUFFIX_RE = re.compile(r"\.(?:mp3|m4a|wav|aac|flac|ogg|json|html)$", re.IGNORECASE)
QUIZ_LANGUAGE_TAG_RE = re.compile(r"\[(?P<lang>[A-Za-z]{2,5})\]")
QUIZ_BRIEF_PREFIX_RE = re.compile(r"^\s*\[brief\]\s*", re.IGNORECASE)
QUIZ_LECTURE_KEY_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
MULTISPACE_RE = re.compile(r"\s+")
SPOTIFY_EPISODE_ID_RE = re.compile(
    r"^https://open\.spotify\.com/episode/(?P<episode_id>[A-Za-z0-9]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
SUBJECT_READING_KEY_RE = re.compile(r"^[a-z0-9-]+$")
SUBJECT_LECTURE_KEY_RE = re.compile(r"^W\d{2}L\d+$", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_READING_EXCLUSION_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "data": {},
}


def _is_http_insecure(request: HttpRequest) -> bool:
    return not request.is_secure()


def _requested_next(request: HttpRequest) -> str:
    value = request.POST.get("next") or request.GET.get("next") or ""
    return value.strip()


def _safe_next_redirect(request: HttpRequest) -> str | None:
    candidate = _requested_next(request)
    if not candidate:
        return None
    if not url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    return candidate


def _safe_referer_redirect(request: HttpRequest) -> str | None:
    referer = str(request.META.get("HTTP_REFERER") or "").strip()
    if not referer:
        return None
    if not url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    return referer


def _as_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _difficulty_label(value: str | None) -> str:
    difficulty = (value or "unknown").strip().lower() or "unknown"
    return DIFFICULTY_LABELS_DA.get(difficulty, difficulty.capitalize())


def _difficulty_sort_rank(value: object) -> int:
    difficulty = str(value or "unknown").strip().lower() or "unknown"
    return DIFFICULTY_SORT_ORDER.get(difficulty, len(DIFFICULTY_SORT_ORDER))


def _subject_or_404(catalog: SubjectCatalog, subject_slug: str):
    subject = catalog.active_subject_by_slug(subject_slug)
    if subject is None:
        raise Http404("Fag ikke fundet")
    return subject


def _source_filename_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return None
    if candidate.name != text:
        return None
    if ".." in candidate.parts:
        return None
    return text


def _reading_file_path_or_404(*, lecture_key: str, source_filename: str) -> Path:
    lecture = str(lecture_key or "").strip().upper()
    if not SUBJECT_LECTURE_KEY_RE.match(lecture):
        raise Http404("Tekst ikke fundet i fagets læringssti.")

    root = Path(settings.FREUDD_READING_FILES_ROOT)
    try:
        resolved_root = root.resolve()
    except OSError as exc:
        raise Http404("Tekst-filer kunne ikke tilgås.") from exc

    candidate = resolved_root / lecture / source_filename
    try:
        resolved_candidate = candidate.resolve()
    except OSError as exc:
        raise Http404("Tekst-filen kunne ikke tilgås.") from exc

    if resolved_root not in resolved_candidate.parents:
        raise Http404("Tekst-filen kunne ikke tilgås.")
    if not resolved_candidate.is_file():
        raise Http404("Tekst-filen blev ikke fundet.")
    return resolved_candidate


def _normalize_exclusion_payload(payload: object) -> dict[str, set[str]]:
    by_subject: dict[str, set[str]] = {}
    if not isinstance(payload, dict):
        return by_subject

    subjects = payload.get("subjects")
    if isinstance(subjects, dict):
        for raw_slug, raw_entry in subjects.items():
            slug = str(raw_slug or "").strip().lower()
            if not SUBJECT_SLUG_RE.match(slug):
                continue
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            values = entry.get("excluded_reading_keys")
            if not isinstance(values, list):
                continue
            excluded = {
                str(item or "").strip().lower()
                for item in values
                if SUBJECT_READING_KEY_RE.match(str(item or "").strip().lower())
            }
            by_subject[slug] = excluded

    # Backward-compatible single-subject shape.
    single_slug = str(payload.get("subject_slug") or "").strip().lower()
    single_values = payload.get("excluded_reading_keys")
    if SUBJECT_SLUG_RE.match(single_slug) and isinstance(single_values, list):
        single_excluded = {
            str(item or "").strip().lower()
            for item in single_values
            if SUBJECT_READING_KEY_RE.match(str(item or "").strip().lower())
        }
        by_subject[single_slug] = single_excluded

    return by_subject


def _load_reading_download_exclusions() -> dict[str, set[str]]:
    path = Path(settings.FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH)
    if not path.exists():
        return {}

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Unable to stat reading exclusion config: %s", path, exc_info=True)
        return {}

    cache_hit = (
        _READING_EXCLUSION_CACHE.get("path") == str(path)
        and _READING_EXCLUSION_CACHE.get("mtime") == mtime
        and isinstance(_READING_EXCLUSION_CACHE.get("data"), dict)
    )
    if cache_hit:
        return _READING_EXCLUSION_CACHE["data"]  # type: ignore[return-value]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to read reading exclusion config: %s", path, exc_info=True)
        data: dict[str, set[str]] = {}
    else:
        data = _normalize_exclusion_payload(payload)

    _READING_EXCLUSION_CACHE["path"] = str(path)
    _READING_EXCLUSION_CACHE["mtime"] = mtime
    _READING_EXCLUSION_CACHE["data"] = data
    return data


def _is_reading_download_excluded(*, subject_slug: str, reading_key: str) -> bool:
    by_subject = _load_reading_download_exclusions()
    excluded = by_subject.get(subject_slug, set())
    return reading_key in excluded


def _auth_url_with_next(route_name: str, next_path: str) -> str:
    return f"{reverse(route_name)}?{urlencode({'next': next_path})}"


def _rate_limit_exceeded(
    request: HttpRequest,
    *,
    scope: str,
    limit: int,
) -> tuple[bool, int]:
    result = evaluate_rate_limit(
        request,
        scope=scope,
        limit=limit,
        window_seconds=settings.QUIZ_RATE_LIMIT_WINDOW_SECONDS,
    )
    return (not result.allowed, result.retry_after_seconds)


def _safe_non_negative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _cooldown_payload(*, progress: QuizProgress) -> dict[str, object]:
    status = build_cooldown_status(progress)
    return {
        "is_blocked": status.is_blocked,
        "retry_after_seconds": status.retry_after_seconds,
        "available_at": status.available_at,
        "streak_count": status.streak_count,
        "next_cooldown_seconds": status.next_cooldown_seconds,
    }


def _subject_path_overview(lectures: object) -> dict[str, int]:
    if not isinstance(lectures, list):
        return {
            "total_lectures": 0,
            "completed_lectures": 0,
            "total_quizzes": 0,
            "completed_quizzes": 0,
            "remaining_quizzes": 0,
            "total_readings": 0,
            "remaining_readings": 0,
            "completion_percent": 0,
        }

    total_lectures = 0
    completed_lectures = 0
    total_quizzes = 0
    completed_quizzes = 0
    total_readings = 0
    remaining_readings = 0

    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        total_lectures += 1
        status = str(lecture.get("status") or "").strip().lower()
        if status == "completed":
            completed_lectures += 1

        total_quizzes += _safe_non_negative_int(lecture.get("total_quizzes"))
        completed_quizzes += _safe_non_negative_int(lecture.get("completed_quizzes"))

        readings = lecture.get("readings")
        if not isinstance(readings, list):
            continue
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            total_readings += 1
            reading_status = str(reading.get("status") or "").strip().lower()
            if reading_status not in {"completed", "no_quiz"}:
                remaining_readings += 1

    remaining_quizzes = max(0, total_quizzes - completed_quizzes)
    completion_percent = int(round((completed_quizzes / total_quizzes) * 100)) if total_quizzes else 0
    return {
        "total_lectures": total_lectures,
        "completed_lectures": completed_lectures,
        "total_quizzes": total_quizzes,
        "completed_quizzes": completed_quizzes,
        "remaining_quizzes": remaining_quizzes,
        "total_readings": total_readings,
        "remaining_readings": remaining_readings,
        "completion_percent": completion_percent,
    }


def _progress_percent(*, completed: object, total: object) -> int:
    completed_count = _safe_non_negative_int(completed)
    total_count = _safe_non_negative_int(total)
    if total_count <= 0:
        return 0
    return max(0, min(100, int(round((completed_count / total_count) * 100))))


def _lecture_display_parts(*, lecture_key: object, lecture_title: object) -> tuple[str, str]:
    raw_key = str(lecture_key or "").strip().upper()
    raw_title = str(lecture_title or "").strip()

    match = LECTURE_KEY_DISPLAY_RE.match(raw_key)
    if match:
        week = int(match.group("week"))
        lecture = int(match.group("lecture"))
        label = f"Uge {week}, forelæsning {lecture}"
    else:
        label = raw_key

    cleaned_title = raw_title
    if raw_key and cleaned_title.upper().startswith(raw_key):
        cleaned_title = cleaned_title[len(raw_key) :].lstrip(" -·").strip()
    cleaned_title = LECTURE_META_SUFFIX_RE.sub("", cleaned_title).strip()
    if cleaned_title:
        return label, cleaned_title
    if label:
        return label, ""
    return "", raw_title


def _lecture_rail_copy(
    *,
    lecture_key: object,
    lecture_display_name: object,
    lecture_display_title: object,
) -> str:
    key_text = str(lecture_key or "").strip().upper()
    name_text = str(lecture_display_name or "").strip()
    title_text = str(lecture_display_title or "").strip()
    lecture_text = name_text or title_text or key_text

    match = LECTURE_KEY_DISPLAY_RE.match(key_text)
    if match:
        week = int(match.group("week"))
        lecture = int(match.group("lecture"))
        prefix = f"Uge {week}, forelæsning {lecture}"
        if lecture_text and lecture_text.casefold() != prefix.casefold():
            return f"{prefix}: {lecture_text}"
        return prefix
    return lecture_text


def _quiz_cfg_tags(raw_title: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for block_match in QUIZ_CFG_BLOCK_RE.finditer(raw_title):
        block = str(block_match.group("body") or "").strip()
        for token_match in QUIZ_CFG_PAIR_RE.finditer(block):
            key = str(token_match.group("key") or "").strip().lower()
            value = str(token_match.group("value") or "").strip()
            if key and value:
                tags[key] = value
    return tags


def _quiz_module_label_from_text(value: str) -> str:
    match = QUIZ_LECTURE_KEY_RE.search(value)
    if not match:
        return ""
    week = int(match.group("week"))
    lecture = int(match.group("lecture"))
    return f"Uge {week}, forelæsning {lecture}"


def _quiz_core_parts(episode_title: object) -> tuple[str, str, dict[str, str], str]:
    raw_title = str(episode_title or "").strip()
    if not raw_title:
        return "", "Quiz", {}, ""

    without_suffix = QUIZ_FILE_SUFFIX_RE.sub("", raw_title)
    cfg_tags = _quiz_cfg_tags(without_suffix)
    without_cfg = QUIZ_CFG_BLOCK_RE.sub("", without_suffix).strip()

    language = str(cfg_tags.get("lang") or "").strip()
    if not language:
        lang_matches = QUIZ_LANGUAGE_TAG_RE.findall(without_cfg)
        if lang_matches:
            language = str(lang_matches[-1]).strip()
    without_language = QUIZ_LANGUAGE_TAG_RE.sub("", without_cfg).strip()

    without_brief = QUIZ_BRIEF_PREFIX_RE.sub("", without_language).strip()
    module_label = _quiz_module_label_from_text(without_brief)

    lecture_match = QUIZ_LECTURE_KEY_RE.search(without_brief)
    if lecture_match:
        without_brief = (
            f"{without_brief[: lecture_match.start()]} {without_brief[lecture_match.end() :]}"
        ).strip()

    title = without_brief.lstrip("-·: ").strip()
    title = MULTISPACE_RE.sub(" ", title).strip()
    if not title:
        title = "Quiz"

    return module_label, title, cfg_tags, language.upper()


def _quiz_meta_chips(*, cfg_tags: dict[str, str], language: str) -> list[str]:
    chips: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        candidate = value.strip()
        if not candidate:
            return
        key = candidate.casefold()
        if key in seen:
            return
        seen.add(key)
        chips.append(candidate)

    media_type = str(cfg_tags.get("type") or "").strip().lower()
    if media_type == "audio":
        _add("Lyd")
    elif media_type:
        _add(media_type.replace("-", " ").replace("_", " ").title())

    format_token = str(cfg_tags.get("format") or "").strip().lower()
    if format_token == "deep-dive":
        _add("Deep dive")
    elif format_token == "brief":
        _add("Brief")
    elif format_token:
        _add(format_token.replace("-", " ").replace("_", " ").title())

    length_token = str(cfg_tags.get("length") or "").strip().lower()
    if length_token == "long":
        _add("Lang")
    elif length_token in {"default", "standard"}:
        _add("Standard")
    elif length_token:
        _add(length_token.replace("-", " ").replace("_", " ").title())

    if language:
        _add(language)

    return chips


def _quiz_display_context(*, episode_title: object, quiz_id: str) -> dict[str, object]:
    module_label, title, cfg_tags, language = _quiz_core_parts(episode_title)
    meta_chips = _quiz_meta_chips(cfg_tags=cfg_tags, language=language)
    raw_title = str(episode_title or "").strip() or str(quiz_id)
    return {
        "raw_title": raw_title,
        "title": title,
        "module_label": module_label,
        "meta_chips": meta_chips,
    }


def _compact_asset_links(
    assets: object,
    *,
    question_count_by_quiz_id: dict[str, int | None] | None = None,
) -> dict[str, list[dict[str, object]]]:
    if not isinstance(assets, dict):
        return {"quizzes": [], "podcasts": []}

    question_count_cache = question_count_by_quiz_id if question_count_by_quiz_id is not None else {}

    compact_quizzes: list[dict[str, object]] = []
    seen_difficulties: set[str] = set()
    quizzes = assets.get("quizzes")
    if isinstance(quizzes, list):
        for quiz in quizzes:
            if not isinstance(quiz, dict):
                continue
            quiz_url = str(quiz.get("quiz_url") or "").strip()
            if not quiz_url:
                continue
            difficulty = str(quiz.get("difficulty") or "unknown").strip().lower() or "unknown"
            if difficulty in seen_difficulties:
                continue
            seen_difficulties.add(difficulty)
            quiz_id = str(quiz.get("quiz_id") or "").strip()
            question_count: int | None = None
            if quiz_id:
                if quiz_id not in question_count_cache:
                    count = quiz_question_count(quiz_id)
                    question_count_cache[quiz_id] = count if count and count > 0 else None
                question_count = question_count_cache.get(quiz_id)
            compact_quizzes.append(
                {
                    **quiz,
                    "difficulty": difficulty,
                    "difficulty_label_da": _difficulty_label(difficulty),
                    "question_count": question_count,
                }
            )
    compact_quizzes.sort(
        key=lambda item: (
            _difficulty_sort_rank(item.get("difficulty")),
            str(item.get("quiz_id") or "").lower(),
            str(item.get("episode_title") or "").casefold(),
        )
    )

    compact_podcasts: list[dict[str, object]] = []
    podcasts = assets.get("podcasts")
    if isinstance(podcasts, list):
        for podcast in podcasts:
            if not isinstance(podcast, dict):
                continue
            podcast_url = str(podcast.get("url") or "").strip()
            if not podcast_url:
                continue
            match = SPOTIFY_EPISODE_ID_RE.match(podcast_url)
            podcast_copy = dict(podcast)
            if match:
                episode_id = str(match.group("episode_id") or "").strip()
                podcast_copy["spotify_embed_url"] = (
                    f"https://open.spotify.com/embed/episode/{episode_id}?utm_source=generator"
                )
                compact_podcasts.append(podcast_copy)

    return {
        "quizzes": compact_quizzes,
        "podcasts": compact_podcasts,
    }


def _enrich_subject_path_lectures(lectures: object) -> list[dict[str, object]]:
    if not isinstance(lectures, list):
        return []

    question_count_by_quiz_id: dict[str, int | None] = {}
    enriched: list[dict[str, object]] = []
    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_assets = _compact_asset_links(
            lecture.get("lecture_assets"),
            question_count_by_quiz_id=question_count_by_quiz_id,
        )
        lecture_copy = dict(lecture)
        lecture_copy["lecture_assets"] = lecture_assets
        lecture_label, lecture_name = _lecture_display_parts(
            lecture_key=lecture_copy.get("lecture_key"),
            lecture_title=lecture_copy.get("lecture_title"),
        )
        lecture_copy["lecture_display_label"] = lecture_label
        lecture_copy["lecture_display_name"] = lecture_name
        if lecture_label and lecture_name:
            lecture_copy["lecture_display_title"] = f"{lecture_label} · {lecture_name}"
        else:
            lecture_copy["lecture_display_title"] = lecture_label or lecture_name
        lecture_copy["progress_percent"] = _progress_percent(
            completed=lecture_copy.get("completed_quizzes"),
            total=lecture_copy.get("total_quizzes"),
        )
        has_lecture_quizzes = bool(lecture_assets.get("quizzes"))
        has_lecture_podcasts = bool(lecture_assets.get("podcasts"))

        readings = lecture_copy.get("readings")
        reading_payload: list[dict[str, object]] = []
        has_reading_quizzes = False
        has_reading_podcasts = False
        if isinstance(readings, list):
            for reading in readings:
                if not isinstance(reading, dict):
                    continue
                reading_copy = dict(reading)
                reading_copy["assets"] = _compact_asset_links(
                    reading_copy.get("assets"),
                    question_count_by_quiz_id=question_count_by_quiz_id,
                )
                reading_copy["progress_percent"] = _progress_percent(
                    completed=reading_copy.get("completed_quizzes"),
                    total=reading_copy.get("total_quizzes"),
                )
                assets = reading_copy.get("assets") if isinstance(reading_copy.get("assets"), dict) else {}
                if assets.get("quizzes"):
                    has_reading_quizzes = True
                if assets.get("podcasts"):
                    has_reading_podcasts = True
                reading_payload.append(reading_copy)
        lecture_copy["readings"] = reading_payload
        lecture_copy["has_reading_quizzes"] = has_reading_quizzes
        lecture_copy["has_reading_podcasts"] = has_reading_podcasts
        lecture_copy["has_any_quizzes"] = has_lecture_quizzes or has_reading_quizzes
        lecture_copy["has_any_podcasts"] = has_lecture_podcasts or has_reading_podcasts
        enriched.append(lecture_copy)
    return enriched


def _quiz_difficulty_slots(assets: object) -> list[dict[str, object]]:
    quiz_by_difficulty: dict[str, dict[str, object]] = {}
    assets_payload = assets if isinstance(assets, dict) else {}
    quizzes = assets_payload.get("quizzes") if isinstance(assets_payload.get("quizzes"), list) else []
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        difficulty = str(quiz.get("difficulty") or "unknown").strip().lower() or "unknown"
        if difficulty not in {"easy", "medium", "hard"}:
            continue
        if difficulty not in quiz_by_difficulty:
            quiz_by_difficulty[difficulty] = quiz

    return [
        {
            "difficulty": "easy",
            "label": "Let",
            "chip": "L",
            "quiz_url": str(quiz_by_difficulty.get("easy", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("easy", {}).get("question_count"),
        },
        {
            "difficulty": "medium",
            "label": "Mellem",
            "chip": "M",
            "quiz_url": str(quiz_by_difficulty.get("medium", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("medium", {}).get("question_count"),
        },
        {
            "difficulty": "hard",
            "label": "Svær",
            "chip": "S",
            "quiz_url": str(quiz_by_difficulty.get("hard", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("hard", {}).get("question_count"),
        },
    ]


def _reading_difficulty_summary(reading: object) -> list[dict[str, object]]:
    if not isinstance(reading, dict):
        return _quiz_difficulty_slots({})
    assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
    return _quiz_difficulty_slots(assets)


def _podcast_display_title(value: object) -> str:
    title_text = str(value or "").strip()
    if not title_text:
        return "Podcast episode"
    parts = [part.strip() for part in title_text.split("·") if part.strip()]
    if len(parts) >= 3:
        return parts[2]
    return title_text


def _flatten_podcast_rows(lecture: object) -> list[dict[str, object]]:
    if not isinstance(lecture, dict):
        return []
    rows: list[dict[str, object]] = []
    lecture_key = str(lecture.get("lecture_key") or "").strip().upper()

    lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
    lecture_podcasts = (
        lecture_assets.get("podcasts")
        if isinstance(lecture_assets.get("podcasts"), list)
        else []
    )
    for podcast in lecture_podcasts:
        if not isinstance(podcast, dict):
            continue
        rows.append(
            {
                **podcast,
                "lecture_key": lecture_key,
                "reading_key": None,
                "source_label": "Forelæsning",
                "display_title": _podcast_display_title(podcast.get("title")),
                "duration_label": str(podcast.get("duration_label") or "").strip(),
            }
        )

    readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
    for reading in readings:
        if not isinstance(reading, dict):
            continue
        reading_title = str(reading.get("reading_title") or "").strip() or "Tekst"
        reading_key = str(reading.get("reading_key") or "").strip() or None
        assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
        reading_podcasts = (
            assets.get("podcasts")
            if isinstance(assets.get("podcasts"), list)
            else []
        )
        for podcast in reading_podcasts:
            if not isinstance(podcast, dict):
                continue
            rows.append(
                {
                    **podcast,
                    "lecture_key": lecture_key,
                    "reading_key": reading_key,
                    "source_label": reading_title,
                    "display_title": _podcast_display_title(podcast.get("title")),
                    "duration_label": str(podcast.get("duration_label") or "").strip(),
                }
            )

    for index, row in enumerate(rows, start=1):
        row["episode_index"] = index
    return rows


def _selected_active_lecture(
    lectures: list[dict[str, object]],
    *,
    requested_lecture_key: object,
) -> tuple[int, dict[str, object] | None]:
    if not lectures:
        return -1, None

    requested_key = str(requested_lecture_key or "").strip().upper()
    if requested_key:
        for index, lecture in enumerate(lectures):
            lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
            if lecture_key == requested_key:
                return index, lecture

    for index, lecture in enumerate(lectures):
        status = str(lecture.get("status") or "").strip().lower()
        if status != "completed":
            return index, lecture

    return 0, lectures[0]


def _normalize_subject_lecture_key(value: object) -> str:
    lecture_key = str(value or "").strip().upper()
    if not lecture_key:
        return ""
    if not SUBJECT_LECTURE_KEY_RE.match(lecture_key):
        return ""
    return lecture_key


def _load_last_subject_lecture_key(*, user, subject_slug: str) -> str:
    row = (
        UserSubjectLastLecture.objects.filter(
            user=user,
            subject_slug=subject_slug,
        )
        .only("lecture_key")
        .first()
    )
    if row is None:
        return ""
    return _normalize_subject_lecture_key(row.lecture_key)


def _save_last_subject_lecture_key(*, user, subject_slug: str, lecture_key: object) -> None:
    normalized_lecture_key = _normalize_subject_lecture_key(lecture_key)
    if not normalized_lecture_key:
        return
    UserSubjectLastLecture.objects.update_or_create(
        user=user,
        subject_slug=subject_slug,
        defaults={"lecture_key": normalized_lecture_key},
    )


def _lecture_rail_items(
    *,
    subject_slug: str,
    lectures: list[dict[str, object]],
    active_index: int,
) -> list[dict[str, object]]:
    detail_url = reverse("subject-detail", kwargs={"subject_slug": subject_slug})
    items: list[dict[str, object]] = []
    for index, lecture in enumerate(lectures, start=1):
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        if lecture_key:
            lecture_url = f"{detail_url}?{urlencode({'lecture': lecture_key})}"
        else:
            lecture_url = detail_url
        status = str(lecture.get("status") or "").strip().lower()
        items.append(
            {
                "index": index,
                "lecture_key": lecture_key,
                "lecture_url": lecture_url,
                "is_active": (index - 1) == active_index,
                "is_past": (index - 1) < active_index,
                "is_completed": status == "completed",
                "lecture_display_label": str(lecture.get("lecture_display_label") or "").strip(),
                "lecture_display_name": str(lecture.get("lecture_display_name") or "").strip(),
                "lecture_display_title": str(lecture.get("lecture_display_title") or "").strip(),
                "rail_copy": _lecture_rail_copy(
                    lecture_key=lecture.get("lecture_key"),
                    lecture_display_name=lecture.get("lecture_display_name"),
                    lecture_display_title=lecture.get("lecture_display_title"),
                ),
            }
        )
    return items


@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("progress")
    safe_next = _safe_next_redirect(request)
    google_auth_enabled = bool(getattr(settings, "FREUDD_AUTH_GOOGLE_ENABLED", False))

    if request.method == "POST":
        blocked, retry_after = _rate_limit_exceeded(
            request,
            scope="signup",
            limit=settings.QUIZ_SIGNUP_RATE_LIMIT,
        )
        form = SignupForm(request.POST)
        if blocked:
            form.add_error(None, f"For mange forsøg på oprettelse. Prøv igen om {retry_after} sekunder.")
            return render(
                request,
                "registration/signup.html",
                {
                    "form": form,
                    "insecure_http": _is_http_insecure(request),
                    "next_value": safe_next,
                    "google_auth_enabled": google_auth_enabled,
                },
                status=429,
            )
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(_safe_next_redirect(request) or "progress")
    else:
        form = SignupForm()

    return render(
        request,
        "registration/signup.html",
        {
            "form": form,
            "insecure_http": _is_http_insecure(request),
            "next_value": safe_next,
            "google_auth_enabled": google_auth_enabled,
        },
    )


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("progress")
    safe_next = _safe_next_redirect(request)
    google_auth_enabled = bool(getattr(settings, "FREUDD_AUTH_GOOGLE_ENABLED", False))

    if request.method == "POST":
        blocked, retry_after = _rate_limit_exceeded(
            request,
            scope="login",
            limit=settings.QUIZ_LOGIN_RATE_LIMIT,
        )
        form = AuthenticationForm(request, data=request.POST)
        if blocked:
            form.add_error(None, f"For mange loginforsøg. Prøv igen om {retry_after} sekunder.")
            return render(
                request,
                "registration/login.html",
                {
                    "form": form,
                    "insecure_http": _is_http_insecure(request),
                    "next_value": safe_next,
                    "google_auth_enabled": google_auth_enabled,
                },
                status=429,
            )
        if form.is_valid():
            login(request, form.get_user())
            return redirect(_safe_next_redirect(request) or "progress")
    else:
        form = AuthenticationForm(request)

    return render(
        request,
        "registration/login.html",
        {
            "form": form,
            "insecure_http": _is_http_insecure(request),
            "next_value": safe_next,
            "google_auth_enabled": google_auth_enabled,
        },
    )


@require_POST
@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    messages.info(request, "Du er nu logget ud.")
    return redirect("login")


def _ensure_quiz_id_or_404(quiz_id: str) -> str:
    if not QUIZ_ID_RE.match(quiz_id):
        raise Http404("Quiz ikke fundet")
    return quiz_id


def _ensure_quiz_exists_or_404(quiz_id: str) -> None:
    if not quiz_exists(quiz_id):
        raise Http404("Quiz ikke fundet")


@require_GET
def quiz_wrapper_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    quiz_id = _ensure_quiz_id_or_404(quiz_id)
    _ensure_quiz_exists_or_404(quiz_id)

    label = load_quiz_label_mapping().get(quiz_id)
    episode_title = label.episode_title if label else quiz_id
    difficulty_label = _difficulty_label(label.difficulty if label else "unknown")
    quiz_display = _quiz_display_context(episode_title=episode_title, quiz_id=quiz_id)
    quiz_path = reverse("quiz-wrapper", kwargs={"quiz_id": quiz_id})
    context = {
        "quiz_id": quiz_id,
        "quiz_page_title": " · ".join(
            item for item in (quiz_display.get("module_label"), quiz_display.get("title")) if item
        ),
        "quiz_title": quiz_display.get("title") or quiz_id,
        "quiz_module_label": quiz_display.get("module_label") or "",
        "quiz_meta_chips": list(quiz_display.get("meta_chips") or []),
        "quiz_raw_title": quiz_display.get("raw_title") or episode_title,
        "quiz_difficulty_label": difficulty_label,
        "quiz_content_url": reverse("quiz-content", kwargs={"quiz_id": quiz_id}),
        "state_api_url": reverse("quiz-state", kwargs={"quiz_id": quiz_id}),
        "question_time_limit_seconds": question_time_limit_seconds(),
        "user_is_authenticated": request.user.is_authenticated,
        "login_next_url": _auth_url_with_next("login", quiz_path),
        "signup_next_url": _auth_url_with_next("signup", quiz_path),
    }
    return render(request, "quizzes/wrapper.html", context)


@require_GET
def quiz_raw_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    quiz_id = _ensure_quiz_id_or_404(quiz_id)
    _ensure_quiz_exists_or_404(quiz_id)
    path = quiz_file_path(quiz_id)
    if not path.is_file():
        raise Http404("Quiz ikke fundet")
    return FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")


@require_GET
def quiz_content_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    quiz_id = _ensure_quiz_id_or_404(quiz_id)
    _ensure_quiz_exists_or_404(quiz_id)

    payload = load_quiz_content(quiz_id)
    if payload is None:
        raise Http404("Quiz ikke fundet")
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET", "POST"])
def quiz_state_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    quiz_id = _ensure_quiz_id_or_404(quiz_id)
    _ensure_quiz_exists_or_404(quiz_id)

    if request.method == "GET":
        progress = QuizProgress.objects.filter(user=request.user, quiz_id=quiz_id).first()
        if not progress:
            return JsonResponse(None, safe=False)
        if maybe_reset_retry_streak(progress):
            progress.save(
                update_fields=[
                    "retry_streak_count",
                    "retry_cooldown_until_at",
                    "updated_at",
                ]
            )
        state_payload = progress.state_json if isinstance(progress.state_json, dict) else {}
        response_payload = dict(state_payload)
        response_payload["_meta"] = {"cooldown": _cooldown_payload(progress=progress)}
        return JsonResponse(response_payload, safe=False)

    if len(request.body) > MAX_STATE_BYTES:
        return HttpResponseBadRequest("State-payload er for stor.")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Ugyldig JSON-body.")

    try:
        state_payload = normalize_state_payload(payload)
    except StatePayloadError as exc:
        return HttpResponseBadRequest(str(exc))

    progress, _ = QuizProgress.objects.get_or_create(
        user=request.user,
        quiz_id=quiz_id,
        defaults={"state_json": {}, "raw_state_payload": None},
    )
    now = timezone.now()
    if maybe_reset_retry_streak(progress, now=now):
        progress.save(
            update_fields=[
                "retry_streak_count",
                "retry_cooldown_until_at",
                "updated_at",
            ]
        )
    previous_answers_count = int(progress.answers_count or 0)
    previous_status = str(progress.status or QuizProgress.Status.IN_PROGRESS)

    question_count = quiz_question_count(quiz_id) or progress.question_count
    computation = compute_progress(state_payload, question_count)

    is_reset_request = (
        previous_status == QuizProgress.Status.COMPLETED
        and computation.status != QuizProgress.Status.COMPLETED
        and computation.answers_count == 0
        and int(state_payload.get("currentQuestionIndex") or 0) == 0
        and str(state_payload.get("currentView") or "question").strip().lower() == "question"
    )
    if is_reset_request:
        cooldown_payload = _cooldown_payload(progress=progress)
        if bool(cooldown_payload.get("is_blocked")):
            return JsonResponse(
                {
                    "error": "cooldown_active",
                    "cooldown": cooldown_payload,
                },
                status=429,
            )
        progress.attempt_started_at = now
    elif progress.attempt_started_at is None:
        progress.attempt_started_at = now

    upsert_progress_from_state(progress=progress, state_payload=state_payload, computation=computation)

    completion_transition = (
        previous_status != QuizProgress.Status.COMPLETED
        and progress.status == QuizProgress.Status.COMPLETED
    )
    if completion_transition:
        now = timezone.now()
        quiz_payload = load_quiz_content(quiz_id)
        outcome = compute_quiz_outcome(state_payload=state_payload, quiz_payload=quiz_payload)
        duration_ms = compute_attempt_duration_ms(progress, now=now)
        apply_completion_cooldown(progress, now=now)
        season_key = current_leaderboard_season_key(now=now)
        score_points = compute_leaderboard_score(
            correct_answers=outcome.correct_answers,
            question_count=outcome.question_count,
            duration_ms=duration_ms,
            question_time_limit_seconds=question_time_limit_seconds(),
        )
        update_leaderboard_best(
            progress=progress,
            season_key=season_key,
            reached_at=now,
            score_points=score_points,
            correct_answers=outcome.correct_answers,
            question_count=outcome.question_count,
            duration_ms=duration_ms,
        )
        progress.save(
            update_fields=[
                "retry_streak_count",
                "last_attempt_completed_at",
                "retry_cooldown_until_at",
                "leaderboard_season_key",
                "leaderboard_best_score",
                "leaderboard_best_correct_answers",
                "leaderboard_best_question_count",
                "leaderboard_best_duration_ms",
                "leaderboard_best_reached_at",
                "updated_at",
            ]
        )

    try:
        record_quiz_progress_delta(
            progress=progress,
            previous_answers_count=previous_answers_count,
            previous_status=previous_status,
        )
    except Exception:
        logger.warning("Gamification update failed for quiz-state write", exc_info=True)

    return JsonResponse(
        {
            "quiz_id": progress.quiz_id,
            "status": progress.status,
            "answers_count": progress.answers_count,
            "question_count": progress.question_count,
            "last_view": progress.last_view,
            "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
            "cooldown": _cooldown_payload(progress=progress),
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def quiz_state_raw_view(request: HttpRequest, quiz_id: str) -> HttpResponse:
    quiz_id = _ensure_quiz_id_or_404(quiz_id)
    _ensure_quiz_exists_or_404(quiz_id)

    if request.method == "GET":
        progress = QuizProgress.objects.filter(user=request.user, quiz_id=quiz_id).first()
        if not progress:
            return JsonResponse(None, safe=False)
        if not progress.raw_state_payload:
            return JsonResponse(None, safe=False)
        return JsonResponse(progress.raw_state_payload, safe=False)

    progress, _ = QuizProgress.objects.get_or_create(
        user=request.user,
        quiz_id=quiz_id,
        defaults={"state_json": {}, "raw_state_payload": None},
    )

    try:
        payload_text = request.body.decode("utf-8").strip()
    except UnicodeDecodeError:
        return HttpResponseBadRequest("Payload skal være UTF-8.")

    if not payload_text:
        return HttpResponseBadRequest("Payload må ikke være tom.")

    try:
        json.loads(payload_text)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Raw payload skal være gyldig JSON.")

    if len(payload_text) > 5_000_000:
        return HttpResponseBadRequest("Payload er for stor.")

    progress.raw_state_payload = payload_text
    progress.save(update_fields=["raw_state_payload", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
@require_GET
def gamification_me_view(request: HttpRequest) -> HttpResponse:
    return JsonResponse(get_gamification_snapshot(request.user))


@login_required
@require_GET
def progress_view(request: HttpRequest) -> HttpResponse:
    catalog = load_subject_catalog()
    season = active_half_year_season()

    enrolled_slugs = set(
        SubjectEnrollment.objects.filter(user=request.user).values_list("subject_slug", flat=True)
    )
    subject_cards: list[dict[str, object]] = []
    subject_tracking_targets: list[dict[str, str]] = []
    leaderboard_preview_by_subject: list[dict[str, object]] = []
    for subject in catalog.active_subjects:
        detail_url = reverse("subject-detail", kwargs={"subject_slug": subject.slug})
        leaderboard_url = reverse("leaderboard-subject", kwargs={"subject_slug": subject.slug})
        subject_cards.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "description": subject.description,
                "is_enrolled": subject.slug in enrolled_slugs,
                "detail_url": detail_url,
                "enroll_url": reverse("subject-enroll", kwargs={"subject_slug": subject.slug}),
                "unenroll_url": reverse("subject-unenroll", kwargs={"subject_slug": subject.slug}),
                "leaderboard_url": leaderboard_url,
            }
        )
        subject_tracking_targets.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "detail_url": detail_url,
            }
        )
        leaderboard_snapshot = build_subject_leaderboard_snapshot(
            subject_slug=subject.slug,
            limit=5,
            season=season,
        )
        leaderboard_preview_by_subject.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "leaderboard_url": leaderboard_url,
                "entries": leaderboard_snapshot.get("entries") or [],
                "participant_count": int(leaderboard_snapshot.get("participant_count") or 0),
            }
        )

    label_mapping = load_quiz_label_mapping()
    progress_rows = (
        QuizProgress.objects.filter(user=request.user, completed_at__isnull=False)
        .order_by("-last_attempt_completed_at", "-completed_at", "-updated_at")
    )

    rows: list[dict[str, object]] = []
    for row in progress_rows:
        label = label_mapping.get(row.quiz_id)
        episode_title = label.episode_title if label else row.quiz_id
        quiz_display = _quiz_display_context(episode_title=episode_title, quiz_id=row.quiz_id)
        best_question_count = int(row.leaderboard_best_question_count or 0)
        best_correct_answers = int(row.leaderboard_best_correct_answers or 0)
        if best_question_count > 0:
            score_question_count = best_question_count
            score_correct_answers = max(0, min(best_correct_answers, best_question_count))
        else:
            score_question_count = max(0, int(row.question_count or 0))
            score_correct_answers = max(0, int(row.answers_count or 0))
        status = QuizProgress.Status.COMPLETED
        updated_at = row.last_attempt_completed_at or row.completed_at or row.updated_at
        rows.append(
            {
                "quiz_id": row.quiz_id,
                "title": quiz_display.get("title") or row.quiz_id,
                "module_label": quiz_display.get("module_label") or "",
                "meta_chips": list(quiz_display.get("meta_chips") or []),
                "difficulty_label": _difficulty_label(label.difficulty if label else "unknown"),
                "status": status,
                "status_label": status.label,
                "answers_count": score_correct_answers,
                "question_count": score_question_count,
                "updated_at": updated_at,
                "completed_at": row.completed_at,
                "quiz_url": reverse("quiz-wrapper", kwargs={"quiz_id": row.quiz_id}),
            }
        )

    profile_payload = get_profile_payload(request.user)
    leaderboard_alias_editing = _as_bool(request.GET.get("edit_alias")) and bool(
        str(profile_payload.get("public_alias") or "").strip()
    )
    personal_tracking_by_subject = personal_tracking_summary_for_user(
        user=request.user,
        subjects=subject_tracking_targets,
    )

    return render(
        request,
        "quizzes/progress.html",
        {
            "rows": rows,
            "subject_cards": subject_cards,
            "subjects_error": catalog.error,
            "leaderboard_profile": profile_payload,
            "leaderboard_alias_editing": leaderboard_alias_editing,
            "leaderboard_preview_by_subject": leaderboard_preview_by_subject,
            "personal_tracking_by_subject": personal_tracking_by_subject,
            "active_season": {
                "key": season.key,
                "label": season.label,
                "start_date_label": season.start_date_label,
                "end_date_label": season.end_date_label,
            },
        },
    )


@require_GET
def leaderboard_subject_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    season = active_half_year_season()
    snapshot = build_subject_leaderboard_snapshot(
        subject_slug=subject.slug,
        limit=50,
        season=season,
    )

    own_profile = None
    if request.user.is_authenticated:
        own_profile = get_profile_payload(request.user)

    return render(
        request,
        "quizzes/leaderboard.html",
        {
            "subject": subject,
            "entries": snapshot.get("entries") or [],
            "participant_count": int(snapshot.get("participant_count") or 0),
            "active_season": snapshot.get("season") or {},
            "leaderboard_profile": own_profile,
        },
    )


@login_required
@require_POST
def leaderboard_profile_view(request: HttpRequest) -> HttpResponse:
    profile_payload = get_profile_payload(request.user)
    current_alias = str(profile_payload.get("public_alias") or "").strip()
    allow_alias_change = _as_bool(request.POST.get("allow_alias_change"))
    alias = request.POST.get("public_alias")
    if current_alias and not allow_alias_change:
        alias = None
    is_public = _as_bool(request.POST.get("is_public"))

    try:
        update_leaderboard_profile(
            user=request.user,
            alias=alias,
            is_public=is_public,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages) if exc.messages else "Kunne ikke opdatere quizliga-profil.")
    else:
        if is_public:
            messages.success(request, "Din quizliga-profil er nu offentlig.")
        else:
            messages.info(request, "Din quizliga-profil er nu privat.")

    return redirect(
        _safe_next_redirect(request)
        or _safe_referer_redirect(request)
        or reverse("progress")
    )


@login_required
@require_GET
def subject_open_reading_view(request: HttpRequest, subject_slug: str, reading_key: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)

    normalized_reading_key = str(reading_key or "").strip().lower()
    if not SUBJECT_READING_KEY_RE.match(normalized_reading_key):
        raise Http404("Tekst ikke fundet i fagets læringssti.")
    if _is_reading_download_excluded(
        subject_slug=subject.slug,
        reading_key=normalized_reading_key,
    ):
        raise Http404("Tekst ikke fundet i fagets læringssti.")

    subject_path = get_subject_learning_path_snapshot(request.user, subject.slug)
    found_lecture_key: str | None = None
    found_source_filename: str | None = None
    for lecture in subject_path.get("lectures") or []:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            candidate_key = str(reading.get("reading_key") or "").strip().lower()
            if candidate_key != normalized_reading_key:
                continue
            found_lecture_key = lecture_key
            found_source_filename = _source_filename_or_none(reading.get("source_filename"))
            break
        if found_lecture_key:
            break

    if not found_lecture_key:
        raise Http404("Tekst ikke fundet i fagets læringssti.")
    if not found_source_filename:
        raise Http404("Tekst-filen blev ikke fundet.")

    file_path = _reading_file_path_or_404(
        lecture_key=found_lecture_key,
        source_filename=found_source_filename,
    )
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        content_type = "application/pdf"
        as_attachment = False
    elif suffix == ".docx":
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        as_attachment = True
    else:
        content_type = "application/octet-stream"
        as_attachment = True

    return FileResponse(
        file_path.open("rb"),
        content_type=content_type,
        as_attachment=as_attachment,
        filename=found_source_filename,
    )


@login_required
@require_POST
def subject_tracking_reading_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)

    lecture_key = str(request.POST.get("lecture_key") or "").strip().upper()
    reading_key = str(request.POST.get("reading_key") or "").strip()
    if not lecture_key or not reading_key:
        return HttpResponseBadRequest("Mangler lecture_key eller reading_key.")

    index = subject_tracking_index(subject.slug)
    if (lecture_key, reading_key, "") not in index["reading_keys"]:
        raise Http404("Tekst ikke fundet i fagets læringssti.")

    action = str(request.POST.get("action") or "toggle").strip().lower()
    if action == "mark":
        marked = True
    elif action == "unmark":
        marked = False
    else:
        marked = not UserReadingMark.objects.filter(
            user=request.user,
            subject_slug=subject.slug,
            lecture_key=lecture_key,
            reading_key=reading_key,
        ).exists()

    set_reading_mark(
        user=request.user,
        subject_slug=subject.slug,
        lecture_key=lecture_key,
        reading_key=reading_key,
        marked=marked,
    )

    return redirect(
        _safe_next_redirect(request)
        or _safe_referer_redirect(request)
        or reverse("subject-detail", kwargs={"subject_slug": subject.slug})
    )


@login_required
@require_POST
def subject_tracking_podcast_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)

    lecture_key = str(request.POST.get("lecture_key") or "").strip().upper()
    reading_key_raw = str(request.POST.get("reading_key") or "").strip()
    reading_key = reading_key_raw or None
    podcast_key = str(request.POST.get("podcast_key") or "").strip().lower()
    if not lecture_key or not podcast_key:
        return HttpResponseBadRequest("Mangler lecture_key eller podcast_key.")

    index = subject_tracking_index(subject.slug)
    if (lecture_key, reading_key, podcast_key) not in index["podcast_keys"]:
        raise Http404("Podcast ikke fundet i fagets læringssti.")

    action = str(request.POST.get("action") or "toggle").strip().lower()
    if action == "mark":
        marked = True
    elif action == "unmark":
        marked = False
    else:
        marked = not UserPodcastMark.objects.filter(
            user=request.user,
            subject_slug=subject.slug,
            lecture_key=lecture_key,
            reading_key=reading_key,
            podcast_key=podcast_key,
        ).exists()

    set_podcast_mark(
        user=request.user,
        subject_slug=subject.slug,
        lecture_key=lecture_key,
        reading_key=reading_key,
        podcast_key=podcast_key,
        marked=marked,
    )

    return redirect(
        _safe_next_redirect(request)
        or _safe_referer_redirect(request)
        or reverse("subject-detail", kwargs={"subject_slug": subject.slug})
    )


@login_required
@require_POST
def subject_enroll_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    SubjectEnrollment.objects.get_or_create(
        user=request.user,
        subject_slug=subject.slug,
    )
    messages.success(request, f"Du er nu tilmeldt {subject.title}.")
    return redirect(_safe_next_redirect(request) or reverse("subject-detail", kwargs={"subject_slug": subject.slug}))


@login_required
@require_POST
def subject_unenroll_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    SubjectEnrollment.objects.filter(
        user=request.user,
        subject_slug=subject.slug,
    ).delete()
    messages.info(request, f"Du er afmeldt {subject.title}.")
    return redirect(_safe_next_redirect(request) or reverse("subject-detail", kwargs={"subject_slug": subject.slug}))


@login_required
@require_GET
def subject_detail_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    is_enrolled = SubjectEnrollment.objects.filter(
        user=request.user,
        subject_slug=subject.slug,
    ).exists()
    try:
        subject_path = get_subject_learning_path_snapshot(request.user, subject.slug)
    except Exception:
        logger.exception(
            "Failed to build subject learning path snapshot",
            extra={
                "user_id": request.user.id,
                "subject_slug": subject.slug,
            },
        )
        subject_path = {"lectures": [], "source_meta": {}}
        readings_error = "Læringsstien kunne ikke indlæses lige nu. Prøv igen om et øjeblik."
    else:
        source_meta = subject_path.get("source_meta") if isinstance(subject_path.get("source_meta"), dict) else {}
        readings_error = str(source_meta.get("reading_error") or "").strip() or None

    lecture_payload = _enrich_subject_path_lectures(subject_path.get("lectures", []))
    annotate_subject_lectures_with_marks(
        user=request.user,
        subject_slug=subject.slug,
        lectures=lecture_payload,
    )
    requested_lecture_key = _normalize_subject_lecture_key(request.GET.get("lecture"))
    fallback_lecture_key = ""
    if not requested_lecture_key:
        fallback_lecture_key = _load_last_subject_lecture_key(
            user=request.user,
            subject_slug=subject.slug,
        )
    active_index, active_lecture = _selected_active_lecture(
        lecture_payload,
        requested_lecture_key=requested_lecture_key or fallback_lecture_key,
    )
    if isinstance(active_lecture, dict):
        _save_last_subject_lecture_key(
            user=request.user,
            subject_slug=subject.slug,
            lecture_key=active_lecture.get("lecture_key"),
        )
        active_lecture["quiz_difficulty_slots"] = _quiz_difficulty_slots(active_lecture.get("lecture_assets"))
        active_lecture["podcast_rows"] = _flatten_podcast_rows(active_lecture)
        readings = active_lecture.get("readings") if isinstance(active_lecture.get("readings"), list) else []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            summary = _reading_difficulty_summary(reading)
            reading["difficulty_summary"] = summary
            reading["primary_quiz_url"] = ""
            normalized_reading_key = str(reading.get("reading_key") or "").strip().lower()
            source_filename = _source_filename_or_none(reading.get("source_filename"))
            reading["download_excluded"] = (
                bool(normalized_reading_key)
                and _is_reading_download_excluded(
                    subject_slug=subject.slug,
                    reading_key=normalized_reading_key,
                )
            )
            if source_filename and normalized_reading_key and not reading["download_excluded"]:
                reading["open_url"] = reverse(
                    "subject-open-reading",
                    kwargs={
                        "subject_slug": subject.slug,
                        "reading_key": normalized_reading_key,
                    },
                )
            else:
                reading["open_url"] = ""
            for slot in summary:
                quiz_url = str(slot.get("quiz_url") or "").strip()
                if quiz_url:
                    reading["primary_quiz_url"] = quiz_url
                    break

    return render(
        request,
        "quizzes/subject_detail.html",
        {
            "subject": subject,
            "is_enrolled": is_enrolled,
            "readings_error": readings_error,
            "subject_path_lectures": lecture_payload,
            "lecture_rail_items": _lecture_rail_items(
                subject_slug=subject.slug,
                lectures=lecture_payload,
                active_index=active_index,
            ),
            "active_lecture": active_lecture,
            "reading_tracking_url": reverse("subject-tracking-reading", kwargs={"subject_slug": subject.slug}),
            "podcast_tracking_url": reverse("subject-tracking-podcast", kwargs={"subject_slug": subject.slug}),
        },
    )
