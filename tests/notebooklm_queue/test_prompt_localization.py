import tempfile
import unittest
from pathlib import Path

from notebooklm_queue import prompt_localization


class PromptLocalizationTests(unittest.TestCase):
    def test_localize_sections_deep_merges_prompt_overrides(self):
        localization = prompt_localization.PromptLocalization(
            locale="da",
            prompt_ui=prompt_localization.PROMPT_UI_STRINGS["da"],
            course_context_ui=prompt_localization.COURSE_CONTEXT_UI_STRINGS["da"],
            prompt_overrides={
                "audio_prompt_strategy": {
                    "audience": "en bachelorstuderende i psykologi",
                    "prompt_types": {
                        "single_reading": {
                            "focus": ["den centrale pointe"]
                        }
                    },
                }
            },
            course_context_translations={},
            omit_untranslated_course_context=True,
            fail_on_missing_course_context_translations=False,
        )

        localized = prompt_localization.localize_sections(
            {
                "audio_prompt_strategy": {
                    "audience": "a bachelor's-level psychology student",
                    "prompt_types": {
                        "single_reading": {
                            "focus": ["the key point", "the main distinction"]
                        },
                        "short": {"focus": ["carry-forward idea"]},
                    },
                }
            },
            localization,
        )

        self.assertEqual(
            localized["audio_prompt_strategy"]["audience"],
            "en bachelorstuderende i psykologi",
        )
        self.assertEqual(
            localized["audio_prompt_strategy"]["prompt_types"]["single_reading"]["focus"],
            ["den centrale pointe"],
        )
        self.assertEqual(
            localized["audio_prompt_strategy"]["prompt_types"]["short"]["focus"],
            ["carry-forward idea"],
        )

    def test_localize_course_context_text_omits_missing_english_when_configured(self):
        localization = prompt_localization.PromptLocalization(
            locale="da",
            prompt_ui=prompt_localization.PROMPT_UI_STRINGS["da"],
            course_context_ui=prompt_localization.COURSE_CONTEXT_UI_STRINGS["da"],
            prompt_overrides={},
            course_context_translations={
                "Assessment is theory-laden and not method-neutral.": (
                    "Assessment er teoriladet og ikke metodeneutral."
                )
            },
            omit_untranslated_course_context=True,
            fail_on_missing_course_context_translations=False,
        )
        missing: set[str] = set()

        translated = prompt_localization.localize_course_context_text(
            "Assessment is theory-laden and not method-neutral.",
            localization=localization,
            missing_texts=missing,
        )
        omitted = prompt_localization.localize_course_context_text(
            "Action is a key unit for linking person and environment.",
            localization=localization,
            missing_texts=missing,
        )
        danish = prompt_localization.localize_course_context_text(
            "Forelaesningen handler om agency og kontekst.",
            localization=localization,
            missing_texts=missing,
        )

        self.assertEqual(translated, "Assessment er teoriladet og ikke metodeneutral.")
        self.assertEqual(omitted, "")
        self.assertEqual(danish, "Forelaesningen handler om agency og kontekst.")
        self.assertIn(
            "Action is a key unit for linking person and environment.",
            missing,
        )

    def test_resolve_prompt_localization_loads_wrapper_assets(self):
        with tempfile.TemporaryDirectory():
            repo_root = Path(__file__).resolve().parents[2]
            prompt_config_path = (
                repo_root
                / "notebooklm-podcast-auto"
                / "personlighedspsykologi-da"
                / "prompt_config.json"
            )
            config = prompt_localization.normalize_prompt_localization(
                {
                    "enabled": True,
                    "default_locale": "en",
                    "locales": {
                        "da": {
                            "prompt_overrides_path": "../personlighedspsykologi/locales/da.prompt.json",
                            "course_context_translations_path": "../personlighedspsykologi/locales/da.course_context.json",
                            "omit_untranslated_course_context": True,
                        }
                    },
                }
            )

            localization = prompt_localization.resolve_prompt_localization(
                repo_root=repo_root,
                prompt_config_path=prompt_config_path,
                config=config,
                prompt_locale="da",
            )

        self.assertEqual(localization.locale, "da")
        self.assertEqual(
            localization.prompt_overrides["audio_prompt_strategy"]["audience"],
            "en bachelorstuderende i psykologi",
        )
        self.assertTrue(localization.omit_untranslated_course_context)
        self.assertIn("anchor", localization.course_context_translations)


if __name__ == "__main__":
    unittest.main()
