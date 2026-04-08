from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import HttpRequest
from django.utils import timezone

from .rate_limit import get_client_ip

logger = logging.getLogger(__name__)

DEFAULT_ACTIVITY_EVENT_KEYS = (
    "signup",
    "quiz_completed",
    "subject_enrolled",
    "reading_marked",
    "podcast_marked",
    "reading_opened",
    "reading_sent_to_chatgpt",
)

EVENT_LABELS = {
    "signup": "Signup created",
    "quiz_completed": "Quiz completed",
    "subject_enrolled": "Subject enrolled",
    "reading_marked": "Reading marked",
    "podcast_marked": "Podcast marked",
    "reading_opened": "Reading opened",
    "reading_sent_to_chatgpt": "Reading sent to ChatGPT",
}

EVENT_SUBJECTS = {
    "signup": "Freudd: New user created",
    "quiz_completed": "Freudd activity: Quiz completed",
    "subject_enrolled": "Freudd activity: Subject enrolled",
    "reading_marked": "Freudd activity: Reading marked",
    "podcast_marked": "Freudd activity: Podcast marked",
    "reading_opened": "Freudd activity: Reading opened",
    "reading_sent_to_chatgpt": "Freudd activity: Reading sent to ChatGPT",
}

READING_ACTIVITY_DEDUPE_SECONDS = 120
CHATGPT_ACTIVITY_DEDUPE_SECONDS = 120


def _normalize_setting_list(value: object) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        parts = [str(item) for item in value]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = str(part or "").strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _activity_recipient_list() -> list[str]:
    primary_notify_email = str(getattr(settings, "FREUDD_NEW_USER_NOTIFY_EMAIL", "") or "").strip()
    if primary_notify_email:
        return [primary_notify_email]
    return _normalize_setting_list(getattr(settings, "FREUDD_ACTIVITY_NOTIFY_EMAILS", ()))


def _activity_event_keys() -> set[str]:
    raw_value = getattr(settings, "FREUDD_ACTIVITY_NOTIFY_EVENTS", DEFAULT_ACTIVITY_EVENT_KEYS)
    return {
        item
        for item in _normalize_setting_list(raw_value)
        if item in EVENT_LABELS
    }


def _activity_enabled(event_key: str) -> bool:
    return event_key in _activity_event_keys()


def send_notification_email(*, recipient_list: Sequence[str], subject: str, body: str) -> bool:
    recipients = _normalize_setting_list(recipient_list)
    if not recipients:
        return False

    resend_api_key = os.environ.get("FREUDD_RESEND_API_KEY", "").strip()
    if resend_api_key:
        resend_api_url = os.environ.get("FREUDD_RESEND_API_URL", "https://api.resend.com/emails").strip()
        try:
            resend_timeout_seconds = int(os.environ.get("FREUDD_RESEND_TIMEOUT_SECONDS", "10"))
        except ValueError:
            resend_timeout_seconds = 10

        try:
            response = requests.post(
                resend_api_url,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.DEFAULT_FROM_EMAIL,
                    "to": recipients,
                    "subject": subject,
                    "text": body,
                },
                timeout=resend_timeout_seconds,
            )
            response.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("Resend delivery failed for Freudd activity notification.")

    sent_count = send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=True,
    )
    return bool(sent_count)


def _activity_actor_token(*, request: HttpRequest | None, user: object | None) -> str:
    if user is not None and bool(getattr(user, "is_authenticated", False)) and getattr(user, "id", None) is not None:
        return f"user:{user.id}"
    if request is not None:
        return f"ip:{get_client_ip(request)}"
    return "unknown"


def _format_metadata_line(key: str, value: object) -> str:
    return f"{key}: {value}"


def _activity_body(
    *,
    event_key: str,
    request: HttpRequest | None,
    user: object | None,
    metadata: Mapping[str, object],
) -> str:
    lines = [
        "Freudd activity detected.",
        _format_metadata_line("event", event_key),
        _format_metadata_line("label", EVENT_LABELS.get(event_key, event_key)),
        _format_metadata_line("timestamp", timezone.now().isoformat()),
    ]

    actor = user if user is not None else getattr(request, "user", None)
    if actor is not None and bool(getattr(actor, "is_authenticated", False)):
        lines.extend(
            [
                _format_metadata_line("user_id", getattr(actor, "id", "")),
                _format_metadata_line("username", getattr(actor, "username", "")),
                _format_metadata_line("email", getattr(actor, "email", "") or "no-email"),
            ]
        )
    else:
        lines.append(_format_metadata_line("user", "anonymous"))

    if request is not None:
        lines.extend(
            [
                _format_metadata_line("method", request.method),
                _format_metadata_line("path", request.path),
                _format_metadata_line("client_ip", get_client_ip(request)),
            ]
        )
        user_agent = str(request.META.get("HTTP_USER_AGENT") or "").strip()
        if user_agent:
            lines.append(_format_metadata_line("user_agent", user_agent[:240]))

    for key, value in metadata.items():
        normalized_value = str(value or "").strip()
        if not normalized_value:
            continue
        lines.append(_format_metadata_line(key, normalized_value))
    return "\n".join(lines)


def notify_activity(
    event_key: str,
    *,
    request: HttpRequest | None = None,
    user: object | None = None,
    metadata: Mapping[str, object] | None = None,
    dedupe_key: str = "",
    dedupe_ttl_seconds: int = 0,
) -> bool:
    if event_key not in EVENT_LABELS:
        raise ValueError(f"Unsupported activity event: {event_key}")
    if not _activity_enabled(event_key):
        return False

    recipients = _activity_recipient_list()
    if not recipients:
        return False

    if dedupe_ttl_seconds > 0 and dedupe_key:
        cache_key = f"freudd-activity-notify:{event_key}:{dedupe_key}"
        if not cache.add(cache_key, "1", timeout=dedupe_ttl_seconds):
            return False

    body = _activity_body(
        event_key=event_key,
        request=request,
        user=user,
        metadata=metadata or {},
    )
    try:
        return send_notification_email(
            recipient_list=recipients,
            subject=EVENT_SUBJECTS[event_key],
            body=body,
        )
    except Exception:
        logger.exception("Activity notification failed.", extra={"event_key": event_key})
        return False


def notify_new_user_created(*, user: object) -> bool:
    return notify_activity(
        "signup",
        user=user,
    )


def notify_quiz_completed(
    *,
    request: HttpRequest,
    quiz_id: str,
    subject_slug: str,
    correct_answers: int,
    question_count: int,
    score_points: int,
    duration_ms: int,
) -> bool:
    return notify_activity(
        "quiz_completed",
        request=request,
        metadata={
            "quiz_id": quiz_id,
            "subject_slug": subject_slug,
            "correct_answers": correct_answers,
            "question_count": question_count,
            "score_points": score_points,
            "duration_ms": duration_ms,
        },
    )


def notify_subject_enrolled(*, request: HttpRequest, subject_slug: str, subject_title: str) -> bool:
    return notify_activity(
        "subject_enrolled",
        request=request,
        metadata={
            "subject_slug": subject_slug,
            "subject_title": subject_title,
        },
    )


def notify_reading_marked(
    *,
    request: HttpRequest,
    subject_slug: str,
    lecture_key: str,
    reading_key: str,
) -> bool:
    return notify_activity(
        "reading_marked",
        request=request,
        metadata={
            "subject_slug": subject_slug,
            "lecture_key": lecture_key,
            "reading_key": reading_key,
        },
    )


def notify_podcast_marked(
    *,
    request: HttpRequest,
    subject_slug: str,
    lecture_key: str,
    reading_key: str | None,
    podcast_key: str,
) -> bool:
    return notify_activity(
        "podcast_marked",
        request=request,
        metadata={
            "subject_slug": subject_slug,
            "lecture_key": lecture_key,
            "reading_key": reading_key or "",
            "podcast_key": podcast_key,
        },
    )


def notify_reading_opened(
    *,
    request: HttpRequest,
    subject_slug: str,
    lecture_key: str,
    reading_key: str,
    source_filename: str,
) -> bool:
    actor_token = _activity_actor_token(request=request, user=getattr(request, "user", None))
    return notify_activity(
        "reading_opened",
        request=request,
        metadata={
            "subject_slug": subject_slug,
            "lecture_key": lecture_key,
            "reading_key": reading_key,
            "source_filename": source_filename,
        },
        dedupe_key=f"{actor_token}:{subject_slug}:{reading_key}",
        dedupe_ttl_seconds=READING_ACTIVITY_DEDUPE_SECONDS,
    )


def notify_reading_sent_to_chatgpt(
    *,
    request: HttpRequest,
    subject_slug: str,
    lecture_key: str,
    reading_key: str,
    source_filename: str,
) -> bool:
    actor_token = _activity_actor_token(request=request, user=getattr(request, "user", None))
    return notify_activity(
        "reading_sent_to_chatgpt",
        request=request,
        metadata={
            "subject_slug": subject_slug,
            "lecture_key": lecture_key,
            "reading_key": reading_key,
            "source_filename": source_filename,
        },
        dedupe_key=f"{actor_token}:{subject_slug}:{reading_key}",
        dedupe_ttl_seconds=CHATGPT_ACTIVITY_DEDUPE_SECONDS,
    )
