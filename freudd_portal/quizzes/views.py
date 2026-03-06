"""Views for auth, quiz wrapper/raw access, subject dashboards, and state/progress APIs."""

from __future__ import annotations

import json
import logging
import re
import zipfile
from xml.etree import ElementTree
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
from django.views.decorators.http import require_GET, require_http_methods, require_POST, require_safe
from pypdf import PdfReader

from .access_services import user_has_elevated_reading_access, user_has_elevated_slide_access
from .content_services import load_subject_content_manifest
from .forms import SignupForm
from .gamification_services import (
    get_gamification_snapshot,
    get_subject_learning_path_snapshot,
    record_quiz_progress_delta,
)
from .leaderboard_services import (
    active_half_year_semester,
    build_subject_leaderboard_snapshot,
    get_profile_payload,
    update_leaderboard_profile,
)
from .models import (
    QuizProgress,
    SubjectEnrollment,
    UserLeaderboardProfile,
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
    current_leaderboard_semester_key,
    load_quiz_content,
    load_quiz_label_mapping,
    lock_answered_questions_in_state,
    maybe_reset_retry_streak,
    normalize_state_payload,
    question_time_limit_seconds,
    quiz_exists,
    quiz_file_path,
    quiz_question_count,
    update_leaderboard_best,
    upsert_progress_from_state,
)
from .subject_services import SubjectCatalog, load_subject_catalog, resolve_subject_paths
from .tracking_services import (
    annotate_subject_lectures_with_marks,
    personal_tracking_summary_for_user,
    set_podcast_mark,
    set_reading_mark,
    subject_tracking_index,
)
logger = logging.getLogger(__name__)
MAX_STATE_BYTES = 5_000_000
QUIZ_DISPLAY_POINTS_MAX = 150
QUIZ_POINTS_MAX_PER_QUESTION = 120
QUIZ_SLOT_STATE_LABELS_DA = {
    "not_started": "",
    "completed": "Fuldført",
}
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
LEADERBOARD_TAB_ICON_BY_SUBJECT = {
    "personlighedspsykologi": "psychology",
    "udviklingspsykologi": "child_care",
    "kognitionspsykologi": "memory",
    "socialpsykologi": "groups",
}
LECTURE_KEY_DISPLAY_RE = re.compile(r"^W(?P<week>\d{1,2})L(?P<lecture>\d+)$", re.IGNORECASE)
LECTURE_META_SUFFIX_RE = re.compile(
    r"\s*\((?:forelæsning|forelaesning)\s+\d+(?:\s*,\s*\d{4}-\d{2}-\d{2})?\)\s*$",
    re.IGNORECASE,
)
LECTURE_DATE_SUFFIX_RE = re.compile(r"\s*\(\d{4}-\d{2}-\d{2}\)\s*$")
QUIZ_CFG_BLOCK_RE = re.compile(r"\{(?P<body>[^{}]+)\}")
QUIZ_CFG_PAIR_RE = re.compile(r"(?P<key>[a-z0-9._:+-]+)=(?P<value>[^{}\s]+)", re.IGNORECASE)
QUIZ_FILE_SUFFIX_RE = re.compile(r"\.(?:mp3|m4a|wav|aac|flac|ogg|json|html)$", re.IGNORECASE)
QUIZ_LANGUAGE_TAG_RE = re.compile(r"\[(?P<lang>[A-Za-z]{2,5})\]")
SOURCE_FILENAME_SEPARATORS_RE = re.compile(r"[\\/]+")
QUIZ_BRIEF_PREFIX_RE = re.compile(r"^\s*\[brief\]\s*", re.IGNORECASE)
QUIZ_LECTURE_KEY_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
MULTISPACE_RE = re.compile(r"\s+")
SLIDE_HINT_RE = re.compile(
    r"\b(?:slide|slides|powerpoint|pptx?|slidedeck|slide\s+deck)\b",
    re.IGNORECASE,
)
SEMINARHOLD_HINT_RE = re.compile(r"\bseminar(?:hold)?\b", re.IGNORECASE)
OVELSESHOLD_HINT_RE = re.compile(
    r"\b(?:øvelseshold|ovelseshold|øvelse(?:shold)?|exercise(?:\s*group)?)\b",
    re.IGNORECASE,
)
SLIDE_SOURCE_EXTENSIONS = {".ppt", ".pptx", ".key", ".odp"}
SPOTIFY_EPISODE_ID_RE = re.compile(
    r"^https://open\.spotify\.com/episode/(?P<episode_id>[A-Za-z0-9]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
SUBJECT_READING_KEY_RE = re.compile(r"^[a-z0-9-]+$")
SUBJECT_SLIDE_KEY_RE = re.compile(r"^[a-z0-9-]+$")
SUBJECT_LECTURE_KEY_RE = re.compile(r"^W\d{2}L\d+$", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
LEADERBOARD_RANK_LOOKUP_LIMIT = 5000
SLIDE_GROUP_TITLES = {
    "lecture": "slides fra forelæsning",
    "seminar": "slides fra seminarhold",
    "exercise": "slides fra øvelseshold",
}
PUBLIC_OPEN_SLIDE_CATEGORIES = {"lecture"}
_READING_EXCLUSION_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "data": {},
}
_SLIDES_CATALOG_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "data": {},
}
READING_TEXT_CHAR_LIMIT = 200_000
READING_TEXT_PAGE_LIMIT = 60


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


def _safe_back_url(request: HttpRequest, *, fallback_url: str) -> str:
    return _safe_next_redirect(request) or _safe_referer_redirect(request) or fallback_url


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


def _quiz_slot_state_from_progress(progress: QuizProgress | None) -> str:
    if progress is None:
        return "not_started"
    status = str(progress.status or QuizProgress.Status.IN_PROGRESS).strip().lower()
    if status == QuizProgress.Status.COMPLETED:
        return "completed"
    return "not_started"


def _display_points_from_raw_score(*, raw_points: int, question_count: int) -> int:
    total_questions = max(0, int(question_count))
    if total_questions <= 0:
        return 0
    raw_max = total_questions * QUIZ_POINTS_MAX_PER_QUESTION
    if raw_max <= 0:
        return 0
    normalized = round((max(0, int(raw_points)) / raw_max) * QUIZ_DISPLAY_POINTS_MAX)
    return max(0, min(QUIZ_DISPLAY_POINTS_MAX, int(normalized)))


def _build_chatgpt_prompt_for_reading(*, pdf_url: object) -> str:
    normalized_pdf_url = str(pdf_url or "").strip()
    if not normalized_pdf_url:
        return ""
    return "\n".join(
        (
            normalized_pdf_url,
            "Jeg studerer psykologi på universitetet. Hjælp mig med denne tekst.",
        )
    )


def _annotate_quiz_difficulty_slots_for_user(
    *,
    user,
    slots: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not slots:
        return []

    quiz_ids = [
        str(item.get("quiz_id") or "").strip().lower()
        for item in slots
        if str(item.get("quiz_id") or "").strip()
    ]
    progress_by_quiz_id: dict[str, QuizProgress] = {}
    if quiz_ids:
        progress_rows = QuizProgress.objects.filter(user=user, quiz_id__in=quiz_ids)
        progress_by_quiz_id = {
            str(row.quiz_id or "").strip().lower(): row
            for row in progress_rows
            if str(row.quiz_id or "").strip()
        }

    quiz_payload_cache: dict[str, dict[str, object] | None] = {}
    enriched_slots: list[dict[str, object]] = []
    for index, slot in enumerate(slots, start=1):
        slot_copy = dict(slot)
        difficulty_label = str(slot_copy.get("label") or "").strip() or "Quiz"
        quiz_id = str(slot_copy.get("quiz_id") or "").strip().lower()
        progress = progress_by_quiz_id.get(quiz_id) if quiz_id else None
        state_key = _quiz_slot_state_from_progress(progress)
        question_count = _safe_non_negative_int(slot_copy.get("question_count"))
        correct_answers = 0
        raw_points = 0

        slot_copy["display_index"] = index
        slot_copy["title"] = f"{difficulty_label} quiz"
        slot_copy["state_key"] = state_key
        slot_copy["state_label"] = QUIZ_SLOT_STATE_LABELS_DA.get(state_key, "")
        slot_copy["has_attempt"] = progress is not None
        slot_copy["has_metrics"] = False
        slot_copy["meta_line"] = slot_copy["state_label"]

        if progress is not None:
            best_question_count = _safe_non_negative_int(progress.leaderboard_best_question_count)
            best_correct_answers = _safe_non_negative_int(progress.leaderboard_best_correct_answers)
            raw_points = _safe_non_negative_int(progress.leaderboard_best_score)

            if best_question_count > 0:
                question_count = best_question_count
                correct_answers = max(0, min(best_correct_answers, best_question_count))
            else:
                progress_question_count = _safe_non_negative_int(progress.question_count)
                if progress_question_count > 0:
                    question_count = progress_question_count
                if best_correct_answers > 0 and question_count > 0:
                    correct_answers = max(0, min(best_correct_answers, question_count))

                if quiz_id and isinstance(progress.state_json, dict):
                    if quiz_id not in quiz_payload_cache:
                        try:
                            quiz_payload_cache[quiz_id] = load_quiz_content(quiz_id)
                        except Exception:
                            logger.exception(
                                "Failed to load quiz content for subject slot",
                                extra={
                                    "user_id": user.id,
                                    "quiz_id": quiz_id,
                                },
                            )
                            quiz_payload_cache[quiz_id] = None
                    quiz_payload = quiz_payload_cache.get(quiz_id)
                    if isinstance(quiz_payload, dict):
                        outcome = compute_quiz_outcome(state_payload=progress.state_json, quiz_payload=quiz_payload)
                        outcome_question_count = _safe_non_negative_int(outcome.question_count)
                        if outcome_question_count > 0:
                            question_count = outcome_question_count
                            correct_answers = max(
                                0,
                                min(_safe_non_negative_int(outcome.correct_answers), outcome_question_count),
                            )

        if raw_points <= 0 and question_count > 0 and correct_answers > 0:
            raw_points = correct_answers * 100

        if question_count > 0:
            display_points = (
                _display_points_from_raw_score(
                    raw_points=raw_points,
                    question_count=question_count,
                )
                if raw_points > 0
                else 0
            )
            slot_copy["has_metrics"] = True
            slot_copy["correct_answers"] = correct_answers
            slot_copy["question_count"] = question_count
            slot_copy["display_points_earned"] = display_points
            slot_copy["display_points_total"] = QUIZ_DISPLAY_POINTS_MAX
            slot_copy["meta_line"] = (
                f"{correct_answers}/{question_count} rigtige"
                f" • {display_points}/{QUIZ_DISPLAY_POINTS_MAX} point"
            )

        enriched_slots.append(slot_copy)

    return enriched_slots


def _annotate_quiz_difficulty_slots_for_anonymous(*, slots: list[dict[str, object]]) -> list[dict[str, object]]:
    if not slots:
        return []

    enriched_slots: list[dict[str, object]] = []
    for index, slot in enumerate(slots, start=1):
        slot_copy = dict(slot)
        difficulty_label = str(slot_copy.get("label") or "").strip() or "Quiz"
        question_count = _safe_non_negative_int(slot_copy.get("question_count"))

        slot_copy["display_index"] = index
        slot_copy["title"] = f"{difficulty_label} quiz"
        slot_copy["state_key"] = "not_started"
        slot_copy["state_label"] = QUIZ_SLOT_STATE_LABELS_DA.get("not_started", "")
        slot_copy["has_attempt"] = False
        slot_copy["has_metrics"] = False
        slot_copy["meta_line"] = slot_copy["state_label"]

        if question_count > 0:
            slot_copy["has_metrics"] = True
            slot_copy["correct_answers"] = 0
            slot_copy["question_count"] = question_count
            slot_copy["display_points_earned"] = 0
            slot_copy["display_points_total"] = QUIZ_DISPLAY_POINTS_MAX
            slot_copy["meta_line"] = f"0/{question_count} rigtige • 0/{QUIZ_DISPLAY_POINTS_MAX} point"

        enriched_slots.append(slot_copy)

    return enriched_slots


def _visible_quiz_difficulty_slots(slots: object) -> list[dict[str, object]]:
    if not isinstance(slots, list):
        return []
    visible: list[dict[str, object]] = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        quiz_url = str(slot.get("quiz_url") or "").strip()
        state_key = str(slot.get("state_key") or "not_started").strip().lower() or "not_started"
        if quiz_url or state_key == "completed":
            visible.append(slot)
    return visible


def _active_lecture_quiz_progress_totals(lecture: object) -> dict[str, int]:
    totals = {
        "total_quizzes": 0,
        "perfect_quizzes": 0,
        "taken_quizzes": 0,
        "correct_answers": 0,
        "total_questions": 0,
        "points_earned": 0,
        "points_total": 0,
    }
    if not isinstance(lecture, dict):
        return totals

    slots = lecture.get("quiz_difficulty_slots") if isinstance(lecture.get("quiz_difficulty_slots"), list) else []
    referenced_slots = 0

    for slot in slots:
        if not isinstance(slot, dict):
            continue
        quiz_id = str(slot.get("quiz_id") or "").strip()
        quiz_url = str(slot.get("quiz_url") or "").strip()
        has_attempt = bool(slot.get("has_attempt"))
        state_key = str(slot.get("state_key") or "").strip().lower()

        if quiz_id or quiz_url or has_attempt or state_key == "completed":
            referenced_slots += 1

        if has_attempt:
            totals["taken_quizzes"] += 1

        question_count = _safe_non_negative_int(slot.get("question_count"))
        correct_answers = max(0, min(_safe_non_negative_int(slot.get("correct_answers")), question_count))
        totals["correct_answers"] += correct_answers
        totals["total_questions"] += question_count

        display_points_total = _safe_non_negative_int(slot.get("display_points_total"))
        if question_count > 0 and display_points_total <= 0:
            display_points_total = QUIZ_DISPLAY_POINTS_MAX
        display_points_earned = max(
            0,
            min(_safe_non_negative_int(slot.get("display_points_earned")), display_points_total),
        )
        totals["points_earned"] += display_points_earned
        totals["points_total"] += display_points_total

        if has_attempt and question_count > 0 and correct_answers >= question_count:
            totals["perfect_quizzes"] += 1

    declared_total = _safe_non_negative_int(lecture.get("total_quizzes"))
    totals["total_quizzes"] = max(
        declared_total,
        referenced_slots,
        totals["taken_quizzes"],
        totals["perfect_quizzes"],
    )
    totals["taken_quizzes"] = min(totals["taken_quizzes"], totals["total_quizzes"])
    totals["perfect_quizzes"] = min(totals["perfect_quizzes"], totals["taken_quizzes"])

    return totals


def _leaderboard_tab_icon(subject_slug: str) -> str:
    slug = str(subject_slug or "").strip().lower()
    return LEADERBOARD_TAB_ICON_BY_SUBJECT.get(slug, "school")


def _subject_or_404(catalog: SubjectCatalog, subject_slug: str):
    subject = catalog.active_subject_by_slug(subject_slug)
    if subject is None:
        raise Http404("Fag ikke fundet")
    return subject


def _source_filename_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    raw_candidate = Path(text)
    if raw_candidate.is_absolute():
        return None
    if ".." in text and ("/" in text or "\\" in text):
        return None
    text = SOURCE_FILENAME_SEPARATORS_RE.sub("-", text).strip()
    candidate = Path(text)
    if candidate.name != text:
        return None
    if ".." in candidate.parts:
        return None
    return text


def _slide_category_key(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"lecture", "forelaesning", "forelæsning"}:
        return "lecture"
    if raw in {"seminar", "seminarhold"}:
        return "seminar"
    if raw in {"exercise", "ovelse", "øvelse", "ovelseshold", "øvelseshold"}:
        return "exercise"
    return ""


def _is_direct_slide_open_allowed(subcategory: object, *, user: object | None = None) -> bool:
    category = _slide_category_key(subcategory)
    return category in PUBLIC_OPEN_SLIDE_CATEGORIES or user_has_elevated_slide_access(user)


def _slide_catalog_path(*, subject_slug: str) -> Path | None:
    path = resolve_subject_paths(subject_slug).slides_catalog_path
    raw_value = str(path).strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def _slide_files_root(*, subject_slug: str) -> Path | None:
    path = resolve_subject_paths(subject_slug).slides_files_root
    raw_value = str(path).strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def _load_subject_slides_catalog(*, subject_slug: str) -> dict[str, object]:
    path = _slide_catalog_path(subject_slug=subject_slug)
    if path is None:
        return {}
    if not path.exists():
        return {}

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Unable to stat slides catalog: %s", path, exc_info=True)
        return {}

    cache_hit = (
        _SLIDES_CATALOG_CACHE.get("path") == str(path)
        and _SLIDES_CATALOG_CACHE.get("mtime") == mtime
        and isinstance(_SLIDES_CATALOG_CACHE.get("data"), dict)
    )
    if cache_hit:
        return dict(_SLIDES_CATALOG_CACHE["data"])

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to read slides catalog: %s", path, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        return {}

    _SLIDES_CATALOG_CACHE["path"] = str(path)
    _SLIDES_CATALOG_CACHE["mtime"] = mtime
    _SLIDES_CATALOG_CACHE["data"] = payload
    return dict(payload)


def _slide_title_from_source_filename(value: object) -> str:
    source_filename = _source_filename_or_none(value)
    if not source_filename:
        return "Slides"
    stem = Path(source_filename).stem
    title = MULTISPACE_RE.sub(" ", stem.replace("_", " ").replace("-", " ")).strip()
    return title or source_filename


def _slide_catalog_entries_for_lecture(
    *,
    subject_slug: str,
    lecture_key: str,
) -> list[dict[str, str]]:
    payload = _load_subject_slides_catalog(subject_slug=subject_slug)
    if not payload:
        return []

    expected_subject_slug = str(payload.get("subject_slug") or "").strip().lower()
    if expected_subject_slug and expected_subject_slug != str(subject_slug or "").strip().lower():
        return []

    normalized_lecture_key = str(lecture_key or "").strip().upper()
    if not SUBJECT_LECTURE_KEY_RE.match(normalized_lecture_key):
        return []

    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        return []

    entries: list[dict[str, str]] = []
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        raw_lecture_key = str(raw_slide.get("lecture_key") or "").strip().upper()
        if raw_lecture_key != normalized_lecture_key:
            continue
        slide_key = str(raw_slide.get("slide_key") or "").strip().lower()
        if not SUBJECT_SLIDE_KEY_RE.match(slide_key):
            continue
        category = _slide_category_key(raw_slide.get("subcategory"))
        if not category:
            continue
        source_filename = _source_filename_or_none(raw_slide.get("source_filename"))
        if not source_filename:
            continue
        title = str(raw_slide.get("title") or "").strip() or _slide_title_from_source_filename(source_filename)
        entries.append(
            {
                "slide_key": slide_key,
                "lecture_key": raw_lecture_key,
                "subcategory": category,
                "source_filename": source_filename,
                "title": title,
            }
        )
    return entries


def _slide_file_path_or_404(
    *,
    subject_slug: str,
    lecture_key: str,
    subcategory: str,
    source_filename: str,
    user: object | None = None,
) -> Path:
    lecture = str(lecture_key or "").strip().upper()
    if not SUBJECT_LECTURE_KEY_RE.match(lecture):
        raise Http404("Slide ikke fundet i fagets læringssti.")
    category = _slide_category_key(subcategory)
    if not category:
        raise Http404("Slide ikke fundet i fagets læringssti.")
    if not _is_direct_slide_open_allowed(category, user=user):
        raise Http404("Slide-filen kunne ikke tilgås.")
    normalized_source_filename = _source_filename_or_none(source_filename)
    if not normalized_source_filename:
        raise Http404("Slide-filen kunne ikke tilgås.")

    root = _slide_files_root(subject_slug=subject_slug)
    if root is None:
        raise Http404("Slide-filer kunne ikke tilgås.")
    try:
        resolved_root = root.resolve()
    except OSError as exc:
        raise Http404("Slide-filer kunne ikke tilgås.") from exc

    candidate = resolved_root / lecture / category / normalized_source_filename
    try:
        resolved_candidate = candidate.resolve()
    except OSError as exc:
        raise Http404("Slide-filen kunne ikke tilgås.") from exc

    if resolved_root not in resolved_candidate.parents:
        raise Http404("Slide-filen kunne ikke tilgås.")
    if not resolved_candidate.is_file():
        raise Http404("Slide-filen blev ikke fundet.")
    return resolved_candidate


def _find_slide_catalog_entry(
    *,
    subject_slug: str,
    slide_key: str,
) -> dict[str, str] | None:
    normalized_slide_key = str(slide_key or "").strip().lower()
    if not SUBJECT_SLIDE_KEY_RE.match(normalized_slide_key):
        return None

    payload = _load_subject_slides_catalog(subject_slug=subject_slug)
    if not payload:
        return None
    expected_subject_slug = str(payload.get("subject_slug") or "").strip().lower()
    if expected_subject_slug and expected_subject_slug != str(subject_slug or "").strip().lower():
        return None

    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        return None

    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        candidate_slide_key = str(raw_slide.get("slide_key") or "").strip().lower()
        if candidate_slide_key != normalized_slide_key:
            continue
        lecture_key = str(raw_slide.get("lecture_key") or "").strip().upper()
        if not SUBJECT_LECTURE_KEY_RE.match(lecture_key):
            continue
        category = _slide_category_key(raw_slide.get("subcategory"))
        if not category:
            continue
        source_filename = _source_filename_or_none(raw_slide.get("source_filename"))
        if not source_filename:
            continue
        return {
            "slide_key": candidate_slide_key,
            "lecture_key": lecture_key,
            "subcategory": category,
            "source_filename": source_filename,
            "title": str(raw_slide.get("title") or "").strip() or _slide_title_from_source_filename(source_filename),
        }
    return None


def _reading_file_path_or_404(*, subject_slug: str, lecture_key: str, source_filename: str) -> Path:
    lecture = str(lecture_key or "").strip().upper()
    if not SUBJECT_LECTURE_KEY_RE.match(lecture):
        raise Http404("Tekst ikke fundet i fagets læringssti.")

    root = resolve_subject_paths(subject_slug).reading_files_root
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


def _find_reading_source_in_lectures(
    *,
    lectures: object,
    normalized_reading_key: str,
) -> tuple[str | None, str | None]:
    lecture_rows = lectures if isinstance(lectures, list) else []
    for lecture in lecture_rows:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        if not lecture_key:
            continue
        readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            candidate_key = str(reading.get("reading_key") or "").strip().lower()
            if candidate_key != normalized_reading_key:
                continue
            source_filename = _source_filename_or_none(reading.get("source_filename"))
            return lecture_key, source_filename
    return None, None


def _resolve_subject_reading_file_or_404(
    request: HttpRequest,
    *,
    subject_slug: str,
    reading_key: str,
) -> tuple[object, str, str, Path]:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)

    normalized_reading_key = str(reading_key or "").strip().lower()
    if not SUBJECT_READING_KEY_RE.match(normalized_reading_key):
        raise Http404("Tekst ikke fundet i fagets læringssti.")
    if _is_reading_download_blocked_for_user(
        subject_slug=subject.slug,
        reading_key=normalized_reading_key,
        user=request.user,
    ):
        raise Http404("Tekst ikke fundet i fagets læringssti.")

    if request.user.is_authenticated:
        subject_payload = get_subject_learning_path_snapshot(request.user, subject.slug)
    else:
        subject_payload = load_subject_content_manifest(subject.slug)
    found_lecture_key, found_source_filename = _find_reading_source_in_lectures(
        lectures=subject_payload.get("lectures") if isinstance(subject_payload, dict) else None,
        normalized_reading_key=normalized_reading_key,
    )

    if not found_lecture_key:
        raise Http404("Tekst ikke fundet i fagets læringssti.")
    if not found_source_filename:
        raise Http404("Tekst-filen blev ikke fundet.")

    file_path = _reading_file_path_or_404(
        subject_slug=subject.slug,
        lecture_key=found_lecture_key,
        source_filename=found_source_filename,
    )
    return subject, normalized_reading_key, found_source_filename, file_path


def _extract_pdf_text_for_chatgpt(path: Path) -> tuple[str, bool]:
    try:
        reader = PdfReader(str(path))
    except Exception:
        return "", False

    parts: list[str] = []
    char_count = 0
    truncated = False
    for page_index, page in enumerate(reader.pages):
        if page_index >= READING_TEXT_PAGE_LIMIT:
            truncated = True
            break
        try:
            page_text = str(page.extract_text() or "").strip()
        except Exception:
            continue
        if not page_text:
            continue
        remaining = READING_TEXT_CHAR_LIMIT - char_count
        if remaining <= 0:
            truncated = True
            break
        clipped = page_text[:remaining]
        if len(clipped) < len(page_text):
            truncated = True
        parts.append(clipped)
        char_count += len(clipped)
    return "\n\n".join(parts).strip(), truncated


def _extract_docx_text_for_chatgpt(path: Path) -> tuple[str, bool]:
    try:
        with zipfile.ZipFile(path) as archive:
            raw_xml = archive.read("word/document.xml")
    except Exception:
        return "", False

    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return "", False

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    char_count = 0
    truncated = False
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [str(node.text) for node in paragraph.findall(".//w:t", namespace) if node.text]
        if not fragments:
            continue
        text = "".join(fragments).strip()
        if not text:
            continue
        remaining = READING_TEXT_CHAR_LIMIT - char_count
        if remaining <= 0:
            truncated = True
            break
        clipped = text[:remaining]
        if len(clipped) < len(text):
            truncated = True
        paragraphs.append(clipped)
        char_count += len(clipped)
    return "\n\n".join(paragraphs).strip(), truncated


def _text_payload_for_chatgpt_reading(*, title: str, text: str, source_url: str, truncated: bool) -> str:
    body = text.strip() or "Ingen læsbar tekst kunne udtrækkes automatisk fra filen."
    lines = [
        f"Titel: {title}",
        f"Kilde: {source_url}",
        "",
    ]
    if truncated:
        lines.append(
            f"Bemærk: Teksten er afkortet til de første {READING_TEXT_CHAR_LIMIT} tegn "
            f"eller {READING_TEXT_PAGE_LIMIT} sider."
        )
        lines.append("")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


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


def _load_reading_download_exclusions(path: Path) -> dict[str, set[str]]:
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
    exclusions_path = resolve_subject_paths(subject_slug).reading_download_exclusions_path
    by_subject = _load_reading_download_exclusions(exclusions_path)
    excluded = by_subject.get(subject_slug, set())
    return reading_key in excluded


def _is_reading_download_blocked_for_user(
    *,
    subject_slug: str,
    reading_key: str,
    user: object | None,
) -> bool:
    if not _is_reading_download_excluded(subject_slug=subject_slug, reading_key=reading_key):
        return False
    return not user_has_elevated_reading_access(user)


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


def _quiz_subject_slug(quiz_id: str) -> str:
    label = load_quiz_label_mapping().get(str(quiz_id or "").strip().lower())
    candidate = str(label.subject_slug or "").strip().lower() if label else ""
    if not SUBJECT_SLUG_RE.match(candidate):
        return ""
    return candidate


def _quiz_cup_url(*, subject_slug: str) -> str:
    slug = str(subject_slug or "").strip().lower()
    if not SUBJECT_SLUG_RE.match(slug):
        return ""
    return reverse("leaderboard-subject", kwargs={"subject_slug": slug})


def _quiz_cup_public_alias(user) -> str:
    profile = UserLeaderboardProfile.objects.filter(user=user, is_public=True).first()
    return str(profile.public_alias if profile else "").strip()


def _quiz_cup_rank_for_alias(
    *,
    subject_slug: str,
    public_alias: str,
    semester,
) -> tuple[int | None, int]:
    alias = str(public_alias or "").strip()
    slug = str(subject_slug or "").strip().lower()
    if not alias or not SUBJECT_SLUG_RE.match(slug):
        return (None, 0)
    snapshot = build_subject_leaderboard_snapshot(
        subject_slug=slug,
        limit=LEADERBOARD_RANK_LOOKUP_LIMIT,
        semester=semester,
    )
    participant_count = _safe_non_negative_int(snapshot.get("participant_count"))
    entries = snapshot.get("entries") if isinstance(snapshot.get("entries"), list) else []
    alias_casefold = alias.casefold()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("alias") or "").strip().casefold() != alias_casefold:
            continue
        rank = _safe_non_negative_int(entry.get("rank"))
        return ((rank if rank > 0 else None), participant_count)
    return (None, participant_count)


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
    cleaned_title = LECTURE_DATE_SUFFIX_RE.sub("", cleaned_title).strip()
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


def _lecture_mobile_rail_label(
    *,
    lecture_key: object,
    lecture_display_label: object,
    index: int,
) -> str:
    key_text = str(lecture_key or "").strip().upper()
    match = LECTURE_KEY_DISPLAY_RE.match(key_text)
    if match:
        week = int(match.group("week"))
        lecture = int(match.group("lecture"))
        return f"U{week} · F{lecture}"

    label_text = str(lecture_display_label or "").strip()
    if label_text:
        return re.sub(r"\s+", " ", label_text)
    if key_text:
        return key_text
    return f"Lektion {index}"


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


def _quiz_meta_chips(*, cfg_tags: dict[str, str], language: str, title: str) -> list[str]:
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

    normalized_title = str(title or "").strip().casefold()
    media_type = str(cfg_tags.get("type") or "").strip().lower()
    if media_type in {"audio", "quiz"}:
        _add("Tekstquiz")
    elif media_type:
        _add(media_type.replace("-", " ").replace("_", " ").title())
    elif normalized_title:
        _add("Tekstquiz")

    if "alle kilder" in normalized_title:
        _add("Alle tekster")

    if language:
        _add(language)

    return chips


def _quiz_display_context(*, episode_title: object, quiz_id: str) -> dict[str, object]:
    module_label, title, cfg_tags, language = _quiz_core_parts(episode_title)
    meta_chips = _quiz_meta_chips(cfg_tags=cfg_tags, language=language, title=title)
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
        slides_payload: list[dict[str, object]] = []
        has_slide_quizzes = False
        has_slide_podcasts = False
        slides = lecture_copy.get("slides")
        if isinstance(slides, list):
            for slide in slides:
                if not isinstance(slide, dict):
                    continue
                slide_copy = dict(slide)
                slide_copy["assets"] = _compact_asset_links(
                    slide_copy.get("assets"),
                    question_count_by_quiz_id=question_count_by_quiz_id,
                )
                assets = slide_copy.get("assets") if isinstance(slide_copy.get("assets"), dict) else {}
                if assets.get("quizzes"):
                    has_slide_quizzes = True
                if assets.get("podcasts"):
                    has_slide_podcasts = True
                slides_payload.append(slide_copy)
        lecture_copy["slides"] = slides_payload
        lecture_copy["has_reading_quizzes"] = has_reading_quizzes
        lecture_copy["has_reading_podcasts"] = has_reading_podcasts
        lecture_copy["has_slide_quizzes"] = has_slide_quizzes
        lecture_copy["has_slide_podcasts"] = has_slide_podcasts
        lecture_copy["has_any_quizzes"] = has_lecture_quizzes or has_reading_quizzes or has_slide_quizzes
        lecture_copy["has_any_podcasts"] = has_lecture_podcasts or has_reading_podcasts or has_slide_podcasts
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
            "quiz_id": str(quiz_by_difficulty.get("easy", {}).get("quiz_id") or "").strip().lower(),
            "quiz_url": str(quiz_by_difficulty.get("easy", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("easy", {}).get("question_count"),
        },
        {
            "difficulty": "medium",
            "label": "Mellem",
            "chip": "M",
            "quiz_id": str(quiz_by_difficulty.get("medium", {}).get("quiz_id") or "").strip().lower(),
            "quiz_url": str(quiz_by_difficulty.get("medium", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("medium", {}).get("question_count"),
        },
        {
            "difficulty": "hard",
            "label": "Svær",
            "chip": "S",
            "quiz_id": str(quiz_by_difficulty.get("hard", {}).get("quiz_id") or "").strip().lower(),
            "quiz_url": str(quiz_by_difficulty.get("hard", {}).get("quiz_url") or "").strip(),
            "question_count": quiz_by_difficulty.get("hard", {}).get("question_count"),
        },
    ]


def _reading_difficulty_summary(reading: object) -> list[dict[str, object]]:
    if not isinstance(reading, dict):
        return _quiz_difficulty_slots({})
    assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
    return _quiz_difficulty_slots(assets)


def _slide_difficulty_summary(slide: object) -> list[dict[str, object]]:
    if not isinstance(slide, dict):
        return _quiz_difficulty_slots({})
    assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
    return _quiz_difficulty_slots(assets)


def _podcast_display_title(value: object) -> str:
    title_text = str(value or "").strip()
    if not title_text:
        return "Podcast episode"
    parts = [part.strip() for part in title_text.split("·") if part.strip()]
    if len(parts) >= 3:
        return parts[2]
    return title_text


def _slide_hint_text(*, reading_title: object, source_filename: object) -> str:
    title_text = str(reading_title or "").strip()
    source_text = str(source_filename or "").strip()
    parts: list[str] = []
    if title_text:
        parts.append(title_text)
    if source_text:
        parts.append(source_text)
        parts.append(Path(source_text).stem)
    return " ".join(parts)


def _is_slide_reading(*, reading_title: object, source_filename: object) -> bool:
    hint_text = _slide_hint_text(reading_title=reading_title, source_filename=source_filename)
    if hint_text and SLIDE_HINT_RE.search(hint_text):
        return True
    source_text = str(source_filename or "").strip()
    if not source_text:
        return False
    return Path(source_text).suffix.lower() in SLIDE_SOURCE_EXTENSIONS


def _slide_group_key(*, reading_title: object, source_filename: object) -> str:
    hint_text = _slide_hint_text(reading_title=reading_title, source_filename=source_filename)
    if SEMINARHOLD_HINT_RE.search(hint_text):
        return "seminar"
    if OVELSESHOLD_HINT_RE.search(hint_text):
        return "exercise"
    return "lecture"


def _slide_groups_for_lecture(
    lecture: object,
    *,
    subject_slug: str,
    user: object | None = None,
) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {
        "lecture": {
            "group_key": "lecture",
            "group_title": SLIDE_GROUP_TITLES["lecture"],
            "items": [],
        },
        "seminar": {
            "group_key": "seminar",
            "group_title": SLIDE_GROUP_TITLES["seminar"],
            "items": [],
        },
        "exercise": {
            "group_key": "exercise",
            "group_title": SLIDE_GROUP_TITLES["exercise"],
            "items": [],
        },
    }
    if not isinstance(lecture, dict):
        return []

    seen_catalog_keys: set[tuple[str, str]] = set()
    lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
    slide_manifest_by_key: dict[str, dict[str, object]] = {}
    lecture_slides = lecture.get("slides") if isinstance(lecture.get("slides"), list) else []
    for slide_item in lecture_slides:
        if not isinstance(slide_item, dict):
            continue
        slide_key = str(slide_item.get("slide_key") or "").strip().lower()
        if not slide_key:
            continue
        slide_manifest_by_key[slide_key] = slide_item
    for slide in _slide_catalog_entries_for_lecture(subject_slug=subject_slug, lecture_key=lecture_key):
        group_key = _slide_category_key(slide.get("subcategory"))
        if not group_key:
            continue
        source_filename = str(slide.get("source_filename") or "").strip()
        seen_catalog_keys.add((group_key, source_filename.casefold()))
        manifest_slide = slide_manifest_by_key.get(str(slide.get("slide_key") or "").strip().lower(), {})
        open_url = ""
        if _is_direct_slide_open_allowed(group_key, user=user):
            open_url = reverse(
                "subject-open-slide",
                kwargs={
                    "subject_slug": str(subject_slug or "").strip().lower(),
                    "slide_key": str(slide.get("slide_key") or "").strip(),
                },
            )
        slide_summary = _slide_difficulty_summary(manifest_slide)
        if user is not None and getattr(user, "is_authenticated", False):
            slide_summary = _annotate_quiz_difficulty_slots_for_user(user=user, slots=slide_summary)
        else:
            slide_summary = _annotate_quiz_difficulty_slots_for_anonymous(slots=slide_summary)
        item = {
            "slide_key": str(slide.get("slide_key") or "").strip(),
            "reading_key": "",
            "reading_title": str(slide.get("title") or "").strip() or _slide_title_from_source_filename(source_filename),
            "source_filename": source_filename,
            "open_url": open_url,
            "visible_difficulty_summary": _visible_quiz_difficulty_slots(slide_summary),
        }
        group = groups.get(group_key, groups["lecture"])
        group_items = group.get("items")
        if isinstance(group_items, list):
            group_items.append(item)

    # Fallback: preserve support for legacy slide detection from reading rows.
    readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
    for reading in readings:
        if not isinstance(reading, dict):
            continue
        reading_title = str(reading.get("reading_title") or "").strip()
        source_filename = _source_filename_or_none(reading.get("source_filename")) or ""
        if not _is_slide_reading(reading_title=reading_title, source_filename=source_filename):
            continue
        group_key = _slide_group_key(reading_title=reading_title, source_filename=source_filename)
        if source_filename and (group_key, source_filename.casefold()) in seen_catalog_keys:
            continue
        open_url = ""
        if _is_direct_slide_open_allowed(group_key, user=user):
            open_url = str(reading.get("open_pdf_url") or reading.get("open_url") or "").strip()
        item = {
            "slide_key": "",
            "reading_key": str(reading.get("reading_key") or "").strip(),
            "reading_title": reading_title or source_filename or "Slides",
            "source_filename": source_filename,
            "open_url": open_url,
            "visible_difficulty_summary": [],
        }
        group = groups.get(group_key, groups["lecture"])
        group_items = group.get("items")
        if isinstance(group_items, list):
            group_items.append(item)

    ordered_group_keys = ("lecture", "seminar", "exercise")
    for key in ordered_group_keys:
        group = groups[key]
        items = group.get("items")
        if not isinstance(items, list):
            group["items"] = []
            group["count"] = 0
            continue
        items.sort(key=lambda item: str(item.get("reading_title") or "").casefold())
        group["count"] = len(items)

    visible_groups: list[dict[str, object]] = []
    for key in ordered_group_keys:
        group = groups[key]
        items = group.get("items")
        if isinstance(items, list) and items:
            visible_groups.append(group)
    return visible_groups


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

    slides = lecture.get("slides") if isinstance(lecture.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_title = str(slide.get("title") or "").strip() or "Slides"
        slide_key = str(slide.get("slide_key") or "").strip().lower()
        assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
        slide_podcasts = assets.get("podcasts") if isinstance(assets.get("podcasts"), list) else []
        for podcast in slide_podcasts:
            if not isinstance(podcast, dict):
                continue
            rows.append(
                {
                    **podcast,
                    "lecture_key": lecture_key,
                    "reading_key": f"slide:{slide_key}" if slide_key else None,
                    "source_label": slide_title,
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
    preview_mode: bool = False,
    preview_locked_lecture_key: str = "",
) -> list[dict[str, object]]:
    detail_url = reverse("subject-detail", kwargs={"subject_slug": subject_slug})
    locked_lecture_key = _normalize_subject_lecture_key(preview_locked_lecture_key) if preview_mode else ""
    items: list[dict[str, object]] = []
    for index, lecture in enumerate(lectures, start=1):
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        requires_login = bool(
            preview_mode and locked_lecture_key and lecture_key and lecture_key != locked_lecture_key
        )
        login_url = ""
        if requires_login:
            login_next_url = f"{detail_url}?{urlencode({'lecture': lecture_key})}"
            lecture_url = _auth_url_with_next("login", login_next_url)
            login_url = lecture_url
        else:
            query_params: dict[str, str] = {}
            if lecture_key:
                query_params["lecture"] = lecture_key
            if preview_mode and locked_lecture_key:
                query_params["preview"] = "true"
            lecture_url = f"{detail_url}?{urlencode(query_params)}" if query_params else detail_url
        status = str(lecture.get("status") or "").strip().lower()
        items.append(
            {
                "index": index,
                "lecture_key": lecture_key,
                "lecture_url": lecture_url,
                "requires_login": requires_login,
                "login_url": login_url,
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
                "mobile_rail_label": _lecture_mobile_rail_label(
                    lecture_key=lecture.get("lecture_key"),
                    lecture_display_label=lecture.get("lecture_display_label"),
                    index=index,
                ),
            }
        )
    return items


def _quiz_count_from_assets(assets: object) -> int:
    if not isinstance(assets, dict):
        return 0
    quizzes = assets.get("quizzes") if isinstance(assets.get("quizzes"), list) else []
    unique_quiz_ids: set[str] = set()
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        quiz_id = str(quiz.get("quiz_id") or "").strip().lower()
        quiz_url = str(quiz.get("quiz_url") or "").strip()
        if quiz_id:
            unique_quiz_ids.add(f"id:{quiz_id}")
        elif quiz_url:
            unique_quiz_ids.add(f"url:{quiz_url}")
    return len(unique_quiz_ids)


def _anonymous_subject_learning_path_snapshot(subject_slug: str) -> dict[str, object]:
    slug = str(subject_slug or "").strip().lower()
    manifest = load_subject_content_manifest(slug)
    lecture_payload: list[dict[str, object]] = []
    for lecture in manifest.get("lectures") or []:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        if not lecture_key:
            continue
        lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
        readings_payload: list[dict[str, object]] = []
        slide_payload: list[dict[str, object]] = []
        slide_quiz_count = 0
        for reading in lecture.get("readings") or []:
            if not isinstance(reading, dict):
                continue
            reading_key = str(reading.get("reading_key") or "").strip()
            if not reading_key:
                continue
            reading_assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
            reading_quiz_count = _quiz_count_from_assets(reading_assets)
            readings_payload.append(
                {
                    "reading_key": reading_key,
                    "reading_title": str(reading.get("reading_title") or reading_key),
                    "is_missing": bool(reading.get("is_missing", False)),
                    "source_filename": str(reading.get("source_filename") or "").strip() or None,
                    "sequence_index": int(reading.get("sequence_index") or 0),
                    "status": "no_quiz" if reading_quiz_count == 0 else "active",
                    "completed_quizzes": 0,
                    "total_quizzes": reading_quiz_count,
                    "assets": {
                        "quizzes": list(reading_assets.get("quizzes") or []),
                        "podcasts": list(reading_assets.get("podcasts") or []),
                    },
                }
            )
        for slide in lecture.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
            slide_count = _quiz_count_from_assets(slide_assets)
            slide_quiz_count += slide_count
            slide_payload.append(
                {
                    "slide_key": str(slide.get("slide_key") or "").strip().lower(),
                    "subcategory": str(slide.get("subcategory") or "").strip().lower(),
                    "title": str(slide.get("title") or "Slides"),
                    "source_filename": str(slide.get("source_filename") or "").strip() or None,
                    "relative_path": str(slide.get("relative_path") or "").strip() or None,
                    "assets": {
                        "quizzes": list(slide_assets.get("quizzes") or []),
                        "podcasts": list(slide_assets.get("podcasts") or []),
                    },
                    "total_quizzes": slide_count,
                }
            )
        lecture_payload.append(
            {
                "lecture_key": lecture_key,
                "lecture_title": str(lecture.get("lecture_title") or lecture_key),
                "sequence_index": int(lecture.get("sequence_index") or 0),
                "status": "active",
                "completed_quizzes": 0,
                "total_quizzes": _quiz_count_from_assets(lecture_assets) + sum(
                    _quiz_count_from_assets(
                        reading.get("assets") if isinstance(reading, dict) else {}
                    )
                    for reading in readings_payload
                ) + slide_quiz_count,
                "warnings": list(lecture.get("warnings") or []),
                "readings": readings_payload,
                "slides": slide_payload,
                "lecture_assets": {
                    "quizzes": list(lecture_assets.get("quizzes") or []),
                    "podcasts": list(lecture_assets.get("podcasts") or []),
                },
            }
        )
    active_lecture = next((lecture for lecture in lecture_payload if lecture.get("status") == "active"), None)
    return {
        "lectures": lecture_payload,
        "active_lecture": active_lecture,
        "warnings": list(manifest.get("warnings") or []),
        "source_meta": dict(manifest.get("source_meta") or {}),
    }


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
    quiz_subject_slug = (
        str(label.subject_slug or "").strip().lower()
        if label and SUBJECT_SLUG_RE.match(str(label.subject_slug or "").strip().lower())
        else ""
    )
    episode_title = label.episode_title if label else quiz_id
    difficulty_label = _difficulty_label(label.difficulty if label else "unknown")
    quiz_display = _quiz_display_context(episode_title=episode_title, quiz_id=quiz_id)
    quiz_path = reverse("quiz-wrapper", kwargs={"quiz_id": quiz_id})
    fallback_back_url = reverse("progress")
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
        "back_url": _safe_back_url(request, fallback_url=fallback_back_url),
        "quiz_cup_url": _quiz_cup_url(subject_slug=quiz_subject_slug),
        "quiz_subject_slug": quiz_subject_slug,
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
    quiz_subject_slug = _quiz_subject_slug(quiz_id)
    quiz_cup_response_payload: dict[str, object] = {
        "subject_slug": quiz_subject_slug,
        "url": _quiz_cup_url(subject_slug=quiz_subject_slug),
    }

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
    else:
        state_payload = lock_answered_questions_in_state(
            previous_state_payload=progress.state_json if isinstance(progress.state_json, dict) else None,
            state_payload=state_payload,
        )
        computation = compute_progress(state_payload, question_count)
        if progress.attempt_started_at is None:
            progress.attempt_started_at = now

    will_transition_to_completed = (
        previous_status != QuizProgress.Status.COMPLETED
        and computation.status == QuizProgress.Status.COMPLETED
    )
    public_alias = ""
    active_semester = None
    previous_rank: int | None = None
    if will_transition_to_completed:
        public_alias = _quiz_cup_public_alias(request.user)
        if quiz_subject_slug and public_alias:
            active_semester = active_half_year_semester(now=now)
            previous_rank, _ = _quiz_cup_rank_for_alias(
                subject_slug=quiz_subject_slug,
                public_alias=public_alias,
                semester=active_semester,
            )

    upsert_progress_from_state(progress=progress, state_payload=state_payload, computation=computation)

    completion_transition = (
        previous_status != QuizProgress.Status.COMPLETED
        and progress.status == QuizProgress.Status.COMPLETED
    )
    if completion_transition:
        now = timezone.now()
        if not public_alias:
            public_alias = _quiz_cup_public_alias(request.user)
        if active_semester is None:
            active_semester = active_half_year_semester(now=now)

        quiz_payload = load_quiz_content(quiz_id)
        outcome = compute_quiz_outcome(state_payload=state_payload, quiz_payload=quiz_payload)
        duration_ms = compute_attempt_duration_ms(progress, now=now)
        apply_completion_cooldown(progress, now=now)
        semester_key = current_leaderboard_semester_key(now=now)
        score_points = compute_leaderboard_score(
            correct_answers=outcome.correct_answers,
            question_count=outcome.question_count,
            duration_ms=duration_ms,
            question_time_limit_seconds=question_time_limit_seconds(),
        )
        update_leaderboard_best(
            progress=progress,
            semester_key=semester_key,
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
                "leaderboard_semester_key",
                "leaderboard_best_score",
                "leaderboard_best_correct_answers",
                "leaderboard_best_question_count",
                "leaderboard_best_duration_ms",
                "leaderboard_best_reached_at",
                "updated_at",
            ]
        )
        if quiz_subject_slug and public_alias:
            current_rank, participant_count = _quiz_cup_rank_for_alias(
                subject_slug=quiz_subject_slug,
                public_alias=public_alias,
                semester=active_semester,
            )
            rank_change = 0
            if previous_rank and current_rank and current_rank < previous_rank:
                rank_change = previous_rank - current_rank
            quiz_cup_response_payload.update(
                {
                    "previous_rank": previous_rank,
                    "current_rank": current_rank,
                    "rank_change": rank_change,
                    "participant_count": participant_count,
                }
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
            "quiz_cup": quiz_cup_response_payload,
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
    semester = active_half_year_semester()
    active_subject_slugs = {subject.slug for subject in catalog.active_subjects}

    enrolled_slugs = set(
        SubjectEnrollment.objects.filter(user=request.user).values_list("subject_slug", flat=True)
    )
    last_opened_subject_row = (
        UserSubjectLastLecture.objects.filter(
            user=request.user,
            subject_slug__in=active_subject_slugs,
        )
        .only("subject_slug")
        .order_by("-updated_at")
        .first()
    )
    last_opened_subject_slug = (
        str(last_opened_subject_row.subject_slug).strip()
        if last_opened_subject_row is not None
        else ""
    )
    subject_cards: list[dict[str, object]] = []
    subject_tracking_targets: list[dict[str, str]] = []
    for subject in catalog.active_subjects:
        detail_url = reverse("subject-detail", kwargs={"subject_slug": subject.slug})
        subject_cards.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "description": subject.description,
                "is_enrolled": subject.slug in enrolled_slugs,
                "detail_url": detail_url,
                "enroll_url": reverse("subject-enroll", kwargs={"subject_slug": subject.slug}),
                "unenroll_url": reverse("subject-unenroll", kwargs={"subject_slug": subject.slug}),
            }
        )
        subject_tracking_targets.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "detail_url": detail_url,
            }
        )

    quiz_history_enabled = bool(getattr(settings, "FREUDD_PROGRESS_QUIZ_HISTORY_ENABLED", True))
    rows: list[dict[str, object]] = []
    quiz_history_summary = {
        "quiz_count": 0,
        "total_correct_answers": 0,
        "total_question_count": 0,
        "completion_percent": 0,
        "perfect_quiz_count": 0,
        "latest_updated_at": None,
    }
    if quiz_history_enabled:
        label_mapping = load_quiz_label_mapping()
        progress_rows = (
            QuizProgress.objects.filter(user=request.user, completed_at__isnull=False)
            .order_by("-last_attempt_completed_at", "-completed_at", "-updated_at")
        )
        for row in progress_rows:
            label = label_mapping.get(row.quiz_id)
            episode_title = label.episode_title if label else row.quiz_id
            quiz_display = _quiz_display_context(episode_title=episode_title, quiz_id=row.quiz_id)
            difficulty_key = str(label.difficulty if label else "unknown").strip().lower() or "unknown"
            if difficulty_key not in DIFFICULTY_SORT_ORDER:
                difficulty_key = "unknown"
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
                    "difficulty_label": _difficulty_label(difficulty_key),
                    "difficulty_key": difficulty_key,
                    "status": status,
                    "status_label": status.label,
                    "answers_count": score_correct_answers,
                    "question_count": score_question_count,
                    "updated_at": updated_at,
                    "completed_at": row.completed_at,
                    "quiz_url": reverse("quiz-wrapper", kwargs={"quiz_id": row.quiz_id}),
                    "search_text": " ".join(
                        [
                            str(quiz_display.get("title") or ""),
                            str(quiz_display.get("module_label") or ""),
                            " ".join(str(chip or "") for chip in list(quiz_display.get("meta_chips") or [])),
                            row.quiz_id,
                        ]
                    ).lower(),
                }
            )

        total_correct_answers = sum(int(item.get("answers_count") or 0) for item in rows)
        total_question_count = sum(int(item.get("question_count") or 0) for item in rows)
        total_quizzes = len(rows)
        perfect_quizzes = sum(
            1
            for item in rows
            if int(item.get("question_count") or 0) > 0
            and int(item.get("answers_count") or 0) >= int(item.get("question_count") or 0)
        )
        completion_percent = (
            int(round((total_correct_answers / total_question_count) * 100))
            if total_question_count > 0
            else 0
        )
        quiz_history_summary = {
            "quiz_count": total_quizzes,
            "total_correct_answers": total_correct_answers,
            "total_question_count": total_question_count,
            "completion_percent": completion_percent,
            "perfect_quiz_count": perfect_quizzes,
            "latest_updated_at": rows[0]["updated_at"] if rows else None,
        }

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
            "last_opened_subject_slug": last_opened_subject_slug,
            "subjects_error": catalog.error,
            "leaderboard_profile": profile_payload,
            "leaderboard_alias_editing": leaderboard_alias_editing,
            "personal_tracking_by_subject": personal_tracking_by_subject,
            "quiz_history_enabled": quiz_history_enabled,
            "quiz_history_summary": quiz_history_summary,
            "active_semester": {
                "key": semester.key,
                "label": semester.label,
                "start_date_label": semester.start_date_label,
                "end_date_label": semester.end_date_label,
            },
        },
    )


@require_GET
def leaderboard_subject_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    semester = active_half_year_semester()
    snapshot = build_subject_leaderboard_snapshot(
        subject_slug=subject.slug,
        limit=50,
        semester=semester,
    )

    own_profile = None
    if request.user.is_authenticated:
        own_profile = get_profile_payload(request.user)

    entries = snapshot.get("entries") or []
    rank_to_entry = {int(item.get("rank") or 0): item for item in entries if isinstance(item, dict)}
    podium_entries = [rank_to_entry[rank] for rank in (2, 1, 3) if rank in rank_to_entry]
    table_entries = entries

    subject_tabs = [
        {
            "slug": item.slug,
            "title": item.title,
            "icon": _leaderboard_tab_icon(item.slug),
            "url": reverse("leaderboard-subject", kwargs={"subject_slug": item.slug}),
            "is_active": item.slug == subject.slug,
        }
        for item in catalog.active_subjects
    ]

    return render(
        request,
        "quizzes/leaderboard.html",
        {
            "subject": subject,
            "entries": entries,
            "podium_entries": podium_entries,
            "table_entries": table_entries,
            "table_preview_limit": 7,
            "subject_tabs": subject_tabs,
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
        messages.error(request, "; ".join(exc.messages) if exc.messages else "Kunne ikke opdatere scoreboard-profil.")
    else:
        if is_public:
            messages.success(request, "Din scoreboard-profil er nu offentlig.")
        else:
            messages.info(request, "Din scoreboard-profil er nu privat.")

    return redirect(
        _safe_next_redirect(request)
        or _safe_referer_redirect(request)
        or reverse("progress")
    )


@require_safe
def subject_open_slide_view(request: HttpRequest, subject_slug: str, slide_key: str) -> HttpResponse:
    catalog = load_subject_catalog()
    _subject_or_404(catalog, subject_slug)
    entry = _find_slide_catalog_entry(
        subject_slug=subject_slug,
        slide_key=slide_key,
    )
    if entry is None:
        raise Http404("Slide ikke fundet i fagets læringssti.")
    file_path = _slide_file_path_or_404(
        subject_slug=subject_slug,
        lecture_key=entry["lecture_key"],
        subcategory=entry["subcategory"],
        source_filename=entry["source_filename"],
        user=request.user,
    )
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        content_type = "application/pdf"
        as_attachment = False
    elif suffix == ".docx":
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        as_attachment = True
    elif suffix == ".pptx":
        content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        as_attachment = True
    elif suffix == ".ppt":
        content_type = "application/vnd.ms-powerpoint"
        as_attachment = True
    else:
        content_type = "application/octet-stream"
        as_attachment = True

    return FileResponse(
        file_path.open("rb"),
        content_type=content_type,
        as_attachment=as_attachment,
        filename=entry["source_filename"],
    )


@require_safe
def subject_open_reading_view(request: HttpRequest, subject_slug: str, reading_key: str) -> HttpResponse:
    _, _, found_source_filename, file_path = _resolve_subject_reading_file_or_404(
        request,
        subject_slug=subject_slug,
        reading_key=reading_key,
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


@require_safe
def subject_open_reading_pdf_view(request: HttpRequest, subject_slug: str, reading_key: str) -> HttpResponse:
    _, _, found_source_filename, file_path = _resolve_subject_reading_file_or_404(
        request,
        subject_slug=subject_slug,
        reading_key=reading_key,
    )
    if file_path.suffix.lower() != ".pdf":
        raise Http404("PDF ikke fundet for teksten.")
    return FileResponse(
        file_path.open("rb"),
        content_type="application/pdf",
        as_attachment=False,
        filename=found_source_filename,
    )


@require_safe
def subject_open_reading_text_view(request: HttpRequest, subject_slug: str, reading_key: str) -> HttpResponse:
    subject, normalized_reading_key, source_filename, file_path = _resolve_subject_reading_file_or_404(
        request,
        subject_slug=subject_slug,
        reading_key=reading_key,
    )
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        extracted_text, truncated = _extract_pdf_text_for_chatgpt(file_path)
    elif suffix == ".docx":
        extracted_text, truncated = _extract_docx_text_for_chatgpt(file_path)
    else:
        extracted_text, truncated = "", False

    source_url = request.build_absolute_uri(
        reverse(
            "subject-open-reading",
            kwargs={
                "subject_slug": subject.slug,
                "reading_key": normalized_reading_key,
            },
        )
    )
    payload = _text_payload_for_chatgpt_reading(
        title=source_filename,
        text=extracted_text,
        source_url=source_url,
        truncated=truncated,
    )
    response = HttpResponse(payload, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'inline; filename="{source_filename}.txt"'
    return response


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


@require_GET
def subject_detail_view(request: HttpRequest, subject_slug: str) -> HttpResponse:
    catalog = load_subject_catalog()
    subject = _subject_or_404(catalog, subject_slug)
    user_is_authenticated = bool(getattr(request.user, "is_authenticated", False))
    preview_mode = (not user_is_authenticated) and _as_bool(request.GET.get("preview"))
    requested_lecture_key = _normalize_subject_lecture_key(request.GET.get("lecture"))
    if not user_is_authenticated and not preview_mode:
        return redirect(_auth_url_with_next("login", request.get_full_path()))
    if preview_mode and not requested_lecture_key:
        return redirect(_auth_url_with_next("login", request.get_full_path()))

    is_enrolled = False
    if user_is_authenticated:
        is_enrolled = SubjectEnrollment.objects.filter(
            user=request.user,
            subject_slug=subject.slug,
        ).exists()
    try:
        if user_is_authenticated:
            subject_path = get_subject_learning_path_snapshot(request.user, subject.slug)
        else:
            subject_path = _anonymous_subject_learning_path_snapshot(subject.slug)
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
    if user_is_authenticated:
        annotate_subject_lectures_with_marks(
            user=request.user,
            subject_slug=subject.slug,
            lectures=lecture_payload,
        )
    fallback_lecture_key = ""
    if user_is_authenticated and not requested_lecture_key:
        fallback_lecture_key = _load_last_subject_lecture_key(
            user=request.user,
            subject_slug=subject.slug,
        )
    active_index, active_lecture = _selected_active_lecture(
        lecture_payload,
        requested_lecture_key=requested_lecture_key or fallback_lecture_key,
    )
    if preview_mode and isinstance(active_lecture, dict):
        active_lecture_key = _normalize_subject_lecture_key(active_lecture.get("lecture_key"))
        if not active_lecture_key or active_lecture_key != requested_lecture_key:
            return redirect(_auth_url_with_next("login", request.get_full_path()))
    if isinstance(active_lecture, dict):
        if user_is_authenticated:
            _save_last_subject_lecture_key(
                user=request.user,
                subject_slug=subject.slug,
                lecture_key=active_lecture.get("lecture_key"),
            )

            def slot_annotator(slots: list[dict[str, object]]) -> list[dict[str, object]]:
                return _annotate_quiz_difficulty_slots_for_user(
                    user=request.user,
                    slots=slots,
                )
        else:
            def slot_annotator(slots: list[dict[str, object]]) -> list[dict[str, object]]:
                return _annotate_quiz_difficulty_slots_for_anonymous(slots=slots)
        active_lecture["quiz_difficulty_slots"] = slot_annotator(
            _quiz_difficulty_slots(active_lecture.get("lecture_assets")),
        )
        active_lecture["quiz_difficulty_visible_slots"] = _visible_quiz_difficulty_slots(
            active_lecture.get("quiz_difficulty_slots"),
        )
        active_lecture["quiz_progress_totals"] = _active_lecture_quiz_progress_totals(active_lecture)
        active_lecture["podcast_rows"] = _flatten_podcast_rows(active_lecture)
        can_bypass_reading_exclusions = user_has_elevated_reading_access(request.user)
        readings = active_lecture.get("readings") if isinstance(active_lecture.get("readings"), list) else []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            summary = _reading_difficulty_summary(reading)
            annotated_summary = slot_annotator(summary)
            reading["difficulty_summary"] = annotated_summary
            reading["visible_difficulty_summary"] = _visible_quiz_difficulty_slots(annotated_summary)
            reading["primary_quiz_url"] = ""
            reading["chatgpt_prompt"] = ""
            normalized_reading_key = str(reading.get("reading_key") or "").strip().lower()
            source_filename = _source_filename_or_none(reading.get("source_filename"))
            reading["download_excluded"] = (
                bool(normalized_reading_key)
                and _is_reading_download_blocked_for_user(
                    subject_slug=subject.slug,
                    reading_key=normalized_reading_key,
                    user=request.user if can_bypass_reading_exclusions else None,
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
                reading["open_pdf_url"] = (
                    reverse(
                        "subject-open-reading-pdf",
                        kwargs={
                            "subject_slug": subject.slug,
                            "reading_key": normalized_reading_key,
                        },
                    )
                    if Path(source_filename).suffix.lower() == ".pdf"
                    else ""
                )
                if reading["open_pdf_url"]:
                    reading["chatgpt_prompt"] = _build_chatgpt_prompt_for_reading(
                        pdf_url=request.build_absolute_uri(reading["open_pdf_url"]),
                    )
            else:
                reading["open_url"] = ""
                reading["open_pdf_url"] = ""
            for slot in summary:
                quiz_url = str(slot.get("quiz_url") or "").strip()
                if quiz_url:
                    reading["primary_quiz_url"] = quiz_url
                    break
        active_lecture["slide_groups"] = _slide_groups_for_lecture(
            active_lecture,
            subject_slug=subject.slug,
            user=request.user,
        )

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
                preview_mode=preview_mode,
                preview_locked_lecture_key=requested_lecture_key,
            ),
            "active_lecture": active_lecture,
            "reading_tracking_url": reverse("subject-tracking-reading", kwargs={"subject_slug": subject.slug}),
            "podcast_tracking_url": reverse("subject-tracking-podcast", kwargs={"subject_slug": subject.slug}),
        },
    )
