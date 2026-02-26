"""Services for personal reading/podcast tracking."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .content_services import load_subject_content_manifest
from .models import QuizProgress, UserPodcastMark, UserReadingMark
from .services import load_quiz_label_mapping


def podcast_key_for_asset(*, lecture_key: str, reading_key: str | None, asset: dict[str, Any]) -> str:
    source = (
        str(asset.get("source_audio_url") or "").strip()
        or str(asset.get("url") or "").strip()
        or str(asset.get("title") or "").strip()
    )
    payload = "|".join(
        [
            str(lecture_key or "").strip().upper(),
            str(reading_key or "").strip(),
            source,
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def subject_tracking_index(subject_slug: str) -> dict[str, set[tuple[str, str | None, str]]]:
    manifest = load_subject_content_manifest(subject_slug)
    reading_keys: set[tuple[str, str | None, str]] = set()
    podcast_keys: set[tuple[str, str | None, str]] = set()
    for lecture in manifest.get("lectures") or []:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        if not lecture_key:
            continue

        for reading in lecture.get("readings") or []:
            if not isinstance(reading, dict):
                continue
            reading_key = str(reading.get("reading_key") or "").strip()
            if not reading_key:
                continue
            reading_keys.add((lecture_key, reading_key, ""))
            assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
            for podcast in assets.get("podcasts") or []:
                if not isinstance(podcast, dict):
                    continue
                podcast_keys.add(
                    (
                        lecture_key,
                        reading_key,
                        podcast_key_for_asset(
                            lecture_key=lecture_key,
                            reading_key=reading_key,
                            asset=podcast,
                        ),
                    )
                )

        lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
        for podcast in lecture_assets.get("podcasts") or []:
            if not isinstance(podcast, dict):
                continue
            podcast_keys.add(
                (
                    lecture_key,
                    None,
                    podcast_key_for_asset(
                        lecture_key=lecture_key,
                        reading_key=None,
                        asset=podcast,
                    ),
                )
            )

    return {
        "reading_keys": reading_keys,
        "podcast_keys": podcast_keys,
    }


def set_reading_mark(
    *,
    user,
    subject_slug: str,
    lecture_key: str,
    reading_key: str,
    marked: bool,
) -> bool:
    slug = str(subject_slug or "").strip().lower()
    lecture = str(lecture_key or "").strip().upper()
    reading = str(reading_key or "").strip()
    if marked:
        UserReadingMark.objects.get_or_create(
            user=user,
            subject_slug=slug,
            lecture_key=lecture,
            reading_key=reading,
        )
        return True
    UserReadingMark.objects.filter(
        user=user,
        subject_slug=slug,
        lecture_key=lecture,
        reading_key=reading,
    ).delete()
    return False


def set_podcast_mark(
    *,
    user,
    subject_slug: str,
    lecture_key: str,
    reading_key: str | None,
    podcast_key: str,
    marked: bool,
) -> bool:
    slug = str(subject_slug or "").strip().lower()
    lecture = str(lecture_key or "").strip().upper()
    reading = str(reading_key or "").strip() or None
    key = str(podcast_key or "").strip().lower()
    if marked:
        UserPodcastMark.objects.get_or_create(
            user=user,
            subject_slug=slug,
            lecture_key=lecture,
            reading_key=reading,
            podcast_key=key,
        )
        return True
    UserPodcastMark.objects.filter(
        user=user,
        subject_slug=slug,
        lecture_key=lecture,
        reading_key=reading,
        podcast_key=key,
    ).delete()
    return False


def mark_sets_for_subject(*, user, subject_slug: str) -> dict[str, set[tuple[str, str | None, str]]]:
    slug = str(subject_slug or "").strip().lower()
    reading_marks = {
        (str(lecture_key).strip().upper(), str(reading_key).strip(), "")
        for lecture_key, reading_key in UserReadingMark.objects.filter(
            user=user,
            subject_slug=slug,
        ).values_list("lecture_key", "reading_key")
    }
    podcast_marks = {
        (
            str(lecture_key).strip().upper(),
            (str(reading_key).strip() or None) if reading_key else None,
            str(podcast_key).strip().lower(),
        )
        for lecture_key, reading_key, podcast_key in UserPodcastMark.objects.filter(
            user=user,
            subject_slug=slug,
        ).values_list("lecture_key", "reading_key", "podcast_key")
    }
    return {
        "reading_marks": reading_marks,
        "podcast_marks": podcast_marks,
    }


def annotate_subject_lectures_with_marks(
    *,
    user,
    subject_slug: str,
    lectures: list[dict[str, Any]],
) -> None:
    marks = mark_sets_for_subject(user=user, subject_slug=subject_slug)
    reading_mark_set = marks["reading_marks"]
    podcast_mark_set = marks["podcast_marks"]

    for lecture in lectures:
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
        lecture_podcasts = lecture_assets.get("podcasts") if isinstance(lecture_assets.get("podcasts"), list) else []
        for podcast in lecture_podcasts:
            if not isinstance(podcast, dict):
                continue
            podcast_key = podcast_key_for_asset(
                lecture_key=lecture_key,
                reading_key=None,
                asset=podcast,
            )
            podcast["podcast_key"] = podcast_key
            podcast["is_marked_listened"] = (lecture_key, None, podcast_key) in podcast_mark_set

        readings = lecture.get("readings") if isinstance(lecture.get("readings"), list) else []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            reading_key = str(reading.get("reading_key") or "").strip()
            reading["is_marked_read"] = (lecture_key, reading_key, "") in reading_mark_set
            assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
            reading_podcasts = assets.get("podcasts") if isinstance(assets.get("podcasts"), list) else []
            for podcast in reading_podcasts:
                if not isinstance(podcast, dict):
                    continue
                podcast_key = podcast_key_for_asset(
                    lecture_key=lecture_key,
                    reading_key=reading_key,
                    asset=podcast,
                )
                podcast["podcast_key"] = podcast_key
                podcast["is_marked_listened"] = (
                    lecture_key,
                    reading_key,
                    podcast_key,
                ) in podcast_mark_set


def personal_tracking_summary_for_user(*, user, subjects: list[dict[str, str]]) -> list[dict[str, Any]]:
    subject_slugs = [str(item.get("slug") or "").strip().lower() for item in subjects]
    reading_marks_by_subject: dict[str, set[tuple[str, str | None, str]]] = defaultdict(set)
    podcast_marks_by_subject: dict[str, set[tuple[str, str | None, str]]] = defaultdict(set)

    for subject_slug, lecture_key, reading_key in UserReadingMark.objects.filter(
        user=user,
        subject_slug__in=subject_slugs,
    ).values_list("subject_slug", "lecture_key", "reading_key"):
        reading_marks_by_subject[str(subject_slug).strip().lower()].add(
            (str(lecture_key).strip().upper(), str(reading_key).strip(), "")
        )

    for subject_slug, lecture_key, reading_key, podcast_key in UserPodcastMark.objects.filter(
        user=user,
        subject_slug__in=subject_slugs,
    ).values_list("subject_slug", "lecture_key", "reading_key", "podcast_key"):
        podcast_marks_by_subject[str(subject_slug).strip().lower()].add(
            (
                str(lecture_key).strip().upper(),
                (str(reading_key).strip() or None) if reading_key else None,
                str(podcast_key).strip().lower(),
            )
        )

    labels = load_quiz_label_mapping()
    quiz_ids_by_subject: dict[str, set[str]] = defaultdict(set)
    for quiz_id, label in labels.items():
        slug = str(label.subject_slug or "").strip().lower()
        if slug:
            quiz_ids_by_subject[slug].add(quiz_id)
    completed_quiz_ids = set(
        QuizProgress.objects.filter(user=user, status=QuizProgress.Status.COMPLETED).values_list(
            "quiz_id",
            flat=True,
        )
    )

    summaries: list[dict[str, Any]] = []
    for subject in subjects:
        slug = str(subject.get("slug") or "").strip().lower()
        manifest = load_subject_content_manifest(slug)

        reading_keys: set[tuple[str, str | None, str]] = set()
        podcast_keys: set[tuple[str, str | None, str]] = set()
        for lecture in manifest.get("lectures") or []:
            if not isinstance(lecture, dict):
                continue
            lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
            if not lecture_key:
                continue

            lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
            lecture_podcasts = lecture_assets.get("podcasts") if isinstance(lecture_assets.get("podcasts"), list) else []
            for podcast in lecture_podcasts:
                if not isinstance(podcast, dict):
                    continue
                podcast_keys.add(
                    (
                        lecture_key,
                        None,
                        podcast_key_for_asset(
                            lecture_key=lecture_key,
                            reading_key=None,
                            asset=podcast,
                        ),
                    )
                )

            for reading in lecture.get("readings") or []:
                if not isinstance(reading, dict):
                    continue
                reading_key = str(reading.get("reading_key") or "").strip()
                if not reading_key:
                    continue
                reading_keys.add((lecture_key, reading_key, ""))
                assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
                reading_podcasts = assets.get("podcasts") if isinstance(assets.get("podcasts"), list) else []
                for podcast in reading_podcasts:
                    if not isinstance(podcast, dict):
                        continue
                    podcast_keys.add(
                        (
                            lecture_key,
                            reading_key,
                            podcast_key_for_asset(
                                lecture_key=lecture_key,
                                reading_key=reading_key,
                                asset=podcast,
                            ),
                        )
                    )

        subject_read_marks = reading_marks_by_subject.get(slug, set())
        subject_podcast_marks = podcast_marks_by_subject.get(slug, set())
        quiz_ids = quiz_ids_by_subject.get(slug, set())
        completed_quizzes = len(quiz_ids.intersection(completed_quiz_ids))
        summaries.append(
            {
                "slug": slug,
                "title": subject.get("title") or slug,
                "detail_url": subject.get("detail_url") or "",
                "readings_marked": len(reading_keys.intersection(subject_read_marks)),
                "readings_total": len(reading_keys),
                "podcasts_marked": len(podcast_keys.intersection(subject_podcast_marks)),
                "podcasts_total": len(podcast_keys),
                "quizzes_completed": completed_quizzes,
                "quizzes_total": len(quiz_ids),
            }
        )

    return summaries
