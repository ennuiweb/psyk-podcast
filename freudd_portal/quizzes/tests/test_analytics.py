from __future__ import annotations

from django.test import TestCase, override_settings


class AnalyticsTemplateTests(TestCase):
    def test_login_page_omits_plausible_script_when_domain_not_configured(self) -> None:
        with override_settings(FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN=""):
            response = self.client.get("/accounts/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "plausible.io/js/script.js")
        self.assertNotContains(response, "data-domain=")

    def test_login_page_includes_plausible_script_when_configured(self) -> None:
        with override_settings(
            FREUDD_ANALYTICS_PLAUSIBLE_DOMAIN="freudd.dk",
            FREUDD_ANALYTICS_PLAUSIBLE_SRC="https://plausible.io/js/script.js",
        ):
            response = self.client.get("/accounts/login")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<script defer data-domain="freudd.dk" src="https://plausible.io/js/script.js"></script>',
            html=True,
        )
