from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from quizzes.flashcard_services import (
    FlashcardValidationError,
    clear_flashcard_service_caches,
    list_flashcard_deck_entries,
    load_flashcard_deck,
)
from quizzes.models import FlashcardReview, FlashcardUserAnswer, QuizProgress
from quizzes.subject_services import clear_subject_service_caches


REPO_ROOT = Path(__file__).resolve().parents[3]
IMPORTER_PATH = REPO_ROOT / "scripts" / "import_anki_flashcards.py"
SOURCE_DECK_PATH = (
    REPO_ROOT
    / "shows"
    / "bioneuro"
    / "flashcards"
    / "source"
    / "Biologisk-psykologi-og-Neuropsykologi.apkg"
)


def _load_importer_module():
    spec = importlib.util.spec_from_file_location("import_anki_flashcards", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load import_anki_flashcards.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AnkiFlashcardImporterTests(SimpleTestCase):
    def test_sanitizer_strips_scripts_handlers_and_javascript_urls(self) -> None:
        importer = _load_importer_module()

        sanitized = importer.sanitize_html(
            '<div onclick="alert(1)">Answer</div>'
            '<script>alert(2)</script>'
            '<a href="javascript:alert(3)">bad</a>'
            "<strong>kept</strong>"
        )

        self.assertIn("<div>Answer</div>", sanitized)
        self.assertIn("bad", sanitized)
        self.assertIn("<strong>kept</strong>", sanitized)
        self.assertNotIn("onclick", sanitized)
        self.assertNotIn("script", sanitized)
        self.assertNotIn("javascript:", sanitized)

    @skipUnless(shutil.which("zstd"), "zstd CLI required for collection.anki21b")
    def test_importer_extracts_current_bioneuro_deck_deterministically(self) -> None:
        importer = _load_importer_module()
        self.assertTrue(SOURCE_DECK_PATH.is_file())

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.json"
            second = Path(temp_dir) / "second.json"
            with tempfile.TemporaryDirectory() as db_temp:
                db_path = Path(db_temp) / "collection.sqlite"
                member = importer.extract_collection_database(SOURCE_DECK_PATH, db_path)
                cards = importer.load_cards_from_database(db_path)
            artifact = importer.build_artifact(
                package_path=SOURCE_DECK_PATH,
                subject_slug="bioneuro",
                deck_slug="biologisk-psykologi-og-neuropsykologi",
                title="Biologisk psykologi og neuropsykologi",
                cards=cards,
                collection_member=member,
            )
            importer.write_json(first, artifact)
            importer.write_json(second, artifact)

            payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(payload["card_count"], 661)
            self.assertEqual(len(payload["cards"]), 661)
            self.assertEqual(len({card["card_id"] for card in payload["cards"]}), 661)
            self.assertEqual(sum(category["card_count"] for category in payload["categories"]), 661)
            self.assertTrue(all(card["category_slug"] for card in payload["cards"]))
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))


class FlashcardPortalTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=REPO_ROOT)
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)

        self.subject_root = root / "shows" / "bioneuro"
        self.flashcard_root = self.subject_root / "flashcards"
        self.flashcard_root.mkdir(parents=True, exist_ok=True)
        self.artifact_path = self.flashcard_root / "deck.json"
        self.registry_path = self.flashcard_root / "decks.json"
        self.subjects_path = root / "subjects.json"
        self.content_manifest_path = self.subject_root / "content_manifest.json"
        self.reading_key_path = self.subject_root / "docs" / "freudd-reading-file-key.md"
        self.reading_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.reading_key_path.write_text("", encoding="utf-8")

        self._write_subjects_file()
        self._write_flashcard_artifact()
        self._write_flashcard_registry()

        self.override = override_settings(
            FREUDD_SUBJECTS_JSON_PATH=self.subjects_path,
            FREUDD_SUBJECT_CONTENT_MANIFEST_PATH=self.content_manifest_path,
            FREUDD_READING_KEY_PATH=self.reading_key_path,
            FREUDD_READING_MASTER_KEY_PATH=self.reading_key_path,
            FREUDD_READING_MASTER_KEY_FALLBACK_PATH=self.reading_key_path,
            QUIZ_FILES_ROOT=root / "quizzes",
            QUIZ_LINKS_JSON_PATH=root / "quiz_links.json",
            FREUDD_SUBJECT_FEED_RSS_PATH=self.subject_root / "feeds" / "rss.xml",
            FREUDD_SUBJECT_EPISODE_INVENTORY_PATH=self.subject_root / "episode_inventory.json",
            FREUDD_SUBJECT_SPOTIFY_MAP_PATH=self.subject_root / "spotify_map.json",
            FREUDD_READING_FILES_ROOT=root / "readings",
            FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH=self.subject_root / "reading_download_exclusions.json",
            FREUDD_SUBJECT_SLIDES_CATALOG_PATH=self.subject_root / "slides_catalog.json",
            FREUDD_SUBJECT_SLIDES_FILES_ROOT=root / "slides",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        clear_subject_service_caches()
        clear_flashcard_service_caches()
        self.addCleanup(clear_subject_service_caches)
        self.addCleanup(clear_flashcard_service_caches)

    def _write_subjects_file(self) -> None:
        self.subjects_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subjects": [
                        {
                            "slug": "bioneuro",
                            "title": "Bioneuro",
                            "description": "Bio / Neuropsychology F26",
                            "active": True,
                            "paths": {
                                "reading_key_path": str(self.reading_key_path),
                                "content_manifest_path": str(self.content_manifest_path),
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _write_flashcard_artifact(self) -> None:
        self.artifact_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "artifact_type": "freudd_flashcards",
                    "subject_slug": "bioneuro",
                    "deck_slug": "test-deck",
                    "title": "Test Deck",
                    "source_file": "test.apkg",
                    "source_sha256": "abc",
                    "generated_at": "2026-05-19T00:00:00Z",
                    "card_count": 2,
                    "categories": [
                        {"slug": "grundbegreber", "title": "Grundbegreber", "card_count": 1},
                        {"slug": "neuroner-og-synapser", "title": "Neuroner og synapser", "card_count": 1},
                    ],
                    "cards": [
                        {
                            "card_id": "anki-1",
                            "front_text": "Front 1",
                            "back_html_sanitized": "<div>Back 1</div>",
                            "back_text": "Back 1",
                            "tags": [],
                            "category_slug": "grundbegreber",
                            "category_title": "Grundbegreber",
                            "content_sha256": "one",
                        },
                        {
                            "card_id": "anki-2",
                            "front_text": "Front 2",
                            "back_html_sanitized": "<strong>Back 2</strong>",
                            "back_text": "Back 2",
                            "tags": ["w01"],
                            "category_slug": "neuroner-og-synapser",
                            "category_title": "Neuroner og synapser",
                            "content_sha256": "two",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _write_flashcard_registry(self, *, artifact_path: str | None = None) -> None:
        artifact_path_value = artifact_path or str(self.artifact_path.relative_to(REPO_ROOT))
        self.registry_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "bioneuro",
                    "decks": [
                        {
                            "deck_slug": "test-deck",
                            "title": "Test Deck",
                            "description": "Imported test cards.",
                            "artifact_path": artifact_path_value,
                            "card_count": 2,
                            "enabled": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _user(self) -> User:
        return User.objects.create_user(username="alice", password="Secret123!!")

    def test_service_loads_enabled_deck(self) -> None:
        entries = list_flashcard_deck_entries("bioneuro")
        self.assertEqual(len(entries), 1)

        deck = load_flashcard_deck("bioneuro", "test-deck")
        self.assertEqual(deck.card_count, 2)
        self.assertEqual(deck.cards[0]["card_id"], "anki-1")

    def test_service_rejects_path_traversal_registry_entry(self) -> None:
        self._write_flashcard_registry(artifact_path="../bad.json")
        clear_flashcard_service_caches()

        with self.assertRaises(FlashcardValidationError):
            list_flashcard_deck_entries("bioneuro")

    def test_flashcard_practice_and_api_allow_anonymous_preview(self) -> None:
        page = self.client.get(
            reverse("flashcard-practice", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Preview uden login")
        self.assertContains(page, "dine svar og din progress gemmes ikke")
        self.assertContains(page, "const previewMode = true;")

        api = self.client.get(
            reverse("flashcard-content", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})
        )
        self.assertEqual(api.status_code, 200)
        payload = api.json()
        self.assertIsNone(payload["review_summary"])
        self.assertIsNone(payload["cards"][0]["review"])
        self.assertEqual(payload["cards"][0]["user_answer"], "")
        self.assertIsNone(payload["cards"][0]["user_answer_updated_at"])

        answer_post = self.client.post(
            reverse("flashcard-answer", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"}),
            data=json.dumps({"card_id": "anki-1", "answer_text": "anonymous draft"}),
            content_type="application/json",
        )
        self.assertEqual(answer_post.status_code, 403)
        self.assertEqual(FlashcardUserAnswer.objects.count(), 0)

    def test_flashcard_practice_and_api_render_for_logged_in_user(self) -> None:
        self.client.force_login(self._user())

        page = self.client.get(
            reverse("flashcard-practice", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "anki-kort")
        self.assertContains(page, "Test Deck")
        self.assertContains(page, "Ubesvarede")
        self.assertContains(page, "Besvarede")
        self.assertContains(page, "Ikke vurderet endnu")
        self.assertContains(page, "Skriv svar")
        self.assertContains(page, "Mit svar")
        self.assertContains(page, 'id="flashcard-category-filter"')
        self.assertContains(page, "Alle emner")
        self.assertContains(page, "const answerUrl =")
        self.assertContains(page, 'id="flashcard-user-answer-panel" class="flashcard-user-answer is-hidden"')
        self.assertContains(page, 'id="flashcard-answer" class="flashcard-answer is-hidden"')
        self.assertContains(page, "Vis svar")
        self.assertContains(page, 'answerNode.classList.toggle("is-hidden", !showingAnswer);')
        self.assertContains(page, ".flashcard-shell .is-hidden")
        self.assertContains(page, "const previewMode = false;")

        api = self.client.get(
            reverse("flashcard-content", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})
        )
        self.assertEqual(api.status_code, 200)
        payload = api.json()
        self.assertEqual(payload["card_count"], 2)
        self.assertEqual(payload["categories"][0]["title"], "Grundbegreber")
        self.assertEqual(payload["cards"][0]["front_text"], "Front 1")
        self.assertEqual(payload["cards"][0]["back_html"], "<div>Back 1</div>")
        self.assertEqual(payload["cards"][0]["category_title"], "Grundbegreber")
        self.assertEqual(payload["cards"][0]["user_answer"], "")
        self.assertIsNone(payload["cards"][0]["user_answer_updated_at"])

    def test_flashcard_answer_post_persists_without_marking_reviewed(self) -> None:
        user = self._user()
        self.client.force_login(user)
        url = reverse("flashcard-answer", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})

        response = self.client.post(
            url,
            data=json.dumps({"card_id": "anki-1", "answer_text": "  Neurons and glia\r\n"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["card_id"], "anki-1")
        self.assertEqual(body["user_answer"], "Neurons and glia")
        self.assertIsNotNone(body["user_answer_updated_at"])

        answer = FlashcardUserAnswer.objects.get(
            user=user,
            subject_slug="bioneuro",
            deck_slug="test-deck",
            card_id="anki-1",
        )
        self.assertEqual(answer.answer_text, "Neurons and glia")
        self.assertEqual(FlashcardReview.objects.count(), 0)

        api = self.client.get(
            reverse("flashcard-content", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})
        )
        self.assertEqual(api.status_code, 200)
        payload = api.json()
        self.assertEqual(payload["review_summary"]["reviewed_count"], 0)
        self.assertEqual(payload["cards"][0]["user_answer"], "Neurons and glia")

        cleared = self.client.post(
            url,
            data=json.dumps({"card_id": "anki-1", "answer_text": "   "}),
            content_type="application/json",
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["user_answer"], "")
        self.assertIsNone(cleared.json()["user_answer_updated_at"])
        self.assertEqual(FlashcardUserAnswer.objects.count(), 0)

    def test_flashcard_review_post_upserts_without_quiz_progress(self) -> None:
        user = self._user()
        self.client.force_login(user)
        url = reverse("flashcard-review", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"})

        first = self.client.post(
            url,
            data=json.dumps({"card_id": "anki-1", "rating": "good", "answer_text": "My recall"}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["review_count"], 1)
        self.assertEqual(first.json()["user_answer"], "My recall")

        second = self.client.post(
            url,
            data=json.dumps({"card_id": "anki-1", "rating": "again"}),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["review_count"], 2)
        self.assertEqual(second.json()["rating"], "again")
        self.assertNotIn("user_answer", second.json())

        review = FlashcardReview.objects.get(
            user=user,
            subject_slug="bioneuro",
            deck_slug="test-deck",
            card_id="anki-1",
        )
        self.assertEqual(review.rating, "again")
        self.assertEqual(review.review_count, 2)
        answer = FlashcardUserAnswer.objects.get(
            user=user,
            subject_slug="bioneuro",
            deck_slug="test-deck",
            card_id="anki-1",
        )
        self.assertEqual(answer.answer_text, "My recall")
        self.assertEqual(QuizProgress.objects.count(), 0)

    def test_subject_detail_shows_flashcard_entry_point(self) -> None:
        self.client.force_login(self._user())

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={"lectures": [], "source_meta": {}},
        ):
            response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "bioneuro"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "anki-kort")
        self.assertContains(response, "2 kort fordelt på 2 emner")
        self.assertContains(response, "Grundbegreber")
        self.assertContains(response, "Neuroner og synapser")
        self.assertContains(response, "0/2 kort besvaret")
        self.assertContains(
            response,
            reverse("flashcard-practice", kwargs={"subject_slug": "bioneuro", "deck_slug": "test-deck"}),
        )
