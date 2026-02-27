from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ResponsiveTemplateRulesTests(SimpleTestCase):
    def _template_text(self, relative_path: str) -> str:
        template_path = Path(settings.BASE_DIR) / "templates" / relative_path
        return template_path.read_text(encoding="utf-8")

    def test_subject_detail_stacks_layout_below_900px(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn("@media (max-width: 900px)", body)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", body)
        self.assertIn("active-lecture-card::before {\n      display: none;", body)

    def test_subject_detail_supports_long_word_wrapping(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn(".active-lecture-title", body)
        self.assertIn("overflow-wrap: anywhere;", body)
        self.assertIn("hyphens: auto;", body)

    def test_subject_detail_has_coarse_pointer_touch_target_guardrails(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn("@media (hover: none), (pointer: coarse)", body)
        self.assertIn("min-width: 44px;", body)
        self.assertIn("min-height: 44px;", body)

    def test_base_template_has_tablet_header_breakpoint(self) -> None:
        body = self._template_text("base.html")
        self.assertIn("@media (max-width: 980px)", body)
        self.assertIn(".nav-group-subjects", body)
