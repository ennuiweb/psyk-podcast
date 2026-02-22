"""Gamification and optional extension services for freudd portal."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    DailyGamificationStat,
    QuizProgress,
    UserExtensionAccess,
    UserExtensionToken,
    UserGamificationProfile,
    UserUnitProgress,
)
from .services import load_quiz_label_mapping
from .subject_services import load_subject_catalog

WEEK_UNIT_PREFIX = "W"
UNKNOWN_UNIT_KEY = "W00"
UNKNOWN_UNIT_LABEL = "Ukendt"
UNIT_RE = r"^(W\d{1,2})L\d+"


@dataclass(frozen=True)
class UnitDefinition:
    key: str
    label: str
    quiz_ids: frozenset[str]


def _subject_slug_default() -> str:
    catalog = load_subject_catalog()
    if catalog.active_subjects:
        return catalog.active_subjects[0].slug
    return "general"


def _unit_key_from_title(title: str) -> tuple[str, str]:
    import re

    cleaned = (title or "").strip()
    match = re.match(UNIT_RE, cleaned, flags=re.IGNORECASE)
    if not match:
        return UNKNOWN_UNIT_KEY, UNKNOWN_UNIT_LABEL
    raw_key = match.group(1).upper()
    digits = raw_key[1:].zfill(2)
    key = f"{WEEK_UNIT_PREFIX}{digits}"
    label = f"Uge {digits}"
    return key, label


def _unit_sort_key(unit_key: str) -> tuple[int, str]:
    if unit_key.startswith(WEEK_UNIT_PREFIX):
        numeric = unit_key[1:]
        if numeric.isdigit():
            return int(numeric), unit_key
    return 9999, unit_key


def _daily_goal_target() -> int:
    value = int(getattr(settings, "FREUDD_GAMIFICATION_DAILY_GOAL", 20))
    return max(1, value)


def _xp_per_answer() -> int:
    value = int(getattr(settings, "FREUDD_GAMIFICATION_XP_PER_ANSWER", 5))
    return max(1, value)


def _xp_per_completion() -> int:
    value = int(getattr(settings, "FREUDD_GAMIFICATION_XP_PER_COMPLETION", 50))
    return max(1, value)


def _xp_per_level() -> int:
    value = int(getattr(settings, "FREUDD_GAMIFICATION_XP_PER_LEVEL", 500))
    return max(1, value)


def _build_unit_definitions_for_user(user) -> list[UnitDefinition]:
    labels = load_quiz_label_mapping()
    grouped: dict[str, dict[str, Any]] = {}

    if labels:
        for quiz_id, label in labels.items():
            unit_key, unit_label = _unit_key_from_title(label.episode_title)
            bucket = grouped.setdefault(
                unit_key,
                {
                    "label": unit_label,
                    "quiz_ids": set(),
                },
            )
            bucket["quiz_ids"].add(quiz_id)
    else:
        user_quiz_ids = set(
            QuizProgress.objects.filter(user=user).values_list("quiz_id", flat=True)
        )
        if user_quiz_ids:
            grouped[UNKNOWN_UNIT_KEY] = {
                "label": UNKNOWN_UNIT_LABEL,
                "quiz_ids": user_quiz_ids,
            }

    units: list[UnitDefinition] = []
    for key, payload in grouped.items():
        quiz_ids = frozenset(payload["quiz_ids"])
        if not quiz_ids:
            continue
        units.append(
            UnitDefinition(
                key=key,
                label=str(payload["label"]),
                quiz_ids=quiz_ids,
            )
        )
    return sorted(units, key=lambda item: _unit_sort_key(item.key))


def _recompute_unit_progress(user) -> tuple[int, list[UserUnitProgress]]:
    subject_slug = _subject_slug_default()
    units = _build_unit_definitions_for_user(user)
    completed_ids = set(
        QuizProgress.objects.filter(user=user, status=QuizProgress.Status.COMPLETED).values_list(
            "quiz_id", flat=True
        )
    )

    rows: list[UserUnitProgress] = []
    first_active_index: int | None = None
    sequence = 0
    for definition in units:
        sequence += 1
        total_quizzes = len(definition.quiz_ids)
        completed_quizzes = len(definition.quiz_ids.intersection(completed_ids))
        ratio = Decimal("0")
        if total_quizzes > 0:
            ratio = Decimal(completed_quizzes) / Decimal(total_quizzes)

        if total_quizzes > 0 and completed_quizzes == total_quizzes:
            status = UserUnitProgress.Status.COMPLETED
        elif first_active_index is None:
            status = UserUnitProgress.Status.ACTIVE
            first_active_index = sequence
        else:
            status = UserUnitProgress.Status.LOCKED

        row, _ = UserUnitProgress.objects.update_or_create(
            user=user,
            subject_slug=subject_slug,
            unit_key=definition.key,
            defaults={
                "unit_label": definition.label,
                "sequence_index": sequence,
                "status": status,
                "completed_quizzes": completed_quizzes,
                "total_quizzes": total_quizzes,
                "mastery_ratio": ratio.quantize(Decimal("0.0001")),
            },
        )
        rows.append(row)

    active_keys = {row.unit_key for row in rows}
    UserUnitProgress.objects.filter(user=user, subject_slug=subject_slug).exclude(
        unit_key__in=active_keys
    ).delete()

    if first_active_index is None:
        current_level = max(1, len(rows))
    else:
        current_level = first_active_index
    return current_level, rows


def _recompute_streak(stats: list[DailyGamificationStat], today: date) -> int:
    met_dates = {item.date for item in stats if item.goal_met}
    streak = 0
    cursor = today
    while cursor in met_dates:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


@transaction.atomic
def recompute_user_gamification(user) -> UserGamificationProfile:
    today = timezone.localdate()
    goal_target = _daily_goal_target()
    daily_stat, _ = DailyGamificationStat.objects.get_or_create(
        user=user,
        date=today,
        defaults={"goal_target": goal_target, "goal_met": False},
    )
    if daily_stat.goal_target != goal_target:
        daily_stat.goal_target = goal_target
    daily_stat.goal_met = daily_stat.answered_delta >= daily_stat.goal_target
    daily_stat.save(update_fields=["goal_target", "goal_met", "updated_at"])

    stats = list(DailyGamificationStat.objects.filter(user=user).order_by("date"))
    xp_total = 0
    for item in stats:
        xp_total += item.answered_delta * _xp_per_answer()
        xp_total += item.completed_delta * _xp_per_completion()

    streak_days = _recompute_streak(stats, today=today)
    current_level_from_xp = max(1, (xp_total // _xp_per_level()) + 1)
    current_level_from_units, _ = _recompute_unit_progress(user)
    current_level = max(current_level_from_xp, current_level_from_units)

    last_activity_date: date | None = None
    for item in reversed(stats):
        if item.answered_delta > 0 or item.completed_delta > 0:
            last_activity_date = item.date
            break

    profile, _ = UserGamificationProfile.objects.update_or_create(
        user=user,
        defaults={
            "xp_total": xp_total,
            "streak_days": streak_days,
            "current_level": current_level,
            "last_activity_date": last_activity_date,
        },
    )
    return profile


@transaction.atomic
def record_quiz_progress_delta(
    *,
    progress: QuizProgress,
    previous_answers_count: int,
    previous_status: str,
) -> UserGamificationProfile:
    answered_gain = max(0, progress.answers_count - max(0, previous_answers_count))
    completed_gain = int(
        previous_status != QuizProgress.Status.COMPLETED
        and progress.status == QuizProgress.Status.COMPLETED
    )

    today = timezone.localdate()
    goal_target = _daily_goal_target()
    daily_stat, _ = DailyGamificationStat.objects.get_or_create(
        user=progress.user,
        date=today,
        defaults={"goal_target": goal_target, "goal_met": False},
    )
    if daily_stat.goal_target != goal_target:
        daily_stat.goal_target = goal_target
    daily_stat.answered_delta += answered_gain
    daily_stat.completed_delta += completed_gain
    daily_stat.goal_met = daily_stat.answered_delta >= daily_stat.goal_target
    daily_stat.save(
        update_fields=[
            "goal_target",
            "answered_delta",
            "completed_delta",
            "goal_met",
            "updated_at",
        ]
    )
    return recompute_user_gamification(progress.user)


def get_gamification_snapshot(user) -> dict[str, Any]:
    profile = recompute_user_gamification(user)
    today = timezone.localdate()
    goal_target = _daily_goal_target()
    daily_stat, _ = DailyGamificationStat.objects.get_or_create(
        user=user,
        date=today,
        defaults={"goal_target": goal_target, "goal_met": False},
    )

    units = list(
        UserUnitProgress.objects.filter(user=user).order_by("sequence_index", "unit_key")
    )
    enabled_extensions = list(
        UserExtensionAccess.objects.filter(user=user, enabled=True).order_by("extension")
    )

    return {
        "profile": {
            "xp_total": profile.xp_total,
            "streak_days": profile.streak_days,
            "current_level": profile.current_level,
            "last_activity_date": profile.last_activity_date.isoformat()
            if profile.last_activity_date
            else None,
        },
        "daily": {
            "date": daily_stat.date.isoformat(),
            "goal_target": daily_stat.goal_target,
            "answered_delta": daily_stat.answered_delta,
            "completed_delta": daily_stat.completed_delta,
            "goal_met": daily_stat.goal_met,
            "missing_answers": max(0, daily_stat.goal_target - daily_stat.answered_delta),
        },
        "units": [
            {
                "subject_slug": unit.subject_slug,
                "unit_key": unit.unit_key,
                "unit_label": unit.unit_label,
                "sequence_index": unit.sequence_index,
                "status": unit.status,
                "completed_quizzes": unit.completed_quizzes,
                "total_quizzes": unit.total_quizzes,
                "mastery_ratio": float(unit.mastery_ratio),
            }
            for unit in units
        ],
        "extensions": [
            {
                "extension": item.extension,
                "enabled": item.enabled,
                "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
                "last_sync_status": item.last_sync_status,
                "last_sync_error": item.last_sync_error,
            }
            for item in enabled_extensions
        ],
    }


def create_extension_token(*, user, created_by: str) -> str:
    token_raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_raw.encode("utf-8")).hexdigest()
    now = timezone.now()
    UserExtensionToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    UserExtensionToken.objects.create(
        user=user,
        token_hash=token_hash,
        token_prefix=token_raw[:12],
        created_by=(created_by or "").strip(),
    )
    return token_raw


def revoke_extension_tokens(*, user) -> int:
    now = timezone.now()
    updated = UserExtensionToken.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now
    )
    return int(updated)


def validate_extension_token(raw_token: str):
    token_value = (raw_token or "").strip()
    if not token_value:
        return None
    token_hash = hashlib.sha256(token_value.encode("utf-8")).hexdigest()
    return (
        UserExtensionToken.objects.select_related("user")
        .filter(token_hash=token_hash, revoked_at__isnull=True)
        .first()
    )


def set_extension_access(*, user, extension: str, enabled: bool, enabled_by: str) -> UserExtensionAccess:
    extension_key = (extension or "").strip().lower()
    if extension_key not in {
        UserExtensionAccess.Extension.HABITICA,
        UserExtensionAccess.Extension.ANKI,
    }:
        raise ValueError("extension must be either 'habitica' or 'anki'")

    if enabled:
        enabled_at = timezone.now()
        enabled_by_value = (enabled_by or "").strip()

    access, _ = UserExtensionAccess.objects.get_or_create(
        user=user,
        extension=extension_key,
        defaults={
            "enabled": False,
            "enabled_by": "",
        },
    )
    access.enabled = bool(enabled)
    if enabled:
        access.enabled_at = enabled_at
        access.enabled_by = enabled_by_value
    else:
        access.enabled_at = None
        access.enabled_by = ""
    access.save(
        update_fields=[
            "enabled",
            "enabled_at",
            "enabled_by",
            "updated_at",
        ]
    )
    return access


def record_extension_sync(
    *,
    user,
    extension: str,
    status: str,
    payload: dict[str, Any],
    error: str,
) -> UserExtensionAccess:
    extension_key = (extension or "").strip().lower()
    status_value = (status or "").strip().lower()
    if extension_key not in {
        UserExtensionAccess.Extension.HABITICA,
        UserExtensionAccess.Extension.ANKI,
    }:
        raise ValueError("Unsupported extension")
    if status_value not in {
        UserExtensionAccess.SyncStatus.OK,
        UserExtensionAccess.SyncStatus.ERROR,
    }:
        raise ValueError("status must be either 'ok' or 'error'")

    access = UserExtensionAccess.objects.filter(
        user=user,
        extension=extension_key,
        enabled=True,
    ).first()
    if access is None:
        raise PermissionError("Extension is not enabled for user")

    access.last_sync_at = timezone.now()
    access.last_sync_status = status_value
    access.last_sync_error = (error or "").strip()
    access.last_sync_payload = payload or {}
    access.save(
        update_fields=[
            "last_sync_at",
            "last_sync_status",
            "last_sync_error",
            "last_sync_payload",
            "updated_at",
        ]
    )
    return access


def recompute_many(*, usernames: list[str] | None = None) -> int:
    user_model = get_user_model()
    queryset = user_model.objects.all()
    if usernames:
        queryset = queryset.filter(username__in=usernames)
    processed = 0
    for user in queryset.iterator():
        recompute_user_gamification(user)
        processed += 1
    return processed


def extension_sync_payload_valid(raw_payload: Any) -> tuple[str, str, dict[str, Any], str]:
    if not isinstance(raw_payload, dict):
        raise ValueError("Payload must be a JSON object")

    extension = str(raw_payload.get("extension", "")).strip().lower()
    status = str(raw_payload.get("status", "")).strip().lower()
    payload = raw_payload.get("payload", {})
    error = str(raw_payload.get("error", "")).strip()

    if extension not in {
        UserExtensionAccess.Extension.HABITICA,
        UserExtensionAccess.Extension.ANKI,
    }:
        raise ValueError("extension must be 'habitica' or 'anki'")
    if status not in {
        UserExtensionAccess.SyncStatus.OK,
        UserExtensionAccess.SyncStatus.ERROR,
    }:
        raise ValueError("status must be 'ok' or 'error'")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return extension, status, payload, error


def extract_bearer_token(authorization_header: str) -> str:
    header = (authorization_header or "").strip()
    if not header:
        return ""
    parts = header.split(" ", 1)
    if len(parts) != 2:
        return ""
    if parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()
