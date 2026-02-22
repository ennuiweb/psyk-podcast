"""Views for auth, quiz wrapper/raw access, subject dashboards, and state/progress APIs."""

from __future__ import annotations

import json
import logging
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
    record_quiz_progress_delta,
)
from .models import QuizProgress, SubjectEnrollment, UserPreference
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
from .subject_services import SubjectCatalog, load_subject_catalog, parse_master_readings

logger = logging.getLogger(__name__)
MAX_STATE_BYTES = 5_000_000
DIFFICULTY_LABELS_DA = {
    "easy": "Let",
    "medium": "Mellem",
    "hard": "Svær",
    "unknown": "Ukendt",
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


def _difficulty_label(value: str | None) -> str:
    difficulty = (value or "unknown").strip().lower() or "unknown"
    return DIFFICULTY_LABELS_DA.get(difficulty, difficulty.capitalize())


def _default_semester_choice(catalog: SubjectCatalog) -> str:
    return catalog.semester_choices[0] if catalog.semester_choices else "F26"


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
    quiz_path = reverse("quiz-wrapper", kwargs={"quiz_id": quiz_id})
    context = {
        "quiz_id": quiz_id,
        "quiz_title": label.episode_title if label else quiz_id,
        "quiz_difficulty_label": _difficulty_label(label.difficulty if label else "unknown"),
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
    preference, _ = UserPreference.objects.get_or_create(
        user=request.user,
        defaults={"semester": _default_semester_choice(catalog)},
    )

    semester_choices = catalog.semester_choices or (_default_semester_choice(catalog),)
    selected_semester = preference.semester
    if selected_semester not in semester_choices:
        selected_semester = _default_semester_choice(catalog)

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
        rows.append(
            {
                "quiz_id": row.quiz_id,
                "title": label.episode_title if label else row.quiz_id,
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

    gamification = get_gamification_snapshot(request.user)

    return render(
        request,
        "quizzes/progress.html",
        {
            "rows": rows,
            "semester_choices": semester_choices,
            "selected_semester": selected_semester,
            "subject_cards": subject_cards,
            "subjects_error": catalog.error,
            "gamification": gamification,
            "extensions_enabled": bool(gamification.get("extensions")),
        },
    )


@login_required
@require_POST
def semester_update_view(request: HttpRequest) -> HttpResponse:
    catalog = load_subject_catalog()
    semester = request.POST.get("semester", "").strip()
    if semester not in catalog.semester_choices:
        messages.error(request, "Ugyldigt semester valgt.")
        return redirect("progress")

    preference, _ = UserPreference.objects.get_or_create(
        user=request.user,
        defaults={"semester": _default_semester_choice(catalog)},
    )
    if preference.semester != semester:
        preference.semester = semester
        preference.save(update_fields=["semester", "updated_at"])
        messages.success(request, "Semester er opdateret.")
    return redirect("progress")


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
    readings = parse_master_readings(settings.FREUDD_READING_MASTER_KEY_PATH)

    return render(
        request,
        "quizzes/subject_detail.html",
        {
            "subject": subject,
            "is_enrolled": is_enrolled,
            "lectures": readings.lectures,
            "readings_error": readings.error,
            "enroll_url": reverse("subject-enroll", kwargs={"subject_slug": subject.slug}),
            "unenroll_url": reverse("subject-unenroll", kwargs={"subject_slug": subject.slug}),
        },
    )
