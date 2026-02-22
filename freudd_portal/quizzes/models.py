"""Data model for user quiz progress."""

from __future__ import annotations

from django.conf import settings
from django.db import models


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


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.CharField(max_length=16, default="F26")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.semester}"


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
        LOCKED = "locked", "Låst"
        ACTIVE = "active", "Aktiv"
        COMPLETED = "completed", "Fuldført"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_slug = models.CharField(max_length=64)
    unit_key = models.CharField(max_length=32)
    unit_label = models.CharField(max_length=128)
    sequence_index = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LOCKED)
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


class UserExtensionToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="ext_token_user_revoked_idx"),
            models.Index(fields=["token_prefix"], name="ext_token_prefix_idx"),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"{self.user_id}:{self.token_prefix}:{state}"


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
