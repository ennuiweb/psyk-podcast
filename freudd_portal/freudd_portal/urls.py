"""Top-level URL routing for freudd."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from quizzes import views as quiz_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup", quiz_views.signup_view, name="signup"),
    path("accounts/login", quiz_views.login_view, name="login"),
    path("accounts/logout", quiz_views.logout_view, name="logout"),
    path("", include("quizzes.urls")),
]

if settings.FREUDD_AUTH_GOOGLE_ENABLED:
    urlpatterns += [
        path("accounts/", include("allauth.socialaccount.providers.google.urls")),
        path("accounts/3rdparty/", include("allauth.socialaccount.urls")),
    ]
