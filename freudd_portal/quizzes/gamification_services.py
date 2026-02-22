"""Gamification and optional extension services for freudd portal."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    DailyGamificationStat,
    ExtensionSyncLedger,
    QuizProgress,
    UserExtensionAccess,
    UserExtensionCredential,
    UserGamificationProfile,
    UserUnitProgress,
)
from .services import load_quiz_label_mapping
from .subject_services import load_subject_catalog

WEEK_UNIT_PREFIX = "W"
UNKNOWN_UNIT_KEY = "W00"
UNKNOWN_UNIT_LABEL = "Ukendt"
UNIT_RE = r"^(W\d{1,2})L\d+"
HABITICA_API_BASE = "https://habitica.com/api/v3"


@dataclass(frozen=True)
class UnitDefinition:
    subject_slug: str
    key: str
    label: str
    quiz_ids: frozenset[str]


class ExtensionCredentialError(RuntimeError):
    """Raised when extension credentials cannot be loaded or decrypted."""


class ExtensionSyncError(RuntimeError):
    """Raised when extension sync fails."""


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


def _build_unit_definitions_for_user(user) -> dict[str, list[UnitDefinition]]:
    labels = load_quiz_label_mapping()
    grouped: dict[str, dict[str, dict[str, Any]]] = {}

    for quiz_id, label in labels.items():
        if not label.subject_slug:
            continue
        unit_key, unit_label = _unit_key_from_title(label.episode_title)
        subject_bucket = grouped.setdefault(label.subject_slug, {})
        unit_bucket = subject_bucket.setdefault(
            unit_key,
            {
                "label": unit_label,
                "quiz_ids": set(),
            },
        )
        unit_bucket["quiz_ids"].add(quiz_id)

    catalog = load_subject_catalog()
    ordered_subjects = [subject.slug for subject in catalog.active_subjects]
    for subject_slug in sorted(grouped):
        if subject_slug not in ordered_subjects:
            ordered_subjects.append(subject_slug)

    units_by_subject: dict[str, list[UnitDefinition]] = {}
    for subject_slug in ordered_subjects:
        subject_units = grouped.get(subject_slug, {})
        units: list[UnitDefinition] = []
        for key, payload in subject_units.items():
            quiz_ids = frozenset(payload["quiz_ids"])
            if not quiz_ids:
                continue
            units.append(
                UnitDefinition(
                    subject_slug=subject_slug,
                    key=key,
                    label=str(payload["label"]),
                    quiz_ids=quiz_ids,
                )
            )
        if units:
            units_by_subject[subject_slug] = sorted(units, key=lambda item: _unit_sort_key(item.key))
    return units_by_subject


def _recompute_unit_progress(user) -> tuple[int, list[UserUnitProgress]]:
    units_by_subject = _build_unit_definitions_for_user(user)
    completed_ids = set(
        QuizProgress.objects.filter(user=user, status=QuizProgress.Status.COMPLETED).values_list(
            "quiz_id", flat=True
        )
    )

    rows: list[UserUnitProgress] = []
    active_keys_by_subject: dict[str, set[str]] = {}
    completed_units_total = 0
    for subject_slug, units in units_by_subject.items():
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
                completed_units_total += 1
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
            active_keys_by_subject.setdefault(subject_slug, set()).add(definition.key)

    if not active_keys_by_subject:
        UserUnitProgress.objects.filter(user=user).delete()
    else:
        for subject_slug, unit_keys in active_keys_by_subject.items():
            UserUnitProgress.objects.filter(user=user, subject_slug=subject_slug).exclude(
                unit_key__in=unit_keys
            ).delete()
        UserUnitProgress.objects.filter(user=user).exclude(
            subject_slug__in=active_keys_by_subject.keys()
        ).delete()

    current_level = max(1, completed_units_total + 1)
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


def get_subject_learning_path_snapshot(user, subject_slug: str) -> dict[str, Any]:
    recompute_user_gamification(user)
    slug = (subject_slug or "").strip().lower()
    units = list(
        UserUnitProgress.objects.filter(user=user, subject_slug=slug).order_by("sequence_index", "unit_key")
    )
    unit_payload = [
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
    ]
    active_unit = next((unit for unit in unit_payload if unit["status"] == UserUnitProgress.Status.ACTIVE), None)
    return {
        "units": unit_payload,
        "active_unit": active_unit,
    }


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


def _credential_key_version() -> int:
    return max(1, int(getattr(settings, "FREUDD_CREDENTIALS_KEY_VERSION", 1)))


def _credential_fernet() -> Fernet:
    raw_key = str(getattr(settings, "FREUDD_CREDENTIALS_MASTER_KEY", "") or "").strip()
    if not raw_key:
        raise ExtensionCredentialError("Missing FREUDD_CREDENTIALS_MASTER_KEY.")
    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception as exc:
        raise ExtensionCredentialError("Invalid FREUDD_CREDENTIALS_MASTER_KEY.") from exc


def _encrypted_payload_from_dict(payload: dict[str, Any]) -> str:
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return _credential_fernet().encrypt(plaintext).decode("utf-8")


def _decrypted_payload_to_dict(ciphertext: str) -> dict[str, Any]:
    try:
        plaintext = _credential_fernet().decrypt((ciphertext or "").encode("utf-8"))
    except InvalidToken as exc:
        raise ExtensionCredentialError("Credential decrypt failed for active master key.") from exc
    except Exception as exc:
        raise ExtensionCredentialError("Credential decrypt failed.") from exc

    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtensionCredentialError("Credential payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ExtensionCredentialError("Credential payload must be a JSON object.")
    return payload


def _validate_habitica_credential_payload(payload: dict[str, Any]) -> dict[str, str]:
    user_id = str(payload.get("habitica_user_id", "")).strip()
    api_token = str(payload.get("habitica_api_token", "")).strip()
    task_id = str(payload.get("habitica_task_id", "")).strip()
    if not user_id:
        raise ExtensionCredentialError("Missing habitica_user_id.")
    if not api_token:
        raise ExtensionCredentialError("Missing habitica_api_token.")
    if not task_id:
        raise ExtensionCredentialError("Missing habitica_task_id.")
    return {
        "habitica_user_id": user_id,
        "habitica_api_token": api_token,
        "habitica_task_id": task_id,
    }


def set_extension_credential(*, user, extension: str, payload: dict[str, Any]) -> UserExtensionCredential:
    extension_key = (extension or "").strip().lower()
    if extension_key != UserExtensionAccess.Extension.HABITICA:
        raise ExtensionCredentialError("Only habitica credentials are supported in this phase.")

    normalized_payload = _validate_habitica_credential_payload(payload)
    encrypted_payload = _encrypted_payload_from_dict(normalized_payload)
    now = timezone.now()
    credential, created = UserExtensionCredential.objects.get_or_create(
        user=user,
        extension=extension_key,
        defaults={
            "encrypted_payload": encrypted_payload,
            "key_version": _credential_key_version(),
        },
    )
    if created:
        return credential

    credential.encrypted_payload = encrypted_payload
    credential.key_version = _credential_key_version()
    credential.rotated_at = now
    credential.save(update_fields=["encrypted_payload", "key_version", "rotated_at", "updated_at"])
    return credential


def clear_extension_credential(*, user, extension: str) -> int:
    extension_key = (extension or "").strip().lower()
    deleted_count, _ = UserExtensionCredential.objects.filter(
        user=user,
        extension=extension_key,
    ).delete()
    return int(deleted_count)


def extension_credential_meta(*, user, extension: str) -> dict[str, Any] | None:
    extension_key = (extension or "").strip().lower()
    row = UserExtensionCredential.objects.filter(user=user, extension=extension_key).first()
    if row is None:
        return None
    return {
        "user": user.username,
        "extension": row.extension,
        "key_version": row.key_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "rotated_at": row.rotated_at.isoformat() if row.rotated_at else None,
    }


def rotate_extension_credential_key(*, user, extension: str) -> UserExtensionCredential:
    extension_key = (extension or "").strip().lower()
    row = UserExtensionCredential.objects.filter(user=user, extension=extension_key).first()
    if row is None:
        raise ExtensionCredentialError("No extension credential found for user/extension.")
    payload = _decrypted_payload_to_dict(row.encrypted_payload)
    row.encrypted_payload = _encrypted_payload_from_dict(payload)
    row.key_version = _credential_key_version()
    row.rotated_at = timezone.now()
    row.save(update_fields=["encrypted_payload", "key_version", "rotated_at", "updated_at"])
    return row


def load_extension_credential_payload(*, user, extension: str) -> dict[str, str]:
    extension_key = (extension or "").strip().lower()
    row = UserExtensionCredential.objects.filter(user=user, extension=extension_key).first()
    if row is None:
        raise ExtensionCredentialError("Missing extension credentials for user.")
    payload = _decrypted_payload_to_dict(row.encrypted_payload)
    if extension_key == UserExtensionAccess.Extension.HABITICA:
        return _validate_habitica_credential_payload(payload)
    raise ExtensionCredentialError("Unsupported extension credential payload.")


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


def _habitica_sync_timeout_seconds() -> int:
    return max(1, int(getattr(settings, "FREUDD_EXT_SYNC_TIMEOUT_SECONDS", 20)))


def _daily_outcome_for_stat(*, daily_stat: DailyGamificationStat) -> dict[str, Any]:
    goal_target = max(1, int(daily_stat.goal_target or _daily_goal_target()))
    answered_delta = max(0, int(daily_stat.answered_delta or 0))
    completed_delta = max(0, int(daily_stat.completed_delta or 0))
    goal_met = answered_delta >= goal_target
    missing_answers = max(0, goal_target - answered_delta)
    score_direction = "up" if goal_met else "down"
    score_events = 1 if goal_target > 0 else max(1, math.ceil(missing_answers / 5))
    return {
        "goal_target": goal_target,
        "answered_delta": answered_delta,
        "completed_delta": completed_delta,
        "goal_met": goal_met,
        "missing_answers": missing_answers,
        "score_direction": score_direction,
        "score_events": score_events,
    }


def _habitica_score_task(*, credential_payload: dict[str, str], direction: str, score_events: int) -> int:
    headers = {
        "x-api-user": credential_payload["habitica_user_id"],
        "x-api-key": credential_payload["habitica_api_token"],
        "Content-Type": "application/json",
    }
    task_id = credential_payload["habitica_task_id"]
    normalized_direction = direction.strip().lower()
    if normalized_direction not in {"up", "down"}:
        raise ExtensionSyncError("Habitica score direction must be 'up' or 'down'.")

    applied_events = 0
    timeout_seconds = _habitica_sync_timeout_seconds()
    endpoint = f"{HABITICA_API_BASE}/tasks/{task_id}/score/{normalized_direction}"
    for _ in range(max(1, score_events)):
        try:
            response = requests.post(endpoint, headers=headers, timeout=timeout_seconds)
        except requests.RequestException as exc:
            raise ExtensionSyncError(f"Habitica request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            error_message = ""
            if isinstance(payload, dict):
                error_message = str(payload.get("message", "")).strip()
            if not error_message:
                error_message = f"Habitica status code: {response.status_code}"
            raise ExtensionSyncError(error_message)
        if isinstance(payload, dict) and payload.get("success") is False:
            error_message = str(payload.get("message", "")).strip() or "Habitica returned success=false."
            raise ExtensionSyncError(error_message)
        applied_events += 1
    return applied_events


def _sync_habitica_access(
    *,
    access: UserExtensionAccess,
    sync_date: date,
    dry_run: bool,
) -> tuple[str, dict[str, Any], str]:
    goal_target = _daily_goal_target()
    daily_stat, _ = DailyGamificationStat.objects.get_or_create(
        user=access.user,
        date=sync_date,
        defaults={"goal_target": goal_target, "goal_met": False},
    )
    if daily_stat.goal_target != goal_target:
        daily_stat.goal_target = goal_target
        if not dry_run:
            daily_stat.save(update_fields=["goal_target", "updated_at"])

    outcome = _daily_outcome_for_stat(daily_stat=daily_stat)
    details: dict[str, Any] = {
        "mode": "dry_run" if dry_run else "live",
        "sync_date": sync_date.isoformat(),
        **outcome,
    }
    try:
        credential_payload = load_extension_credential_payload(
            user=access.user,
            extension=access.extension,
        )
    except ExtensionCredentialError as exc:
        return ExtensionSyncLedger.Status.ERROR, details, str(exc)

    if dry_run:
        details["applied_events"] = outcome["score_events"]
        return ExtensionSyncLedger.Status.OK, details, ""

    try:
        applied_events = _habitica_score_task(
            credential_payload=credential_payload,
            direction=str(outcome["score_direction"]),
            score_events=int(outcome["score_events"]),
        )
    except ExtensionSyncError as exc:
        return ExtensionSyncLedger.Status.ERROR, details, str(exc)

    details["applied_events"] = applied_events
    return ExtensionSyncLedger.Status.OK, details, ""


def sync_extensions_batch(
    *,
    extension: str,
    username: str | None = None,
    sync_date: date | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    extension_key = (extension or "").strip().lower()
    if extension_key not in {"habitica", "all"}:
        raise ValueError("extension must be 'habitica' or 'all'")

    sync_day = sync_date or timezone.localdate()
    enabled_extensions = [UserExtensionAccess.Extension.HABITICA]
    if extension_key == "all":
        enabled_extensions.append(UserExtensionAccess.Extension.ANKI)

    accesses = UserExtensionAccess.objects.filter(
        enabled=True,
        extension__in=enabled_extensions,
    ).select_related("user")
    if username:
        accesses = accesses.filter(user__username=username.strip())
    accesses = accesses.order_by("user__username", "extension")

    summary: dict[str, Any] = {
        "sync_date": sync_day.isoformat(),
        "dry_run": bool(dry_run),
        "requested_extension": extension_key,
        "processed": 0,
        "ok": 0,
        "error": 0,
        "skipped": 0,
        "results": [],
    }

    for access in accesses.iterator():
        row_key = {
            "user": access.user.username,
            "extension": access.extension,
            "sync_date": sync_day.isoformat(),
        }
        existing_ledger = ExtensionSyncLedger.objects.filter(
            user=access.user,
            extension=access.extension,
            sync_date=sync_day,
        ).first()
        if existing_ledger is not None:
            summary["processed"] += 1
            summary["skipped"] += 1
            summary["results"].append(
                {
                    **row_key,
                    "status": ExtensionSyncLedger.Status.SKIPPED,
                    "details": {"reason": "ledger_exists"},
                }
            )
            continue

        if access.extension == UserExtensionAccess.Extension.ANKI:
            status = ExtensionSyncLedger.Status.SKIPPED
            details = {"reason": "anki_server_sync_deferred"}
            error_message = ""
        else:
            status, details, error_message = _sync_habitica_access(
                access=access,
                sync_date=sync_day,
                dry_run=dry_run,
            )

        summary["processed"] += 1
        if status == ExtensionSyncLedger.Status.OK:
            summary["ok"] += 1
        elif status == ExtensionSyncLedger.Status.ERROR:
            summary["error"] += 1
        else:
            summary["skipped"] += 1

        if not dry_run:
            if status in {ExtensionSyncLedger.Status.OK, ExtensionSyncLedger.Status.ERROR}:
                record_extension_sync(
                    user=access.user,
                    extension=access.extension,
                    status=status,
                    payload=details,
                    error=error_message,
                )
            ExtensionSyncLedger.objects.create(
                user=access.user,
                extension=access.extension,
                sync_date=sync_day,
                status=status,
                details_json={**details, "error": error_message} if error_message else details,
            )

        summary["results"].append(
            {
                **row_key,
                "status": status,
                "error": error_message,
                "details": details,
            }
        )
    return summary


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
