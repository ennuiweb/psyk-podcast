"""Template context processors for UI concerns."""

from __future__ import annotations

import os

from django.conf import settings
from django.urls import reverse

from .models import SubjectEnrollment
from .design_systems import iter_design_system_payload
from .subject_services import load_subject_catalog
from .theme_resolver import (
    resolve_design_system,
)


def _topmenu_enrolled_subjects(request, *, catalog):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return tuple()

    enrolled_slugs = set(
        SubjectEnrollment.objects.filter(user=user).values_list("subject_slug", flat=True)
    )
    if not enrolled_slugs:
        return tuple()

    return tuple(
        {
            "slug": subject.slug,
            "title": subject.title,
            "detail_url": reverse("subject-detail", kwargs={"subject_slug": subject.slug}),
        }
        for subject in catalog.active_subjects
        if subject.slug in enrolled_slugs
    )


def design_system_context(request):
    resolved = resolve_design_system(request)
    catalog = load_subject_catalog()
    default_subject = catalog.active_subjects[0].slug if catalog.active_subjects else ""
    enrolled_subjects = _topmenu_enrolled_subjects(request, catalog=catalog)
    plausible_domain = getattr(
        settings,
        "FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN",
        os.environ.get("FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN", ""),
    ).strip()
    plausible_src = getattr(
        settings,
        "FREUDD_ANALYTICS_PLAUSIBLE_SRC",
        os.environ.get("FREUDD_ANALYTICS_PLAUSIBLE_SRC", "https://plausible.io/js/script.js"),
    ).strip()
    return {
        "design_systems": list(iter_design_system_payload()),
        "active_design_system": {
            "key": resolved.key,
            "label": resolved.definition.label,
            "description": resolved.definition.description,
            "source": resolved.source,
            "is_preview": resolved.is_preview,
        },
        "active_design_system_key": resolved.key,
        "leaderboard_default_subject_slug": default_subject,
        "topmenu_enrolled_subjects": enrolled_subjects,
        "google_auth_enabled": bool(getattr(settings, "FREUDD_AUTH_GOOGLE_ENABLED", False)),
        "plausible_domain": plausible_domain,
        "plausible_src": plausible_src,
    }
