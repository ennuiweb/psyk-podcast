import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "transcribe_episode_ab_review.py"
    )
    spec = importlib.util.spec_from_file_location("transcribe_episode_ab_review", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TranscribeEpisodeABReviewTests(unittest.TestCase):
    def test_build_stt_prompt_includes_source_labels_and_key_points(self):
        mod = _load_module()

        prompt = mod.build_stt_prompt(
            {
                "prompt_type": "single_reading",
                "lecture_key": "W10L2",
                "source_context": {
                    "source_files": [
                        "/tmp/W10L2 Davies (1990).pdf",
                        "/tmp/W10L2 Foucault (1997).pdf",
                    ],
                    "key_points": [
                        "power relations are not identical to domination",
                        "freedom practices differ from liberation",
                    ],
                },
            }
        )

        self.assertIn("Episode type: single_reading.", prompt)
        self.assertIn("Lecture key: W10L2.", prompt)
        self.assertIn("W10L2 Davies (1990)", prompt)
        self.assertIn("freedom practices differ from liberation", prompt)

    def test_segment_time_for_size_returns_zero_below_limit(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audio.mp3"
            path.write_bytes(b"x" * 1024)

            result = mod.segment_time_for_size(path, max_upload_bytes=2048)

        self.assertEqual(result, 0)

    def test_segment_time_for_size_scales_from_duration(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audio.mp3"
            path.write_bytes(b"x" * 10_000)

            with mock.patch.object(mod, "ffprobe_duration_seconds", return_value=1000.0):
                result = mod.segment_time_for_size(path, max_upload_bytes=1_000)

        self.assertGreaterEqual(result, 300)

    def test_resolve_paths_uses_run_relative_layout(self):
        mod = _load_module()
        manifest_path = Path("/tmp/run/manifest.json")
        entry = {
            "sample_id": "single_reading__w11l1__hacking_2007",
            "baseline": {
                "transcript_path": "transcripts/before/single_reading__w11l1__hacking_2007.txt",
            },
        }

        resolved = mod.resolve_paths(manifest_path, entry, "baseline")

        self.assertEqual(
            resolved["transcript_txt"],
            Path("/tmp/run/transcripts/before/single_reading__w11l1__hacking_2007.txt"),
        )
        self.assertEqual(
            resolved["stt_prompt"],
            Path("/tmp/run/stt_prompts/before/single_reading__w11l1__hacking_2007.txt"),
        )

    def test_speaker_labeled_text_groups_words_by_speaker(self):
        mod = _load_module()

        text = mod.speaker_labeled_text_from_words(
            [
                {"text": "Hello", "speaker_id": "speaker_0"},
                {"text": "there", "speaker_id": "speaker_0"},
                {"text": ".", "speaker_id": "speaker_0"},
                {"text": "Conceptually", "speaker_id": "speaker_1"},
                {"text": "yes", "speaker_id": "speaker_1"},
                {"text": ".", "speaker_id": "speaker_1"},
            ]
        )

        self.assertEqual(text, "speaker_0: Hello there.\n\nspeaker_1: Conceptually yes.")

    def test_build_elevenlabs_keyterms_filters_and_deduplicates(self):
        mod = _load_module()

        terms = mod.build_elevenlabs_keyterms(
            {
                "source_context": {
                    "source_files": ["/tmp/W10L2 Foucault, M. (1997).pdf"],
                    "key_points": [
                        "power relations are not identical to domination",
                        "this one is far too long to be accepted as an elevenlabs keyterm phrase",
                    ],
                }
            },
            limit=20,
        )

        self.assertIn("power relations", terms)
        self.assertIn("Foucault, M", terms)
        self.assertNotIn(
            "this one is far too long to be accepted as an elevenlabs keyterm phrase",
            terms,
        )

    def test_transcribe_elevenlabs_scribe_posts_diarization_payload(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.mp3"
            audio_path.write_bytes(b"audio")

            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {
                "text": "Hello there. Conceptually yes.",
                "words": [
                    {"text": "Hello", "speaker_id": "speaker_0"},
                    {"text": "there", "speaker_id": "speaker_0"},
                    {"text": ".", "speaker_id": "speaker_0"},
                    {"text": "Conceptually", "speaker_id": "speaker_1"},
                    {"text": "yes", "speaker_id": "speaker_1"},
                    {"text": ".", "speaker_id": "speaker_1"},
                ],
            }
            fake_requests = types.SimpleNamespace(post=mock.Mock(return_value=response))

            with mock.patch.dict(sys.modules, {"requests": fake_requests}):
                speaker_text, plain_text, payload, keyterms = mod.transcribe_elevenlabs_scribe(
                    api_key="secret",
                    audio_path=audio_path,
                    model="scribe_v2",
                    entry={"source_context": {"key_points": ["power relations"]}},
                    num_speakers=2,
                    keyterms_limit=10,
                    language_code="eng",
                    tag_audio_events=False,
                    timeout_seconds=120,
                )

        self.assertEqual(speaker_text, "speaker_0: Hello there.\n\nspeaker_1: Conceptually yes.")
        self.assertEqual(plain_text, "Hello there. Conceptually yes.")
        self.assertEqual(payload["text"], "Hello there. Conceptually yes.")
        self.assertIn("power relations", keyterms)
        fake_requests.post.assert_called_once()
        kwargs = fake_requests.post.call_args.kwargs
        self.assertEqual(kwargs["headers"], {"xi-api-key": "secret"})
        self.assertIn(("model_id", "scribe_v2"), kwargs["data"])
        self.assertIn(("diarize", "true"), kwargs["data"])
        self.assertIn(("num_speakers", "2"), kwargs["data"])
        self.assertIn(("keyterms", "power relations"), kwargs["data"])


if __name__ == "__main__":
    unittest.main()
