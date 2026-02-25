"""Views for auth, quiz wrapper/raw access, subject dashboards, and state/progress APIs."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import SignupForm
from .gamification_services import (
    get_gamification_snapshot,
    get_subject_learning_path_snapshot,
    record_quiz_progress_delta,
)
from .models import QuizProgress, SubjectEnrollment
from .rate_limit import evaluate_rate_limit
from .services import (
    QUIZ_ID_RE,
    StatePayloadError,
    compute_progress,
    load_quiz_content,
    load_quiz_label_mapping,
    normalize_state_payload,
    quiz_exists,
    quiz_file_path,
    quiz_question_count,
    upsert_progress_from_state,
)
from .subject_services import SubjectCatalog, load_subject_catalog

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


def _compact_asset_links(assets: object) -> dict[str, list[dict[str, object]]]:
    if not isinstance(assets, dict):
        return {"quizzes": [], "podcasts": []}

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
            compact_quizzes.append(
                {
                    **quiz,
                    "difficulty": difficulty,
                    "difficulty_label_da": _difficulty_label(difficulty),
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
            compact_podcasts.append(dict(podcast))

    return {
        "quizzes": compact_quizzes,
        "podcasts": compact_podcasts,
    }


def _enrich_subject_path_lectures(lectures: object) -> list[dict[str, object]]:
    if not isinstance(lectures, list):
        return []

    enriched: list[dict[str, object]] = []
    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_assets = _compact_asset_links(lecture.get("lecture_assets"))
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

        readings = lecture_copy.get("readings")
        reading_payload: list[dict[str, object]] = []
        if isinstance(readings, list):
            for reading in readings:
                if not isinstance(reading, dict):
                    continue
                reading_copy = dict(reading)
                reading_copy["assets"] = _compact_asset_links(reading_copy.get("assets"))
                reading_copy["progress_percent"] = _progress_percent(
                    completed=reading_copy.get("completed_quizzes"),
                    total=reading_copy.get("total_quizzes"),
                )
                reading_payload.append(reading_copy)
        lecture_copy["readings"] = reading_payload
        enriched.append(lecture_copy)
    return enriched


@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("progress")

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
                    "next_value": _requested_next(request),
                },
                status=429,
            )
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(_safe_next_redirect(request) or "progress")
    else:
        form = SignupForm()

    return render(
        request,
        "registration/signup.html",
        {
            "form": form,
            "insecure_http": _is_http_insecure(request),
            "next_value": _requested_next(request),
        },
    )


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("progress")

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
                    "next_value": _requested_next(request),
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
            "next_value": _requested_next(request),
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
        return JsonResponse(progress.state_json, safe=False)

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
    previous_answers_count = int(progress.answers_count or 0)
    previous_status = str(progress.status or QuizProgress.Status.IN_PROGRESS)

    question_count = quiz_question_count(quiz_id) or progress.question_count
    computation = compute_progress(state_payload, question_count)
    upsert_progress_from_state(progress=progress, state_payload=state_payload, computation=computation)
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

    enrolled_slugs = set(
        SubjectEnrollment.objects.filter(user=request.user).values_list("subject_slug", flat=True)
    )
    subject_cards: list[dict[str, object]] = []
    for subject in catalog.active_subjects:
        subject_cards.append(
            {
                "slug": subject.slug,
                "title": subject.title,
                "description": subject.description,
                "is_enrolled": subject.slug in enrolled_slugs,
                "detail_url": reverse("subject-detail", kwargs={"subject_slug": subject.slug}),
                "enroll_url": reverse("subject-enroll", kwargs={"subject_slug": subject.slug}),
                "unenroll_url": reverse("subject-unenroll", kwargs={"subject_slug": subject.slug}),
            }
        )

    label_mapping = load_quiz_label_mapping()
    progress_rows = QuizProgress.objects.filter(user=request.user).order_by("-updated_at")

    rows: list[dict[str, object]] = []
    for row in progress_rows:
        label = label_mapping.get(row.quiz_id)
        episode_title = label.episode_title if label else row.quiz_id
        quiz_display = _quiz_display_context(episode_title=episode_title, quiz_id=row.quiz_id)
        rows.append(
            {
                "quiz_id": row.quiz_id,
                "title": quiz_display.get("title") or row.quiz_id,
                "module_label": quiz_display.get("module_label") or "",
                "meta_chips": list(quiz_display.get("meta_chips") or []),
                "difficulty_label": _difficulty_label(label.difficulty if label else "unknown"),
                "status": row.status,
                "status_label": row.get_status_display(),
                "answers_count": row.answers_count,
                "question_count": row.question_count,
                "updated_at": row.updated_at,
                "completed_at": row.completed_at,
                "quiz_url": reverse("quiz-wrapper", kwargs={"quiz_id": row.quiz_id}),
            }
        )

    return render(
        request,
        "quizzes/progress.html",
        {
            "rows": rows,
            "subject_cards": subject_cards,
            "subjects_error": catalog.error,
        },
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
    overview = _subject_path_overview(lecture_payload)

    return render(
        request,
        "quizzes/subject_detail.html",
        {
            "subject": subject,
            "is_enrolled": is_enrolled,
            "readings_error": readings_error,
            "subject_path_lectures": lecture_payload,
            "subject_path_overview": overview,
        },
    )
