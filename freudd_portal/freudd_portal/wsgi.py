"""WSGI config for freudd."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "freudd_portal.settings")

application = get_wsgi_application()
