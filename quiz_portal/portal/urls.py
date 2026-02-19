"""Top-level URL routing for the quiz portal."""

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
