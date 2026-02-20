from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = REPO_ROOT / "gamifiication"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import config as config_mod
import ingest as ingest_mod
import state as state_mod
import sync as sync_mod


class ParseCardsPayloadTests(unittest.TestCase):
    def test_accepts_wrapped_json(self):
        payload = "Result:\n[{\"front\": \"A\", \"back\": \"B\"}]\nThanks"
        cards = ingest_mod.parse_cards_payload(payload)
        self.assertEqual(cards, [{"front": "A", "back": "B"}])

    def test_rejects_missing_front_or_back(self):
        payload = '[{"front": "A", "back": ""}]'
        with self.assertRaises(ingest_mod.IngestError):
            ingest_mod.parse_cards_payload(payload)


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.units = [
            config_mod.UnitConfig(id="Unit_1", label="Unit 1", anki_tag="Unit_1"),
            config_mod.UnitConfig(id="Unit_2", label="Unit 2", anki_tag="Unit_2"),
            config_mod.UnitConfig(id="Unit_3", label="Unit 3", anki_tag="Unit_3"),
        ]

    def test_status_derivation_completed_active_locked(self):
        current_level, normalized = state_mod.derive_unit_status_updates(
            units=self.units,
            unit_progress={
                "Unit_1": {"total_cards": 10, "mastered_cards": 9},
                "Unit_2": {"total_cards": 10, "mastered_cards": 2},
                "Unit_3": {"total_cards": 10, "mastered_cards": 0},
            },
            mastery_ratio_threshold=0.8,
        )
        self.assertEqual(current_level, 2)
        self.assertEqual(normalized["Unit_1"]["status"], "completed")
        self.assertEqual(normalized["Unit_2"]["status"], "active")
        self.assertEqual(normalized["Unit_3"]["status"], "locked")


class DailyOutcomeTests(unittest.TestCase):
    def _build_config(self) -> config_mod.AppConfig:
        return config_mod.AppConfig(
            anki=config_mod.AnkiConfig(
                endpoint="http://localhost:8765",
                deck_name="Psychology",
                note_model="Basic",
                front_field="Front",
                back_field="Back",
                default_tags=["GamifiedSRS"],
            ),
            habitica=config_mod.HabiticaConfig(
                api_base="https://habitica.com/api/v3",
                task_id="task123",
                user_id_env="HABITICA_USER_ID",
                api_token_env="HABITICA_API_TOKEN",
                xp_per_review=0.2,
                gold_per_review=0.05,
                damage_per_missing_review=0.3,
                max_damage=15.0,
                reviews_per_score_up=20,
                missing_reviews_per_score_down=5,
            ),
            sync=config_mod.SyncConfig(
                min_daily_reviews=20,
                state_file=Path("/tmp/semester_state.json"),
                timezone="UTC",
                deck_name="Psychology",
                mastery_interval_days=7,
                mastery_ratio_threshold=0.8,
                units=[config_mod.UnitConfig(id="Unit_1", label="Unit 1", anki_tag="Unit_1")],
            ),
            render=config_mod.RenderConfig(
                mode="none",
                html_template=Path("/tmp/path.html.j2"),
                html_output=Path("/tmp/index.html"),
                canvas_file=Path("/tmp/course_map.canvas"),
            ),
            ingest=config_mod.IngestConfig(
                provider="mock",
                model="gpt-4.1-mini",
                api_key_env="OPENAI_API_KEY",
                max_cards=10,
                default_unit_tag="Unit_1",
            ),
        )

    def test_pass_outcome(self):
        outcome = sync_mod.evaluate_daily_outcome(reviews_today=44, config=self._build_config())
        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.score_direction, "up")
        self.assertEqual(outcome.score_events, 2)
        self.assertEqual(outcome.missing_reviews, 0)

    def test_fail_outcome(self):
        outcome = sync_mod.evaluate_daily_outcome(reviews_today=8, config=self._build_config())
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.score_direction, "down")
        self.assertEqual(outcome.score_events, 3)
        self.assertEqual(outcome.missing_reviews, 12)


if __name__ == "__main__":
    unittest.main()
