"""Data model for user quiz progress."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


PUBLIC_ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,24}$")


class QuizProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "I gang"
        COMPLETED = "completed", "Fuldført"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    quiz_id = models.CharField(max_length=8)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    state_json = models.JSONField(default=dict)
    raw_state_payload = models.TextField(blank=True, null=True)
    answers_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    last_view = models.CharField(max_length=32, default="question")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "quiz_id"], name="uq_user_quiz_progress"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="quiz_prog_user_status_idx"),
            models.Index(fields=["quiz_id"], name="quiz_prog_quiz_id_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.quiz_id}:{self.status}"


class SubjectEnrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "subject_slug"], name="uq_user_subject_enrollment"),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug"], name="subj_enroll_user_slug_idx"),
            models.Index(fields=["subject_slug"], name="subj_enroll_slug_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.subject_slug}"


class UserInterfacePreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    design_system = models.CharField(max_length=32, default="classic")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.design_system}"


class UserGamificationProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    xp_total = models.PositiveIntegerField(default=0)
    streak_days = models.PositiveIntegerField(default=0)
    current_level = models.PositiveIntegerField(default=1)
    last_activity_date = models.DateField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}:lvl={self.current_level}:xp={self.xp_total}"


class UserUnitProgress(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        COMPLETED = "completed", "Fuldført"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    unit_key = models.CharField(max_length=32)
    unit_label = models.CharField(max_length=128)
    sequence_index = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    completed_quizzes = models.PositiveIntegerField(default=0)
    total_quizzes = models.PositiveIntegerField(default=0)
    mastery_ratio = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "subject_slug", "unit_key"], name="uq_user_subject_unit"),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug"], name="unit_prog_user_subject_idx"),
            models.Index(fields=["user", "status"], name="unit_prog_user_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.subject_slug}:{self.unit_key}:{self.status}"


class UserLectureProgress(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        COMPLETED = "completed", "Fuldført"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    lecture_key = models.CharField(max_length=32)
    lecture_title = models.CharField(max_length=255)
    sequence_index = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    completed_quizzes = models.PositiveIntegerField(default=0)
    total_quizzes = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "subject_slug", "lecture_key"],
                name="uq_user_subject_lecture",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug"], name="lecture_prog_user_subject_idx"),
            models.Index(fields=["user", "status"], name="lecture_prog_user_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.subject_slug}:{self.lecture_key}:{self.status}"


class UserReadingProgress(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        COMPLETED = "completed", "Fuldført"
        NO_QUIZ = "no_quiz", "Ingen quiz"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    lecture_key = models.CharField(max_length=32)
    reading_key = models.CharField(max_length=96)
    reading_title = models.CharField(max_length=255)
    sequence_index = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    completed_quizzes = models.PositiveIntegerField(default=0)
    total_quizzes = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "subject_slug", "lecture_key", "reading_key"],
                name="uq_user_subject_lecture_reading",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug", "lecture_key"], name="reading_prog_user_lecture_idx"),
            models.Index(fields=["user", "status"], name="reading_prog_user_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.subject_slug}:{self.lecture_key}:{self.reading_key}:{self.status}"


class UserExtensionAccess(models.Model):
    class Extension(models.TextChoices):
        HABITICA = "habitica", "Habitica"
        ANKI = "anki", "Anki"

    class SyncStatus(models.TextChoices):
        IDLE = "idle", "Idle"
        OK = "ok", "OK"
        ERROR = "error", "Error"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    extension = models.CharField(max_length=16, choices=Extension.choices)
    enabled = models.BooleanField(default=False)
    enabled_at = models.DateTimeField(blank=True, null=True)
    enabled_by = models.CharField(max_length=150, blank=True)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    last_sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.IDLE)
    last_sync_error = models.TextField(blank=True)
    last_sync_payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "extension"], name="uq_user_extension_access"),
        ]
        indexes = [
            models.Index(fields=["user", "enabled"], name="ext_access_user_enabled_idx"),
            models.Index(fields=["extension", "enabled"], name="ext_access_ext_enabled_idx"),
        ]

    def __str__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"{self.user_id}:{self.extension}:{state}"


class UserExtensionCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    extension = models.CharField(max_length=16, choices=UserExtensionAccess.Extension.choices)
    encrypted_payload = models.TextField()
    key_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rotated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "extension"], name="uq_user_extension_credential"),
        ]
        indexes = [
            models.Index(fields=["user", "extension"], name="ext_cred_user_ext_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.extension}:v{self.key_version}"


class ExtensionSyncLedger(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"
        SKIPPED = "skipped", "Skipped"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    extension = models.CharField(max_length=16, choices=UserExtensionAccess.Extension.choices)
    sync_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices)
    details_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "extension", "sync_date"],
                name="uq_user_extension_sync_date",
            ),
        ]
        indexes = [
            models.Index(fields=["extension", "sync_date"], name="ext_ledger_ext_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.extension}:{self.sync_date}:{self.status}"


class DailyGamificationStat(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    answered_delta = models.PositiveIntegerField(default=0)
    completed_delta = models.PositiveIntegerField(default=0)
    goal_target = models.PositiveIntegerField(default=20)
    goal_met = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="uq_user_gamification_day"),
        ]
        indexes = [
            models.Index(fields=["user", "date"], name="daily_stat_user_date_idx"),
            models.Index(fields=["user", "goal_met"], name="daily_stat_user_goal_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.date}:goal={self.goal_met}"


class UserReadingMark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    lecture_key = models.CharField(max_length=32)
    reading_key = models.CharField(max_length=96)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "subject_slug", "lecture_key", "reading_key"],
                name="uq_user_subject_lecture_reading_mark",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug"], name="reading_mark_user_subject_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.subject_slug}:{self.lecture_key}:{self.reading_key}"


class UserPodcastMark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    lecture_key = models.CharField(max_length=32)
    reading_key = models.CharField(max_length=96, blank=True, null=True)
    podcast_key = models.CharField(max_length=40)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "subject_slug", "lecture_key", "reading_key", "podcast_key"],
                condition=Q(reading_key__isnull=False),
                name="uq_user_subject_lecture_reading_podcast_mark",
            ),
            models.UniqueConstraint(
                fields=["user", "subject_slug", "lecture_key", "podcast_key"],
                condition=Q(reading_key__isnull=True),
                name="uq_user_subject_lecture_podcast_mark",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "subject_slug"], name="podcast_mark_user_subject_idx"),
        ]

    def __str__(self) -> str:
        reading = self.reading_key or "-"
        return f"{self.user_id}:{self.subject_slug}:{self.lecture_key}:{reading}:{self.podcast_key}"


class UserLeaderboardProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    public_alias = models.CharField(max_length=24, blank=True, null=True)
    public_alias_normalized = models.CharField(max_length=24, blank=True, null=True, unique=True)
    is_public = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["is_public", "public_alias_normalized"],
                name="leader_public_alias_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        alias = str(self.public_alias or "").strip()
        if alias and not PUBLIC_ALIAS_RE.match(alias):
            raise ValidationError(
                {
                    "public_alias": (
                        "Alias skal være 3-24 tegn og må kun indeholde bogstaver, tal, '_' eller '-'."
                    )
                }
            )

    def save(self, *args, **kwargs):
        alias = str(self.public_alias or "").strip()
        self.public_alias = alias or None
        self.public_alias_normalized = alias.lower() if alias else None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        alias = self.public_alias or "-"
        state = "public" if self.is_public else "private"
        return f"{self.user_id}:{alias}:{state}"
