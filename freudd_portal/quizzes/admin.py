from django.contrib import admin

from .models import QuizProgress, SubjectEnrollment, UserPreference


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


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "semester", "updated_at")
    search_fields = ("user__username", "user__email", "semester")
    list_filter = ("semester", "updated_at")


@admin.register(SubjectEnrollment)
class SubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "enrolled_at", "updated_at")
    search_fields = ("user__username", "user__email", "subject_slug")
    list_filter = ("subject_slug", "enrolled_at")
