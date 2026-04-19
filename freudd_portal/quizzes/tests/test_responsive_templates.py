from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase


class ResponsiveTemplateRulesTests(SimpleTestCase):
    databases = {"default"}

    def _template_text(self, relative_path: str) -> str:
        template_path = Path(settings.BASE_DIR) / "templates" / relative_path
        return template_path.read_text(encoding="utf-8")

    def test_subject_detail_uses_compact_app_shell_on_tablet_mobile(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn("@media (max-width: 1180px)", body)
        self.assertIn("grid-template-columns: minmax(62px, 84px) minmax(0, 1fr);", body)
        self.assertIn(".subject-mobile-topbar", body)
        self.assertNotIn("display: none !important;", body)

    def test_base_mobile_navigation_uses_subjects_quiz_cup_and_indstillinger_order_with_icons(self) -> None:
        body = self._template_text("base.html")
        mobile_nav_start = body.index("<nav class=\"mobile-tabbar\"")
        mobile_nav_end = body.index("</nav>", mobile_nav_start)
        mobile_nav = body[mobile_nav_start:mobile_nav_end]
        self.assertIn("data-mobile-nav", body)
        self.assertNotIn("data-header-menu-toggle", body)
        self.assertNotIn("data-header-menu-panel", body)
        self.assertIn("<span class=\"mobile-tab-label\">Mine fag</span>", body)
        self.assertIn("<span class=\"mobile-tab-label\">scoreboard</span>", body)
        self.assertIn("<span class=\"mobile-tab-label\">Indstillinger</span>", body)
        self.assertIn("mobile-tab-icon--subjects", body)
        self.assertIn("mobile-tab-icon--cup", body)
        self.assertIn("mobile-tab-icon--overview", body)
        self.assertIn("viewBox=\"0 0 24 24\"", body)
        self.assertLess(mobile_nav.index(">Mine fag</span>"), mobile_nav.index(">scoreboard</span>"))
        self.assertLess(mobile_nav.index(">scoreboard</span>"), mobile_nav.index(">Indstillinger</span>"))
        self.assertIn("data-subject-menu-toggle", body)
        self.assertIn("data-subject-menu-list", body)
        self.assertIn("document.body.appendChild(list);", body)
        self.assertIn("nav.contains(target) || list.contains(target)", body)
        self.assertIn("box-shadow: 0 20px 42px rgba(15, 95, 140, 0.22), 0 6px 14px rgba(11, 75, 111, 0.14);", body)

    def test_progress_template_has_mobile_history_cards_and_last_opened_subject_badge_hook(self) -> None:
        body = self._template_text("quizzes/progress.html")
        self.assertIn("quiz-history-mobile", body)
        self.assertIn("quiz-history-card", body)
        self.assertIn("last_opened_subject_slug", body)

    def test_leaderboard_template_has_quiz_cup_layout_sections(self) -> None:
        body = self._template_text("quizzes/leaderboard.html")
        self.assertIn("cup-tabs", body)
        self.assertIn("cup-podium", body)
        self.assertIn("cup-table-shell", body)
        self.assertIn("data-cup-expand", body)
        self.assertIn("cup-participation-note", body)

    def test_leaderboard_template_compiles_and_renders(self) -> None:
        request = RequestFactory().get("/leaderboard/personlighedspsykologi")
        request.user = AnonymousUser()
        template = get_template("quizzes/leaderboard.html")
        rendered = template.render(
            {
                "subject": SimpleNamespace(title="Personlighedspsykologi", slug="personlighedspsykologi"),
                "subject_tabs": [
                    {
                        "title": "Personlighedspsykologi",
                        "url": "/leaderboard/personlighedspsykologi",
                        "icon": "psychology",
                        "is_active": True,
                    }
                ],
                "leaderboard_profile": {
                    "public_alias": "",
                    "is_public": False,
                },
                "podium_entries": [],
                "table_entries": [
                    {
                        "rank": 1,
                        "alias": "alpha",
                        "score_points_label": "100",
                        "correct_answers": 1,
                        "quiz_count": 1,
                    }
                ],
                "table_preview_limit": 7,
            },
            request=request,
        )
        self.assertIn("top 50 - Personlighedspsykologi", rendered)

    def test_subject_detail_supports_long_word_wrapping(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn(".active-lecture-title", body)
        self.assertIn("overflow-wrap: anywhere;", body)
        self.assertIn("hyphens: auto;", body)

    def test_subject_detail_exposes_desktop_only_quiz_cup_link(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn("subject-head-actions", body)
        self.assertIn("subject-cup-link", body)
        self.assertIn("subject-cup-icon", body)
        self.assertIn("aria-label=\"scoreboard\"", body)
        self.assertIn("<span class=\"subject-cup-link-label\">scoreboard</span>", body)
        self.assertIn("{% url 'leaderboard-subject' subject_slug=subject.slug %}", body)
        self.assertIn(
            ".subject-head-actions {\n"
            "      display: none;\n"
            "    }",
            body,
        )

    def test_subject_detail_uses_desktop_section_order_on_compact_layout(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn(".lecture-readings {\n      order: 1;", body)
        self.assertIn(".lecture-slides {\n      order: 2;", body)
        self.assertIn(".lecture-podcasts {\n      order: 3;", body)
        self.assertIn(".lecture-quizzes {\n      order: 4;", body)

    def test_subject_detail_has_desktop_timeline_toggle_hook(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertIn("data-subject-rail-toggle", body)
        self.assertIn("data-subject-rail-toggle-label", body)
        self.assertIn("data-subject-path-layout", body)
        self.assertIn(".subject-path-layout.is-rail-hidden", body)
        self.assertRegex(body, r"\.subject-path-tools\s*\{\s*display:\s*grid;")
        self.assertRegex(
            body,
            r"grid-template-columns:\s*minmax\(168px,\s*230px\)\s*minmax\(0,\s*1fr\);",
        )
        self.assertRegex(body, r"\.subject-path-toggle\s*\{\s*min-height:\s*44px;")
        self.assertIn(".subject-path-toggle-icon", body)
        self.assertIn("Vis tidslinje", body)
        self.assertIn("Skjul tidslinje", body)

    def test_subject_detail_has_coarse_pointer_touch_target_guardrails(self) -> None:
        body = self._template_text("quizzes/subject_detail.html")
        self.assertRegex(body, r"@media\s+\(hover:\s*none\),\s*\(pointer:\s*coarse\)")
        self.assertIn("min-width: 44px;", body)
        self.assertIn("min-height: 44px;", body)

    def test_base_template_has_tablet_header_breakpoint(self) -> None:
        body = self._template_text("base.html")
        self.assertIn("@media (max-width: 980px)", body)
        self.assertIn(".nav-group-subjects", body)

    def test_base_template_keeps_topbar_visible_on_mobile(self) -> None:
        body = self._template_text("base.html")
        self.assertIn("@media (max-width: 1180px)", body)
        self.assertIn(".site-header", body)
        self.assertRegex(
            body,
            re.compile(
                r"\.header-inner\s*\{\s*"
                r"padding:\s*var\(--space-2\)\s+var\(--space-3\);\s*"
                r"justify-content:\s*flex-start;\s*"
                r"align-items:\s*center;\s*"
                r"flex-wrap:\s*nowrap;\s*"
                r"\}",
                re.MULTILINE,
            ),
        )
        self.assertRegex(body, r"\.nav-links\s*\{\s*display:\s*none;\s*\}")
        self.assertNotIn(".mobile-header-menu-button", body)
        self.assertNotIn("is-mobile-menu-open", body)
        self.assertNotIn(
            ".site-header {\n          display: none;\n        }",
            body,
        )

    def test_base_template_guards_against_horizontal_overflow_drift(self) -> None:
        body = self._template_text("base.html")
        self.assertRegex(
            body,
            re.compile(
                r"html\s*\{\s*max-width:\s*100%;\s*overflow-x:\s*clip;\s*\}",
                re.MULTILINE,
            ),
        )
        self.assertIn("max-width: 100%;", body)
        self.assertIn("overflow-x: clip;", body)
        self.assertIn("@supports not (overflow: clip)", body)
        self.assertIn("overflow-x: hidden;", body)

    def test_quiz_wrapper_supports_long_option_copy_without_horizontal_overflow(self) -> None:
        body = self._template_text("quizzes/wrapper.html")
        self.assertIn(".quiz-shell {\n    display: grid;\n    gap: var(--space-4);\n    min-width: 0;\n  }", body)
        self.assertIn(".quiz-stage {\n    border: 1px solid var(--border);", body)
        self.assertIn(
            ".quiz-question {\n    margin: 0 0 var(--space-4);\n    font-family: var(--font-body);\n    font-weight: 600;",
            body,
        )
        self.assertIn("padding: var(--space-5);\n    min-width: 0;\n  }", body)
        self.assertIn("width: 100%;\n    min-width: 0;\n    min-height: var(--control-min-height);", body)
        self.assertIn(".quiz-option-text {\n    flex: 1 1 auto;\n    min-width: 0;", body)
        self.assertIn('id="quiz-score-progress"', body)
        self.assertIn("const scoreProgressNode = document.getElementById(\"quiz-score-progress\");", body)

    def test_quiz_wrapper_summary_exposes_quiz_cup_link_and_rank_feedback_hook(self) -> None:
        body = self._template_text("quizzes/wrapper.html")
        self.assertIn("quiz-cup-summary", body)
        self.assertIn('id="quiz-cup-rank-feedback"', body)
        self.assertIn("Gå til scoreboard", body)
        self.assertIn("const quizCupUrl =", body)
        self.assertIn("quizCupState = body.quiz_cup;", body)

    def test_base_template_exposes_page_class_hook_for_scoped_layout_modes(self) -> None:
        body = self._template_text("base.html")
        self.assertIn("page-{{ request.resolver_match.url_name }}", body)
        self.assertIn("has-mobile-nav", body)
