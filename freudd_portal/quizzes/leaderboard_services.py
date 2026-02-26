"""Services for public leaderboard calculations and profile management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PUBLIC_ALIAS_RE, QuizProgress, UserLeaderboardProfile
from .services import load_quiz_label_mapping


@dataclass(frozen=True)
class LeaderboardSeason:
    key: str
    start_at: datetime
    end_at: datetime
    label: str
    start_date_label: str
    end_date_label: str


def active_half_year_season(now: datetime | None = None) -> LeaderboardSeason:
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, dt_timezone.utc)
    current = current.astimezone(dt_timezone.utc)

    if current.month <= 6:
        start_at = datetime(current.year, 1, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        end_at = datetime(current.year, 7, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        key = f"{current.year}-H1"
    else:
        start_at = datetime(current.year, 7, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        end_at = datetime(current.year + 1, 1, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        key = f"{current.year}-H2"

    end_inclusive = (end_at - timedelta(seconds=1)).date()
    start_date_label = start_at.date().strftime("%d.%m.%Y")
    end_date_label = end_inclusive.strftime("%d.%m.%Y")
    return LeaderboardSeason(
        key=key,
        start_at=start_at,
        end_at=end_at,
        label=f"{key} ({start_date_label}-{end_date_label})",
        start_date_label=start_date_label,
        end_date_label=end_date_label,
    )


def normalize_public_alias(value: object) -> str:
    return str(value or "").strip()


def validate_public_alias(value: object) -> str:
    alias = normalize_public_alias(value)
    if not PUBLIC_ALIAS_RE.match(alias):
        raise ValidationError(
            "Alias skal være 3-24 tegn og må kun indeholde bogstaver, tal, '_' eller '-'."
        )
    return alias


@transaction.atomic
def update_leaderboard_profile(*, user, alias: object, is_public: bool) -> UserLeaderboardProfile:
    profile, _ = UserLeaderboardProfile.objects.get_or_create(user=user)
    alias_candidate = normalize_public_alias(alias)

    if alias_candidate:
        profile.public_alias = validate_public_alias(alias_candidate)
    elif not profile.public_alias and is_public:
        raise ValidationError("Alias er påkrævet for at være offentlig i quizligaen.")

    profile.is_public = bool(is_public)
    profile.full_clean()
    try:
        profile.save()
    except IntegrityError as exc:
        raise ValidationError("Alias er allerede i brug.") from exc
    return profile


def get_profile_payload(user) -> dict[str, Any]:
    profile = UserLeaderboardProfile.objects.filter(user=user).first()
    if profile is None:
        return {
            "public_alias": "",
            "is_public": False,
            "has_profile": False,
        }
    return {
        "public_alias": profile.public_alias or "",
        "is_public": bool(profile.is_public),
        "has_profile": True,
    }


def build_subject_leaderboard_snapshot(
    *,
    subject_slug: str,
    limit: int = 50,
    season: LeaderboardSeason | None = None,
) -> dict[str, Any]:
    slug = str(subject_slug or "").strip().lower()
    active_season = season or active_half_year_season()

    labels = load_quiz_label_mapping()
    subject_quiz_ids = {
        quiz_id
        for quiz_id, label in labels.items()
        if str(label.subject_slug or "").strip().lower() == slug
    }
    if not subject_quiz_ids:
        return {
            "subject_slug": slug,
            "season": _season_payload(active_season),
            "participant_count": 0,
            "entries": [],
        }

    public_profiles = {
        row.user_id: row
        for row in UserLeaderboardProfile.objects.filter(
            is_public=True,
            public_alias_normalized__isnull=False,
        )
    }
    if not public_profiles:
        return {
            "subject_slug": slug,
            "season": _season_payload(active_season),
            "participant_count": 0,
            "entries": [],
        }

    rows = QuizProgress.objects.filter(
        quiz_id__in=subject_quiz_ids,
        completed_at__isnull=False,
        completed_at__gte=active_season.start_at,
        completed_at__lt=active_season.end_at,
        user_id__in=public_profiles.keys(),
    ).values("user_id", "quiz_id", "completed_at")

    aggregate_by_user: dict[int, dict[str, Any]] = {}
    for row in rows:
        user_id = int(row["user_id"])
        payload = aggregate_by_user.setdefault(
            user_id,
            {
                "quiz_ids": set(),
                "quiz_count": 0,
                "reached_at": None,
            },
        )
        quiz_id = str(row.get("quiz_id") or "").strip().lower()
        if not quiz_id or quiz_id in payload["quiz_ids"]:
            continue
        payload["quiz_ids"].add(quiz_id)
        payload["quiz_count"] += 1
        completed_at = row.get("completed_at")
        reached_at = payload["reached_at"]
        if reached_at is None or (completed_at and completed_at > reached_at):
            payload["reached_at"] = completed_at

    ranking_rows: list[dict[str, Any]] = []
    for user_id, payload in aggregate_by_user.items():
        if int(payload.get("quiz_count") or 0) <= 0:
            continue
        profile = public_profiles.get(user_id)
        if profile is None or not profile.public_alias:
            continue
        ranking_rows.append(
            {
                "user_id": user_id,
                "alias": profile.public_alias,
                "alias_normalized": profile.public_alias_normalized or profile.public_alias.lower(),
                "quiz_count": int(payload["quiz_count"]),
                "reached_at": payload["reached_at"],
            }
        )

    ranking_rows.sort(
        key=lambda item: (
            -int(item["quiz_count"]),
            item["reached_at"] or datetime.max.replace(tzinfo=dt_timezone.utc),
            str(item["alias_normalized"]),
        )
    )

    entries: list[dict[str, Any]] = []
    for index, item in enumerate(ranking_rows[: max(1, int(limit))], start=1):
        reached_at = item.get("reached_at")
        entries.append(
            {
                "rank": index,
                "alias": item["alias"],
                "quiz_count": item["quiz_count"],
                "reached_at": reached_at.isoformat() if reached_at else None,
            }
        )

    return {
        "subject_slug": slug,
        "season": _season_payload(active_season),
        "participant_count": len(ranking_rows),
        "entries": entries,
    }


def _season_payload(season: LeaderboardSeason) -> dict[str, str]:
    return {
        "key": season.key,
        "label": season.label,
        "start_at": season.start_at.isoformat(),
        "end_at": season.end_at.isoformat(),
        "start_date_label": season.start_date_label,
        "end_date_label": season.end_date_label,
    }
