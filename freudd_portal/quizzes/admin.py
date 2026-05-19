from django.contrib import admin

from .models import (
    FlashcardReview,
    FlashcardUserAnswer,
    QuizProgress,
    SubjectEnrollment,
    UserInterfacePreference,
    UserNotificationPreference,
    UserLeaderboardProfile,
    UserPodcastMark,
    UserReadingMark,
)


@admin.register(QuizProgress)
class QuizProgressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "quiz_id",
        "status",
        "answers_count",
        "question_count",
        "last_view",
        "updated_at",
    )
    search_fields = ("quiz_id", "user__username", "user__email")
    list_filter = ("status", "updated_at")


@admin.register(SubjectEnrollment)
class SubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "enrolled_at", "updated_at")
    search_fields = ("user__username", "user__email", "subject_slug")
    list_filter = ("subject_slug", "enrolled_at")


@admin.register(FlashcardReview)
class FlashcardReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "subject_slug",
        "deck_slug",
        "card_id",
        "rating",
        "review_count",
        "last_reviewed_at",
        "next_review_at",
    )
    search_fields = ("user__username", "user__email", "subject_slug", "deck_slug", "card_id")
    list_filter = ("subject_slug", "deck_slug", "rating", "last_reviewed_at")


@admin.register(FlashcardUserAnswer)
class FlashcardUserAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "deck_slug", "card_id", "updated_at")
    search_fields = ("user__username", "user__email", "subject_slug", "deck_slug", "card_id", "answer_text")
    list_filter = ("subject_slug", "deck_slug", "updated_at")


@admin.register(UserInterfacePreference)
class UserInterfacePreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "design_system", "updated_at")
    search_fields = ("user__username", "user__email", "design_system")
    list_filter = ("design_system", "updated_at")


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "activity_notifications_enabled", "updated_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("activity_notifications_enabled", "updated_at")


@admin.register(UserReadingMark)
class UserReadingMarkAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "lecture_key", "reading_key", "marked_at")
    search_fields = ("user__username", "subject_slug", "lecture_key", "reading_key")
    list_filter = ("subject_slug", "lecture_key", "marked_at")


@admin.register(UserPodcastMark)
class UserPodcastMarkAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "lecture_key", "reading_key", "podcast_key", "marked_at")
    search_fields = ("user__username", "subject_slug", "lecture_key", "reading_key", "podcast_key")
    list_filter = ("subject_slug", "lecture_key", "marked_at")


@admin.register(UserLeaderboardProfile)
class UserLeaderboardProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "public_alias", "is_public", "updated_at")
    search_fields = ("user__username", "public_alias", "public_alias_normalized")
    list_filter = ("is_public", "updated_at")
