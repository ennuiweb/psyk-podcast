"""Request guards for portal authentication flows."""

from __future__ import annotations

from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)

from .auth_origins import google_auth_origin_allowed


class GoogleOAuthOriginMiddleware:
    """Prevent Google OAuth from starting with an unapproved callback origin."""

    google_login_path = "/accounts/google/login/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if (
            getattr(settings, "FREUDD_AUTH_GOOGLE_ENABLED", False)
            and request.path == self.google_login_path
            and not google_auth_origin_allowed(request)
        ):
            canonical_login_url = getattr(
                settings,
                "FREUDD_AUTH_GOOGLE_CANONICAL_LOGIN_URL",
                "",
            ).strip()
            if canonical_login_url:
                return HttpResponseRedirect(canonical_login_url)
            return HttpResponseBadRequest("Google login is not available from this origin.")

        return self.get_response(request)
